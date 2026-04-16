"""
inference-service/app/models.py

Load trained model artifacts from disk at service startup.

Two artifact sets are loaded independently:
  MF artifacts        — model.pth + config.json + user2idx.json + item2idx.json
  Popularity artifact — popularity_model.json

Either may be absent (e.g., training hasn't run yet). The service degrades
gracefully: missing MF → cold-start users always get popularity; missing
popularity → the fallback itself is unavailable and the health check degrades.

MatrixFactorization is defined here (not imported from training/) because
the inference service must not depend on training code. In production this
boundary would be enforced by packaging: the model architecture lives in a
shared library, and artifacts are distributed as TorchScript or ONNX. For
this repo the class is small enough that an intentional local copy is cleaner
than a circular import.

IMPORTANT: the MatrixFactorization class here must stay structurally identical
to training/models/mf.py — same layer names, same shapes — or torch.load()
will fail with a missing-key error.
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path

import torch
import torch.nn as nn

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Model architecture (must match training/models/mf.py)
# ---------------------------------------------------------------------------

class MatrixFactorization(nn.Module):
    """
    Dot-product MF with user/item bias terms.
    score(u, i) = sigmoid( <U_u, V_i> + b_u + b_i )
    """

    def __init__(self, n_users: int, n_items: int, embedding_dim: int) -> None:
        super().__init__()
        self.user_emb  = nn.Embedding(n_users, embedding_dim)
        self.item_emb  = nn.Embedding(n_items, embedding_dim)
        self.user_bias = nn.Embedding(n_users, 1)
        self.item_bias = nn.Embedding(n_items, 1)

    def forward(self, user_idx: torch.Tensor, item_idx: torch.Tensor) -> torch.Tensor:
        u    = self.user_emb(user_idx)
        v    = self.item_emb(item_idx)
        dot  = (u * v).sum(dim=1)
        bias = self.user_bias(user_idx).squeeze(1) + self.item_bias(item_idx).squeeze(1)
        return torch.sigmoid(dot + bias)


# ---------------------------------------------------------------------------
# Artifact bundles
# ---------------------------------------------------------------------------

@dataclass
class MFBundle:
    """Everything needed to serve MF recommendations."""
    model:    MatrixFactorization
    user2idx: dict[str, int]
    idx2item: dict[int, str]   # int keys for direct lookup after topk()
    n_items:  int
    device:   torch.device


@dataclass
class PopularityBundle:
    """Everything needed to serve popularity recommendations."""
    ranked_items: list[str]           # pre-sorted, descending score
    item_scores:  dict[str, float]    # item_id → raw score (for normalization)


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_mf(artifact_dir: Path) -> MFBundle | None:
    """
    Load MF weights and index mappings from disk.

    Returns None (and logs a warning) if any required file is missing,
    allowing the service to start and fall back to popularity.
    """
    base = artifact_dir / "mf"
    required = ["model.pth", "config.json", "user2idx.json", "item2idx.json"]
    missing  = [f for f in required if not (base / f).exists()]

    if missing:
        logger.warning("mf_artifacts_missing files=%s — MF recommender disabled", missing)
        return None

    with open(base / "config.json") as f:
        cfg = json.load(f)

    with open(base / "user2idx.json") as f:
        user2idx: dict[str, int] = json.load(f)

    with open(base / "item2idx.json") as f:
        item2idx_str: dict[str, int] = json.load(f)

    # Invert item2idx; keys come back as strings from JSON — convert to int
    idx2item: dict[int, str] = {int(v): k for k, v in item2idx_str.items()}

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    model = MatrixFactorization(
        n_users=cfg["n_users"],
        n_items=cfg["n_items"],
        embedding_dim=cfg["embedding_dim"],
    )
    state = torch.load(base / "model.pth", map_location=device, weights_only=True)
    model.load_state_dict(state)
    model.to(device)
    model.eval()

    logger.info(
        "mf_loaded n_users=%d n_items=%d embedding_dim=%d device=%s",
        cfg["n_users"], cfg["n_items"], cfg["embedding_dim"], device,
    )
    return MFBundle(
        model=model,
        user2idx=user2idx,
        idx2item=idx2item,
        n_items=cfg["n_items"],
        device=device,
    )


def load_popularity(artifact_dir: Path) -> PopularityBundle | None:
    """
    Load popularity scores from disk.

    Returns None (and logs a warning) if the artifact is missing.
    """
    path = artifact_dir / "popularity" / "popularity_model.json"

    if not path.exists():
        logger.warning("popularity_artifact_missing path=%s — popularity recommender disabled", path)
        return None

    with open(path) as f:
        payload = json.load(f)

    item_scores: dict[str, float] = payload["item_scores"]
    ranked_items = sorted(item_scores, key=item_scores.__getitem__, reverse=True)

    logger.info("popularity_loaded items=%d", len(ranked_items))
    return PopularityBundle(ranked_items=ranked_items, item_scores=item_scores)
