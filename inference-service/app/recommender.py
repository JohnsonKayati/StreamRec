"""
inference-service/app/recommender.py

Recommendation logic for both loaded model types.

Responsibilities:
  MFRecommender         — score all items for a user with the MF model,
                          mask seen items, return top-K (item_id, score) pairs.
  PopularityRecommender — walk the pre-sorted popularity list, skip seen items,
                          return top-K (item_id, score) pairs.

Both classes accept a `seen_items` set so the caller (the route handler)
controls where the seen set comes from — Redis at serving time — rather than
baking it into the model.  This keeps the recommenders stateless and testable.

Return convention:
  recommend() returns list[tuple[item_id, score]] ordered best-first.
  MFRecommender.recommend() returns None when the user is unknown (cold-start
  signal). Caller must check for None and fall back to PopularityRecommender.
"""

import logging

import torch

from app.models import MFBundle, PopularityBundle

logger = logging.getLogger(__name__)


class MFRecommender:
    """
    Serves top-K recommendations using the trained MF model.

    All n_items items are scored in a single forward pass (one batched
    matrix multiply + sigmoid). For catalogues up to ~500k items this is
    fast enough on CPU (~50ms). For larger catalogues, pre-compute
    approximate nearest neighbours (e.g. FAISS) and index them offline.
    """

    def __init__(self, bundle: MFBundle) -> None:
        self._bundle = bundle
        # Pre-compute item_id → index mapping for O(1) seen-item masking.
        # idx2item is int→str; invert once here rather than on every request.
        self._item2idx: dict[str, int] = {v: k for k, v in bundle.idx2item.items()}

    @torch.no_grad()
    def recommend(
        self,
        user_id: str,
        k: int,
        seen_items: set[str],
    ) -> list[tuple[str, float]] | None:
        """
        Score all items for user_id, mask seen items, return top-K.

        Returns:
            list of (item_id, score) ordered best-first, or
            None if user_id is not in the training index (cold start).
        """
        bundle   = self._bundle
        user_idx = bundle.user2idx.get(user_id)
        if user_idx is None:
            logger.debug("mf_cold_start user_id=%s", user_id)
            return None

        device = bundle.device
        n      = bundle.n_items

        # Score every item in one forward pass
        user_t = torch.full((n,), user_idx, dtype=torch.long, device=device)
        item_t = torch.arange(n,            dtype=torch.long, device=device)
        scores = bundle.model(user_t, item_t).cpu()   # (n_items,)

        # Zero-out seen items so they cannot appear in the top-K
        for item_id in seen_items:
            idx = self._item2idx.get(item_id)
            if idx is not None:
                scores[idx] = -1.0

        top_k_vals, top_k_idx = scores.topk(min(k, n))
        results = [
            (bundle.idx2item[int(i)], float(v))
            for i, v in zip(top_k_idx.tolist(), top_k_vals.tolist())
            if int(i) in bundle.idx2item
        ]

        logger.debug(
            "mf_recommend user_id=%s k=%d returned=%d", user_id, k, len(results)
        )
        return results


class PopularityRecommender:
    """
    Serves globally popular items filtered by the user's seen set.

    Scores are normalized to [0, 1] against the most popular item's raw score
    so the magnitude is meaningful and comparable across model versions.
    """

    def __init__(self, bundle: PopularityBundle) -> None:
        self._bundle    = bundle
        self._max_score = max(bundle.item_scores.values()) if bundle.item_scores else 1.0

    def recommend(
        self,
        k: int,
        seen_items: set[str],
    ) -> list[tuple[str, float]]:
        """
        Return top-K globally popular items not already seen by the user.

        Iterates the pre-sorted ranked_items list and stops as soon as k
        unseen items are found — O(1) amortized for sparse seen sets.
        """
        results: list[tuple[str, float]] = []

        for item_id in self._bundle.ranked_items:
            if item_id in seen_items:
                continue
            score = round(self._bundle.item_scores[item_id] / self._max_score, 6)
            results.append((item_id, score))
            if len(results) == k:
                break

        logger.debug("popularity_recommend k=%d returned=%d", k, len(results))
        return results
