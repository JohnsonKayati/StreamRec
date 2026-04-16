"""
training/models/mf.py

Dot-product Matrix Factorization for implicit-feedback collaborative filtering.

Architecture:
    score(u, i) = sigmoid( <U_u, V_i> + b_u + b_i )

Trained with binary cross-entropy on positive/negative-sampled interactions.
Sigmoid output keeps scores in [0, 1] and pairs naturally with BCELoss.

Design notes:
  - Xavier-normal init on embeddings stabilizes early training compared to
    the default uniform init, which can push sigmoid into saturation.
  - Zero-init on bias terms: neutral starting point, learned jointly.
  - evaluate_loss() is separated from train_epoch() so callers can track
    val loss without accidentally updating weights.

AWS equivalent:
  SageMaker built-in Factorization Machines covers this use case at scale.
  For custom architecture: SageMaker Training Job with a PyTorch container,
  artifacts written to S3, registered in SageMaker Model Registry.
"""

import logging

import torch
import torch.nn as nn
from torch.utils.data import DataLoader

logger = logging.getLogger(__name__)


class MatrixFactorization(nn.Module):
    """
    Standard MF with user/item embeddings and bias terms.

    Args:
        n_users:       Number of users in the training catalogue.
        n_items:       Number of items in the training catalogue.
        embedding_dim: Latent factor dimensionality (D).
    """

    def __init__(self, n_users: int, n_items: int, embedding_dim: int) -> None:
        super().__init__()
        self.user_emb  = nn.Embedding(n_users, embedding_dim)
        self.item_emb  = nn.Embedding(n_items, embedding_dim)
        self.user_bias = nn.Embedding(n_users, 1)
        self.item_bias = nn.Embedding(n_items, 1)

        nn.init.xavier_normal_(self.user_emb.weight)
        nn.init.xavier_normal_(self.item_emb.weight)
        nn.init.zeros_(self.user_bias.weight)
        nn.init.zeros_(self.item_bias.weight)

    def forward(
        self, user_idx: torch.Tensor, item_idx: torch.Tensor
    ) -> torch.Tensor:
        """
        Args:
            user_idx: (B,) long tensor of user indices
            item_idx: (B,) long tensor of item indices
        Returns:
            (B,) float tensor of scores in [0, 1]
        """
        u = self.user_emb(user_idx)                           # (B, D)
        v = self.item_emb(item_idx)                           # (B, D)
        dot = (u * v).sum(dim=1)                              # (B,)
        bias = (
            self.user_bias(user_idx).squeeze(1)
            + self.item_bias(item_idx).squeeze(1)
        )                                                      # (B,)
        return torch.sigmoid(dot + bias)                       # (B,)


def train_epoch(
    model: MatrixFactorization,
    loader: DataLoader,
    optimizer: torch.optim.Optimizer,
    device: torch.device,
) -> float:
    """Run one training epoch. Returns mean BCE loss over all batches."""
    model.train()
    criterion = nn.BCELoss()
    total_loss = 0.0
    n_batches = 0

    for user_idx, item_idx, labels in loader:
        user_idx = user_idx.to(device)
        item_idx = item_idx.to(device)
        labels   = labels.to(device)

        optimizer.zero_grad()
        preds = model(user_idx, item_idx)
        loss  = criterion(preds, labels)
        loss.backward()
        optimizer.step()

        total_loss += loss.item()
        n_batches  += 1

    return total_loss / n_batches if n_batches > 0 else 0.0


def evaluate_loss(
    model: MatrixFactorization,
    loader: DataLoader,
    device: torch.device,
) -> float:
    """Compute mean BCE loss on a DataLoader without updating weights."""
    model.eval()
    criterion = nn.BCELoss()
    total_loss = 0.0
    n_batches  = 0

    with torch.no_grad():
        for user_idx, item_idx, labels in loader:
            user_idx = user_idx.to(device)
            item_idx = item_idx.to(device)
            labels   = labels.to(device)
            preds = model(user_idx, item_idx)
            total_loss += criterion(preds, labels).item()
            n_batches  += 1

    return total_loss / n_batches if n_batches > 0 else 0.0
