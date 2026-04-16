"""
training/data/loader.py

Load interaction data from PostgreSQL and build structures for training.

Responsibilities:
  load_interactions()  — fetch and aggregate raw events from Postgres
  InteractionMatrix    — build user/item index mappings and holdout splits
  NCFDataset           — PyTorch Dataset with in-epoch negative sampling
  build_dataloaders()  — wrap pre-split interactions into DataLoaders

Design decisions:
  - Aggregation (COUNT per user/item/event_type) is pushed to Postgres so
    we never transfer one row per raw event over the wire.
  - EVENT_WEIGHTS are applied in Python to keep weight logic in one place
    (shared/constants.py). This is correct because only Python needs them.
  - min_interactions filtering removes noise users and cold-start items.
    A user who clicked one item once contributes almost nothing to MF
    gradient updates; including them inflates the embedding table for free.
  - holdout_split() does a per-user random holdout (not global temporal).
    For proper temporal evaluation, store per-event timestamps and sort
    each user's history before splitting.

AWS equivalent:
  In production, batch training jobs read from S3-partitioned Parquet files
  written by Glue/Spark to avoid query load on the operational database.
"""

import logging
from dataclasses import dataclass

import numpy as np
import psycopg2
import psycopg2.extras
import torch
from torch.utils.data import DataLoader, Dataset

from shared.constants import EVENT_WEIGHTS

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RawInteraction:
    """
    Aggregated interaction score for one (user, item) pair.

    score is the weighted sum of all event contributions:
        score = sum(EVENT_WEIGHTS[event_type] * count for each event_type)
    """
    user_id: str
    item_id: str
    score: float


def load_interactions(
    database_url: str,
    min_interactions: int = 5,
) -> list[RawInteraction]:
    """
    Load and aggregate interaction scores from the events table.

    Steps:
      1. COUNT events per (user_id, item_id, event_type) in Postgres.
      2. Multiply by EVENT_WEIGHTS in Python, sum per (user, item) pair.
      3. Drop pairs with score <= 0 (e.g., only remove_from_cart events).
      4. Drop users and items below min_interactions to reduce noise.

    Returns:
        Sorted list of RawInteractions for reproducibility.
    """
    logger.info("loading_interactions min_interactions=%d", min_interactions)

    conn = psycopg2.connect(database_url)
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT user_id, item_id, event_type, COUNT(*) AS cnt
                FROM events
                WHERE item_id IS NOT NULL
                GROUP BY user_id, item_id, event_type
            """)
            rows = cur.fetchall()
    finally:
        conn.close()

    # Aggregate weighted score per (user, item) pair
    raw_scores: dict[tuple[str, str], float] = {}
    for row in rows:
        weight = EVENT_WEIGHTS.get(row["event_type"], 0.0)
        if weight == 0.0:
            continue
        key = (row["user_id"], row["item_id"])
        raw_scores[key] = raw_scores.get(key, 0.0) + weight * int(row["cnt"])

    interactions = [
        RawInteraction(user_id=uid, item_id=iid, score=score)
        for (uid, iid), score in raw_scores.items()
        if score > 0.0
    ]

    # Filter users and items below the interaction threshold
    user_counts: dict[str, int] = {}
    item_counts: dict[str, int] = {}
    for ia in interactions:
        user_counts[ia.user_id] = user_counts.get(ia.user_id, 0) + 1
        item_counts[ia.item_id] = item_counts.get(ia.item_id, 0) + 1

    filtered = [
        ia for ia in interactions
        if user_counts[ia.user_id] >= min_interactions
        and item_counts[ia.item_id] >= min_interactions
    ]

    logger.info(
        "interactions_loaded raw=%d filtered=%d users=%d items=%d",
        len(interactions),
        len(filtered),
        len({ia.user_id for ia in filtered}),
        len({ia.item_id for ia in filtered}),
    )

    return sorted(filtered, key=lambda ia: (ia.user_id, ia.item_id))


class InteractionMatrix:
    """
    Builds integer index mappings and train/val/test split state.

    Attributes:
        n_users, n_items:  catalogue sizes after filtering
        user2idx/item2idx: original ID (str) → integer index
        idx2user/idx2item: integer index → original ID
        interactions:      full list of (user_idx, item_idx, score) tuples
        user_items:        user_idx → set[item_idx]  — for NCFDataset negative sampling
        user_seen:         user_id  → set[item_id]   — for evaluation / seen-item filtering
    """

    def __init__(self, interactions: list[RawInteraction]) -> None:
        users = sorted({ia.user_id for ia in interactions})
        items = sorted({ia.item_id for ia in interactions})

        self.user2idx: dict[str, int] = {u: i for i, u in enumerate(users)}
        self.item2idx: dict[str, int] = {it: i for i, it in enumerate(items)}
        self.idx2user: dict[int, str] = {i: u for u, i in self.user2idx.items()}
        self.idx2item: dict[int, str] = {i: it for it, i in self.item2idx.items()}

        self.n_users = len(users)
        self.n_items = len(items)

        self.interactions: list[tuple[int, int, float]] = [
            (self.user2idx[ia.user_id], self.item2idx[ia.item_id], ia.score)
            for ia in interactions
        ]

        # O(1) score lookup used in holdout_split
        self._score_lookup: dict[tuple[int, int], float] = {
            (u, it): s for u, it, s in self.interactions
        }

        # Index-space view of per-user items: used in NCFDataset negative sampling
        self.user_items: dict[int, set[int]] = {}
        for u, it, _ in self.interactions:
            self.user_items.setdefault(u, set()).add(it)

        # Original-ID view: used in evaluation and PopularityRecommender
        self.user_seen: dict[str, set[str]] = {}
        for ia in interactions:
            self.user_seen.setdefault(ia.user_id, set()).add(ia.item_id)

    def holdout_split(
        self,
        test_frac: float = 0.1,
        val_frac: float = 0.1,
        seed: int = 42,
    ) -> tuple[
        list[tuple[int, int, float]],
        list[tuple[int, int, float]],
        list[tuple[int, int, float]],
        dict[str, set[str]],
    ]:
        """
        Per-user random holdout split.

        For each user with >= 3 interactions, holds out test_frac of their
        items for test and val_frac for val; the rest goes to train. Users
        with < 3 interactions are placed entirely in the training set.

        Returns:
            train, val, test  — lists of (user_idx, item_idx, score)
            test_ground_truth — {user_id: set[held-out item_ids]} for evaluation
        """
        rng = np.random.default_rng(seed)
        train: list[tuple[int, int, float]] = []
        val:   list[tuple[int, int, float]] = []
        test:  list[tuple[int, int, float]] = []
        test_ground_truth: dict[str, set[str]] = {}

        for user_idx, item_set in self.user_items.items():
            user_id = self.idx2user[user_idx]
            items = sorted(item_set)  # deterministic before shuffling
            rng.shuffle(items)
            n = len(items)

            if n < 3:
                train.extend(
                    (user_idx, it, self._score_lookup[(user_idx, it)])
                    for it in items
                )
                continue

            n_test = max(1, int(n * test_frac))
            n_val  = max(1, int(n * val_frac))

            for it in items[:n_test]:
                test.append((user_idx, it, self._score_lookup[(user_idx, it)]))
                test_ground_truth.setdefault(user_id, set()).add(self.idx2item[it])

            for it in items[n_test: n_test + n_val]:
                val.append((user_idx, it, self._score_lookup[(user_idx, it)]))

            for it in items[n_test + n_val:]:
                train.append((user_idx, it, self._score_lookup[(user_idx, it)]))

        logger.info(
            "split_done train=%d val=%d test=%d test_users=%d",
            len(train), len(val), len(test), len(test_ground_truth),
        )
        return train, val, test, test_ground_truth


# ---------------------------------------------------------------------------
# PyTorch Dataset
# ---------------------------------------------------------------------------

class NCFDataset(Dataset):
    """
    PyTorch Dataset for implicit-feedback MF training.

    Each positive interaction generates n_negatives random negative samples.
    Labels: 1.0 for positive, 0.0 for negative.

    Negative sampling rejects known positives (from positive_set) to avoid
    false negatives. For very dense catalogues this may loop; with realistic
    sparsity (< 1% density) rejection rate is negligible.
    """

    def __init__(
        self,
        interactions: list[tuple[int, int, float]],
        n_items: int,
        positive_set: set[tuple[int, int]],
        n_negatives: int = 4,
        seed: int = 42,
    ) -> None:
        self.rng = np.random.default_rng(seed)
        users, items, labels = [], [], []

        for u, it, _ in interactions:
            # Positive sample
            users.append(u)
            items.append(it)
            labels.append(1.0)

            # Negative samples
            for _ in range(n_negatives):
                neg = int(self.rng.integers(0, n_items))
                while (u, neg) in positive_set:
                    neg = int(self.rng.integers(0, n_items))
                users.append(u)
                items.append(neg)
                labels.append(0.0)

        self._users  = users
        self._items  = items
        self._labels = labels

    def __len__(self) -> int:
        return len(self._labels)

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        return (
            torch.tensor(self._users[idx],  dtype=torch.long),
            torch.tensor(self._items[idx],  dtype=torch.long),
            torch.tensor(self._labels[idx], dtype=torch.float32),
        )


def build_dataloaders(
    matrix: InteractionMatrix,
    train_interactions: list[tuple[int, int, float]],
    val_interactions:   list[tuple[int, int, float]],
    test_interactions:  list[tuple[int, int, float]],
    batch_size: int = 1024,
    n_negatives: int = 4,
    seed: int = 42,
) -> tuple[DataLoader, DataLoader, DataLoader]:
    """
    Build train/val/test DataLoaders from pre-split interaction lists.

    positive_set is derived from the full matrix so that negative sampling
    never surfaces an item the user has actually interacted with, even if
    that interaction landed in a different split.
    """
    positive_set = {(u, it) for u, it, _ in matrix.interactions}

    train_ds = NCFDataset(train_interactions, matrix.n_items, positive_set, n_negatives, seed)
    val_ds   = NCFDataset(val_interactions,   matrix.n_items, positive_set, n_negatives=1, seed=seed)
    test_ds  = NCFDataset(test_interactions,  matrix.n_items, positive_set, n_negatives=1, seed=seed)

    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True,  num_workers=0)
    val_loader   = DataLoader(val_ds,   batch_size=batch_size, shuffle=False, num_workers=0)
    test_loader  = DataLoader(test_ds,  batch_size=batch_size, shuffle=False, num_workers=0)

    return train_loader, val_loader, test_loader
