"""
stream-processor/app/processor.py

Event processing logic.

Responsibility: decide what a given event means in terms of feature updates,
log it for observability, and delegate storage to the feature store.

This module is intentionally free of Kafka and storage code so it can be
unit-tested with a mock feature store, independent of any infrastructure.

Design note:
  Per-user ordering is guaranteed upstream — the event producer uses user_id
  as the Kafka partition key, so all events for a given user arrive at this
  consumer in causal order. No additional ordering logic is needed here.
"""

import logging

from shared.constants import EVENT_WEIGHTS
from shared.schemas import UserEvent
from app.feature_store import UserFeatureStore

logger = logging.getLogger(__name__)


class EventProcessor:
    """
    Translates a UserEvent into feature store updates.

    Receives a UserFeatureStore via constructor injection so storage
    is swappable without touching this class (useful for testing and
    for adding a second store later, e.g. a columnar feature store).
    """

    def __init__(self, feature_store: UserFeatureStore) -> None:
        self._store = feature_store

    def process(self, event: UserEvent) -> None:
        """
        Process one event: log it and update user feature state.

        Called once per consumed Kafka message in partition (arrival) order.
        Exceptions from the feature store propagate to the caller so the
        consumer loop can decide whether to skip or retry.
        """
        weight = EVENT_WEIGHTS.get(event.event_type.value, 0.0)

        logger.info(
            "processing event_type=%s user_id=%s item_id=%s weight=%.1f",
            event.event_type.value,
            event.user_id,
            event.item_id or "none",
            weight,
        )

        self._store.update(event)
