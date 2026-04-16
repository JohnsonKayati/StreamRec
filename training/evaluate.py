"""
training/evaluate.py

Offline ranking metrics for recommender system evaluation.

Metrics:
  Precision@K  — fraction of top-K recommendations that are relevant
  Recall@K     — fraction of relevant items that appear in the top-K
  NDCG@K       — position-weighted ranking quality (standard IR metric)

All three are macro-averaged across users. Users with an empty ground-truth
set are skipped — they cannot contribute a meaningful signal.

Interface:
  evaluate_recommender() accepts a callable (user_id, k) -> list[item_id]
  so it works identically for PopularityRecommender and the MF wrapper
  without requiring a shared base class.
"""

import logging
import math
from collections.abc import Callable

logger = logging.getLogger(__name__)


def precision_at_k(recommended: list[str], relevant: set[str], k: int) -> float:
    """Fraction of the top-K that are relevant. Range: [0, 1]."""
    hits = sum(1 for r in recommended[:k] if r in relevant)
    return hits / k


def recall_at_k(recommended: list[str], relevant: set[str], k: int) -> float:
    """Fraction of relevant items found in the top-K. Range: [0, 1]."""
    if not relevant:
        return 0.0
    hits = sum(1 for r in recommended[:k] if r in relevant)
    return hits / len(relevant)


def ndcg_at_k(recommended: list[str], relevant: set[str], k: int) -> float:
    """
    Normalized Discounted Cumulative Gain at K.

    DCG  = Σ_i  rel(i) / log2(i + 2)     [i is 0-based rank]
    IDCG = DCG of the ideal ranking (all relevant items at the top)
    NDCG = DCG / IDCG

    Binary relevance: rel(i) = 1 if item is in relevant set, else 0.
    Range: [0, 1].
    """
    dcg = sum(
        1.0 / math.log2(rank + 2)
        for rank, item in enumerate(recommended[:k])
        if item in relevant
    )
    # IDCG: place min(|relevant|, k) hits at ranks 0, 1, ..., min-1
    n_ideal = min(len(relevant), k)
    idcg = sum(1.0 / math.log2(rank + 2) for rank in range(n_ideal))
    return dcg / idcg if idcg > 0.0 else 0.0


def evaluate_recommender(
    recommend_fn: Callable[[str, int], list[str]],
    ground_truth: dict[str, set[str]],
    k: int = 10,
) -> dict[str, float]:
    """
    Macro-average Precision@K, Recall@K, NDCG@K over all evaluable users.

    Args:
        recommend_fn:   Callable (user_id, k) -> list[item_id], best-first order.
        ground_truth:   {user_id: {held-out item_ids}} — the test set.
        k:              Ranking cut-off.

    Returns:
        {"precision": float, "recall": float, "ndcg": float, "n_users": int}
    """
    precisions: list[float] = []
    recalls:    list[float] = []
    ndcgs:      list[float] = []

    for user_id, relevant in ground_truth.items():
        if not relevant:
            continue
        recs = recommend_fn(user_id, k)
        precisions.append(precision_at_k(recs, relevant, k))
        recalls.append(recall_at_k(recs, relevant, k))
        ndcgs.append(ndcg_at_k(recs, relevant, k))

    n = len(precisions)
    if n == 0:
        logger.warning("evaluate_recommender: no evaluable users in ground_truth")
        return {"precision": 0.0, "recall": 0.0, "ndcg": 0.0, "n_users": 0}

    metrics = {
        "precision": sum(precisions) / n,
        "recall":    sum(recalls) / n,
        "ndcg":      sum(ndcgs) / n,
        "n_users":   n,
    }
    logger.info(
        "eval k=%d precision=%.4f recall=%.4f ndcg=%.4f users=%d",
        k, metrics["precision"], metrics["recall"], metrics["ndcg"], n,
    )
    return metrics
