"""
training/train.py

Main training pipeline entry point.

Execution order:
  1. Load and filter interaction data from PostgreSQL
  2. Build index mappings and holdout split
  3. Train popularity baseline  → evaluate  → save artifact
  4. Train matrix factorization → evaluate  → save artifact
  5. Register both models in the model_registry table

Run:
    python -m training.train

All hyperparameters are env-overridable via TRAINING_* variables.
See training/config.py for the full list.

AWS equivalent:
  SageMaker Training Job triggered by Step Functions or an EventBridge
  schedule. Artifacts written to s3://bucket/models/<name>/<version>/.
  Model registry entries use S3 URIs and integrate with SageMaker Model
  Registry for canary / shadow deployment approval flows.
"""

import json
import logging
import time
from pathlib import Path

import psycopg2
import torch
import torch.optim as optim

from shared.logging_config import configure_logging, get_logger
from training.config import get_settings
from training.data.loader import (
    InteractionMatrix,
    build_dataloaders,
    load_interactions,
)
from training.evaluate import evaluate_recommender
from training.models.mf import MatrixFactorization, evaluate_loss, train_epoch
from training.models.popularity import PopularityRecommender

_settings = get_settings()
configure_logging(_settings.service_name, _settings.log_level)
logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Artifact saving
# ---------------------------------------------------------------------------

def _save_popularity(model: PopularityRecommender, artifact_dir: Path) -> Path:
    out = artifact_dir / "popularity"
    model.save(out)
    return out


def _save_mf(
    model: MatrixFactorization,
    matrix: InteractionMatrix,
    embedding_dim: int,
    artifact_dir: Path,
) -> Path:
    """
    Save MF artifacts in a format the inference service can load cold:
      model.pth     — state_dict (weights only, no class dependency)
      config.json   — architecture params needed to reconstruct the model
      user2idx.json — user_id → integer index mapping
      item2idx.json — item_id → integer index mapping
    """
    out = artifact_dir / "mf"
    out.mkdir(parents=True, exist_ok=True)

    torch.save(model.state_dict(), out / "model.pth")

    with open(out / "config.json", "w") as f:
        json.dump(
            {"n_users": matrix.n_users, "n_items": matrix.n_items, "embedding_dim": embedding_dim},
            f, indent=2,
        )

    with open(out / "user2idx.json", "w") as f:
        json.dump(matrix.user2idx, f)

    with open(out / "item2idx.json", "w") as f:
        json.dump(matrix.item2idx, f)

    logger.info("mf_artifacts_saved path=%s", out)
    return out


# ---------------------------------------------------------------------------
# Model registry
# ---------------------------------------------------------------------------

def _register_model(
    database_url: str,
    model_name: str,
    version: str,
    artifact_path: str,
    metrics: dict,
) -> None:
    """Upsert a model run into the model_registry table."""
    conn = psycopg2.connect(database_url)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO model_registry (model_name, version, artifact_path, metrics)
                VALUES (%s, %s, %s, %s::jsonb)
                ON CONFLICT (model_name, version) DO UPDATE SET
                    artifact_path = EXCLUDED.artifact_path,
                    metrics       = EXCLUDED.metrics,
                    trained_at    = NOW()
                """,
                (model_name, version, artifact_path, json.dumps(metrics)),
            )
        conn.commit()
        logger.info("model_registered name=%s version=%s", model_name, version)
    except psycopg2.Error as exc:
        logger.error("model_registry_failed name=%s error=%s", model_name, exc)
        conn.rollback()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# MF recommendation wrapper for evaluate_recommender()
# ---------------------------------------------------------------------------

@torch.no_grad()
def _mf_recommend(
    model: MatrixFactorization,
    matrix: InteractionMatrix,
    device: torch.device,
    user_id: str,
    k: int,
) -> list[str]:
    """Score all items for a user, mask seen items, return top-K item_ids."""
    user_idx = matrix.user2idx.get(user_id)
    if user_idx is None:
        return []

    model.eval()
    n = matrix.n_items
    user_tensor = torch.full((n,), user_idx, dtype=torch.long, device=device)
    item_tensor = torch.arange(n, dtype=torch.long, device=device)

    scores = model(user_tensor, item_tensor).cpu()  # (n_items,)

    # Mask items the user has already seen so we don't recommend them
    for seen_idx in matrix.user_items.get(user_idx, set()):
        scores[seen_idx] = -1.0

    top_k_indices = scores.topk(k).indices.tolist()
    return [matrix.idx2item[i] for i in top_k_indices]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run() -> None:
    settings  = get_settings()
    artifact_dir = Path(settings.artifact_dir)
    device    = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.info("training_started device=%s", device)

    # ------------------------------------------------------------------
    # 1. Load data
    # ------------------------------------------------------------------
    interactions = load_interactions(
        database_url=settings.database_url,
        min_interactions=settings.min_interactions,
    )
    if not interactions:
        logger.error(
            "no_interactions_loaded — populate the database first "
            "(python -m training.data.generate_synthetic --db-url <url>)"
        )
        return

    matrix = InteractionMatrix(interactions)
    train_data, val_data, test_data, test_ground_truth = matrix.holdout_split(
        seed=settings.seed,
    )

    if not test_ground_truth:
        logger.warning("test_ground_truth_empty — dataset too small for evaluation")

    train_loader, val_loader, _ = build_dataloaders(
        matrix=matrix,
        train_interactions=train_data,
        val_interactions=val_data,
        test_interactions=test_data,
        batch_size=settings.batch_size,
        n_negatives=settings.n_negatives,
        seed=settings.seed,
    )

    # ------------------------------------------------------------------
    # 2. Popularity baseline
    # ------------------------------------------------------------------
    logger.info("training_popularity_baseline")
    popularity = PopularityRecommender()
    popularity.fit(interactions)

    pop_metrics = evaluate_recommender(
        recommend_fn=lambda uid, k: [iid for iid, _ in popularity.recommend(uid, k)],
        ground_truth=test_ground_truth,
        k=settings.eval_k,
    )

    pop_path = _save_popularity(popularity, artifact_dir)
    _register_model(
        database_url=settings.database_url,
        model_name="popularity",
        version="v1",
        artifact_path=str(pop_path.resolve()),
        metrics={**pop_metrics, "k": settings.eval_k},
    )

    # ------------------------------------------------------------------
    # 3. Matrix factorization
    # ------------------------------------------------------------------
    logger.info(
        "training_mf n_users=%d n_items=%d embedding_dim=%d epochs=%d",
        matrix.n_users, matrix.n_items, settings.embedding_dim, settings.n_epochs,
    )

    mf_model = MatrixFactorization(
        n_users=matrix.n_users,
        n_items=matrix.n_items,
        embedding_dim=settings.embedding_dim,
    ).to(device)

    optimizer = optim.Adam(
        mf_model.parameters(),
        lr=settings.learning_rate,
        weight_decay=settings.weight_decay,
    )

    best_val_loss = float("inf")
    # Store cloned tensors so we don't keep a reference to the live model
    best_state: dict | None = None

    for epoch in range(1, settings.n_epochs + 1):
        t0         = time.monotonic()
        train_loss = train_epoch(mf_model, train_loader, optimizer, device)
        val_loss   = evaluate_loss(mf_model, val_loader, device)
        elapsed    = time.monotonic() - t0

        logger.info(
            "epoch=%d/%d train_loss=%.4f val_loss=%.4f elapsed_s=%.1f",
            epoch, settings.n_epochs, train_loss, val_loss, elapsed,
        )

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_state = {k: v.clone() for k, v in mf_model.state_dict().items()}

    # Restore best checkpoint before evaluation and saving
    if best_state is not None:
        mf_model.load_state_dict(best_state)

    mf_metrics = evaluate_recommender(
        recommend_fn=lambda uid, k: _mf_recommend(mf_model, matrix, device, uid, k),
        ground_truth=test_ground_truth,
        k=settings.eval_k,
    )

    mf_path = _save_mf(mf_model, matrix, settings.embedding_dim, artifact_dir)
    _register_model(
        database_url=settings.database_url,
        model_name="mf",
        version="v1",
        artifact_path=str(mf_path.resolve()),
        metrics={**mf_metrics, "k": settings.eval_k, "best_val_loss": round(best_val_loss, 6)},
    )

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    logger.info(
        "training_complete "
        "popularity_ndcg=%.4f mf_ndcg=%.4f "
        "popularity_recall=%.4f mf_recall=%.4f",
        pop_metrics.get("ndcg", 0.0),
        mf_metrics.get("ndcg", 0.0),
        pop_metrics.get("recall", 0.0),
        mf_metrics.get("recall", 0.0),
    )


if __name__ == "__main__":
    run()
