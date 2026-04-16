"""
training/models/popularity.py

Popularity-based recommender — the production baseline.

Why it matters:
  - Establishes a non-trivial floor before any ML model is evaluated.
  - Often beats personalized models for cold-start users.
  - NDCG@K from this model is the bar every MF/NCF result must clear.

Logic:
  Score each item by the sum of its interaction scores across all users.
  Interaction scores are pre-aggregated by load_interactions() using
  EVENT_WEIGHTS, so no weight table is needed here.
  Personalize by filtering out items the user has already seen.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class PopularityRecommender:
    """
    Non-personalized popularity recommender.

    fit() accepts the same list[RawInteraction] produced by load_interactions(),
    so no separate weight table is needed — scores are already aggregated.

    Attributes:
        item_scores:    item_id → total interaction score across all users
        user_seen:      user_id → set of item_ids the user has interacted with
        _ranked_items:  pre-sorted item_ids for O(1) top-K serving
    """

    def __init__(self) -> None:
        self.item_scores: dict[str, float] = {}
        self.user_seen:   dict[str, set[str]] = {}
        self._ranked_items: list[str] = []
        self.is_fitted = False

    def fit(self, interactions: list) -> "PopularityRecommender":
        """
        Fit on pre-aggregated RawInteraction objects.

        Args:
            interactions: list[RawInteraction] from load_interactions()
        """
        scores: dict[str, float] = {}
        user_seen: dict[str, set[str]] = {}

        for ia in interactions:
            scores[ia.item_id] = scores.get(ia.item_id, 0.0) + ia.score
            user_seen.setdefault(ia.user_id, set()).add(ia.item_id)

        self.item_scores   = scores
        self.user_seen     = user_seen
        self._ranked_items = sorted(scores, key=scores.__getitem__, reverse=True)
        self.is_fitted     = True

        logger.info(
            "popularity_fitted items=%d users=%d",
            len(self.item_scores), len(self.user_seen),
        )
        return self

    def recommend(
        self,
        user_id: str,
        k: int = 10,
        exclude_seen: bool = True,
    ) -> list[tuple[str, float]]:
        """
        Return top-K (item_id, score) tuples, scores normalized to [0, 1].

        Args:
            user_id:      Target user.
            k:            Number of recommendations.
            exclude_seen: Filter out items the user has already interacted with.
        """
        if not self.is_fitted:
            raise RuntimeError("Call fit() before recommend().")

        seen = self.user_seen.get(user_id, set()) if exclude_seen else set()
        max_score = max(self.item_scores.values()) if self.item_scores else 1.0
        results: list[tuple[str, float]] = []

        for item_id in self._ranked_items:
            if item_id in seen:
                continue
            score = round(self.item_scores[item_id] / max_score, 6)
            results.append((item_id, score))
            if len(results) == k:
                break

        return results

    # ------------------------------------------------------------------
    # Persistence — JSON instead of pickle for portability and safety
    # ------------------------------------------------------------------

    def save(self, path: Path) -> None:
        """Save model state to <path>/popularity_model.json."""
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        payload = {
            "item_scores": self.item_scores,
            # sets are not JSON-serializable; convert to sorted lists
            "user_seen": {u: sorted(items) for u, items in self.user_seen.items()},
        }
        with open(path / "popularity_model.json", "w") as f:
            json.dump(payload, f)
        logger.info("popularity_saved path=%s", path / "popularity_model.json")

    @classmethod
    def load(cls, path: Path) -> "PopularityRecommender":
        """Load model state from <path>/popularity_model.json."""
        path = Path(path)
        with open(path / "popularity_model.json") as f:
            payload = json.load(f)

        m = cls()
        m.item_scores   = payload["item_scores"]
        m.user_seen     = {u: set(items) for u, items in payload["user_seen"].items()}
        m._ranked_items = sorted(m.item_scores, key=m.item_scores.__getitem__, reverse=True)
        m.is_fitted     = True
        return m
