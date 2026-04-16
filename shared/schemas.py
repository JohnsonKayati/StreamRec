"""
shared/schemas.py

Canonical Pydantic schemas shared across all StreamRec services.
These are the data contract between the event producer, stream processor,
training pipeline, and inference service. Changes here are breaking changes
for every downstream consumer — treat with care.

Versioning policy:
  - schema_version on EventEnvelope is a Literal — consumers that receive
    an unrecognized version will fail fast rather than silently misparse.
  - When a breaking field change is needed, bump to "2.0" and run both
    versions in parallel during the migration window.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utcnow() -> datetime:
    """Return the current time as a timezone-aware UTC datetime.

    Replaces the deprecated datetime.utcnow() which returns a naive datetime,
    causing silent timezone bugs when values hit PostgreSQL TIMESTAMPTZ columns
    or are compared across services.
    """
    return datetime.now(timezone.utc)


# Reusable type alias so user_id constraints are defined exactly once
# and shared between UserEvent and RecommendationRequest.
UserId = Annotated[str, Field(min_length=1, max_length=64)]

# Events that semantically require an item in an e-commerce recommender.
# SEARCH is the only event type that is purely non-item (a free-text query).
# RATING is kept here because in this system ratings are always product ratings.
# If seller/store ratings are added later, relax this set and handle in the validator.
_ITEM_REQUIRED_EVENT_TYPES: frozenset[str] = frozenset({
    "product_view",
    "add_to_cart",
    "remove_from_cart",
    "purchase",
    "rating",
})


# ---------------------------------------------------------------------------
# Event types
# ---------------------------------------------------------------------------

class EventType(str, Enum):
    """
    Supported behavioral event types.

    str base class means EventType.PRODUCT_VIEW == "product_view" is True,
    which keeps JSON serialization and dict lookups clean without extra
    .value calls throughout the codebase.
    """
    PRODUCT_VIEW    = "product_view"
    SEARCH          = "search"
    ADD_TO_CART     = "add_to_cart"
    REMOVE_FROM_CART = "remove_from_cart"
    PURCHASE        = "purchase"
    RATING          = "rating"


# ---------------------------------------------------------------------------
# Core event schema
# ---------------------------------------------------------------------------

class UserEvent(BaseModel):
    """
    A single behavioral event emitted by a user on the platform.

    This is the primary unit of data flowing through Kafka. It is frozen
    (immutable) because events are append-only facts — no service should
    mutate an event after it has been produced.

    Downstream impact of frozen=True:
      - stream-processor and training code must read fields, not assign them.
      - If you need to enrich an event, produce a new derived event type
        instead of patching this one.
    """

    model_config = ConfigDict(
        frozen=True,
        json_schema_extra={
            "example": {
                "user_id": "user_042",
                "event_type": "product_view",
                "item_id": "item_199",
                "session_id": "sess_abc123",
            }
        },
    )

    event_id:   UUID      = Field(default_factory=uuid4, description="Unique event identifier (UUID v4)")
    user_id:    UserId    = Field(..., description="Platform user ID")
    event_type: EventType = Field(..., description="Behavioral signal type")
    item_id:    str | None = Field(None,  min_length=1, max_length=128, description="Product SKU; required for all non-search events")
    session_id: str | None = Field(None,  max_length=128, description="Browser or app session ID for session-aware models")
    query:      str | None = Field(None,  max_length=512, description="Raw search query text (search events only)")
    rating:     float | None = Field(None, ge=1.0, le=5.0, description="Explicit product rating on a 1–5 scale")
    metadata:   dict[str, Any] = Field(default_factory=dict, description="Arbitrary extra context (page, device, A/B variant, etc.)")
    timestamp:  datetime = Field(default_factory=_utcnow, description="Event time in UTC; always timezone-aware")

    @model_validator(mode="after")
    def _validate_item_id(self) -> "UserEvent":
        """
        Enforce item_id presence for event types that require a product context.

        Uses mode="after" so all fields are already coerced and available as
        typed attributes — avoids the Pydantic v2 pitfall where field_validator
        runs before sibling fields are populated in info.data.
        """
        if self.event_type.value in _ITEM_REQUIRED_EVENT_TYPES and self.item_id is None:
            raise ValueError(
                f"item_id is required for event_type='{self.event_type.value}'. "
                "Only 'search' events may omit item_id."
            )
        return self


# ---------------------------------------------------------------------------
# Kafka message envelope
# ---------------------------------------------------------------------------

class EventEnvelope(BaseModel):
    """
    Wrapper serialized into every Kafka message on the user-events topic.

    Frozen for the same reason as UserEvent — envelopes are immutable
    once published.

    schema_version is a Literal so Pydantic will reject messages from a
    future schema version at parse time rather than silently deserializing
    them with wrong field semantics. When a breaking change is needed,
    add a union type (EventEnvelope_v1 | EventEnvelope_v2) at the consumer.

    producer_id should be set from service config/env at runtime — the
    default is a safe fallback but loses per-instance traceability.
    """

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    event:          UserEvent
    producer_id:    str      = Field(default="event-producer-v1", description="Service instance that produced this message")
    ingested_at:    datetime = Field(default_factory=_utcnow, description="Wall-clock time the envelope was created, UTC")


# ---------------------------------------------------------------------------
# Recommendation API schemas
# ---------------------------------------------------------------------------

class RecommendationRequest(BaseModel):
    """
    Query parameters for the /recommendations/{user_id} endpoint.

    validate_assignment=True means if the inference service modifies a field
    (e.g. clamping k) after construction, the constraint is re-checked.
    """

    model_config = ConfigDict(validate_assignment=True)

    # user_id uses the same UserId alias as UserEvent — one definition, consistent everywhere
    user_id:      UserId = Field(..., description="User to generate recommendations for")
    k:            int    = Field(default=10, ge=1, le=100, description="Number of items to return")
    exclude_seen: bool   = Field(default=True, description="Filter out items the user has already interacted with")
    context:      dict[str, Any] = Field(default_factory=dict, description="Optional serving context (page type, device, A/B variant)")


class RecommendedItem(BaseModel):
    """
    A single item in a recommendation list.

    score is an unbounded float — models are not required to normalize
    their outputs to [0, 1] before the schema layer. The inference service
    is responsible for normalizing before returning a response. Keeping the
    schema loose avoids validation errors during model development when
    raw logits or dot products are inspected.

    Frozen because a ranked result list should not be mutated after scoring.
    """

    model_config = ConfigDict(frozen=True)

    item_id:       str   = Field(..., description="Product SKU")
    score:         float = Field(..., description="Raw model score; not assumed to be normalized")
    rank:          int   = Field(..., ge=1, description="1-based rank in the result list")
    model_version: str   = Field(default="unknown", description="Model artifact version that produced this score")


class RecommendationResponse(BaseModel):
    """
    Full API response for a recommendation request.

    request_id ties the response back to the originating request in logs
    and traces — essential for debugging cache misses, latency spikes, and
    model version rollouts in production.
    """

    model_config = ConfigDict(validate_assignment=True)

    request_id:       UUID   = Field(default_factory=uuid4, description="Correlates this response to its request in distributed traces")
    user_id:          str    = Field(..., description="User these recommendations were generated for")
    recommendations:  list[RecommendedItem]
    model_name:       str    = Field(..., description="Logical model name (e.g. 'neural_cf', 'popularity')")
    served_from_cache: bool  = Field(default=False)
    latency_ms:       float | None = Field(default=None, ge=0.0, description="End-to-end serving latency in milliseconds")
    generated_at:     datetime = Field(default_factory=_utcnow)


# ---------------------------------------------------------------------------
# Item catalog schema
# ---------------------------------------------------------------------------

class ItemMetadata(BaseModel):
    """
    Product catalog record.

    price uses Decimal instead of float. Floating-point arithmetic on
    currency values introduces rounding errors (e.g. 0.1 + 0.2 != 0.3)
    that compound in ranking and discount logic. Decimal is exact.

    Downstream impact: PostgreSQL NUMERIC maps cleanly to Python Decimal.
    JSON serialization requires mode='json' on model_dump() or a custom
    encoder — both are already handled by Pydantic v2's default behavior.
    """

    model_config = ConfigDict(validate_assignment=True)

    item_id:      str            = Field(..., min_length=1, max_length=128)
    title:        str            = Field(..., min_length=1, max_length=512)
    category:     str            = Field(..., min_length=1, max_length=128)
    subcategory:  str | None     = Field(default=None, max_length=128)
    price:        Decimal        = Field(..., gt=Decimal("0"), decimal_places=2, description="Item price; Decimal avoids float rounding errors")
    avg_rating:   float | None   = Field(default=None, ge=1.0, le=5.0)
    review_count: int            = Field(default=0, ge=0)
    tags:         list[str]      = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Public API surface
# ---------------------------------------------------------------------------

__all__ = [
    "EventType",
    "UserEvent",
    "EventEnvelope",
    "RecommendationRequest",
    "RecommendedItem",
    "RecommendationResponse",
    "ItemMetadata",
    "UserId",
]
