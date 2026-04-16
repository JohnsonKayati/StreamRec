"""
stream-processor/app/feature_store.py

Dual-write feature store: Redis (hot path) and PostgreSQL (cold path).

Redis key schema
----------------
  user:{user_id}:recent_items   ZSET    item_id → unix_timestamp (float)
    Last REDIS_RECENT_ITEMS_MAX interacted items, ordered by event time.
    Read by the inference service to build the user's session context.
    Also used directly as input to sequence-aware models (e.g. GRU4Rec).

  user:{user_id}:event_counts   HASH    event_type → cumulative integer count
    Encodes per-user:
      view_count          = HGET ... product_view
      add_to_cart_count   = HGET ... add_to_cart
      purchase_count      = HGET ... purchase
      search_count        = HGET ... search
    Used as user-side features in collaborative filtering and neural CF.

  user:{user_id}:last_event_ts  STRING  ISO-8601 UTC datetime
    Timestamp of the most recently processed event for this user.
    Used as a recency feature at inference time (e.g. "active in last hour").

  item:popularity               ZSET    item_id → cumulative weighted score
    Global popularity signal across all users. Backing store for the
    popularity baseline model and for cold-start fallback in neural CF.

PostgreSQL tables
-----------------
  events                 — append-only raw event log, primary training data source.
  user_item_interactions — running aggregated interaction matrix.
                           Consumed directly by collaborative filtering training.
  (both defined in infra/postgres/init.sql)

AWS equivalent
--------------
  Redis  → Amazon ElastiCache for Redis (same API)
  Postgres → Amazon RDS PostgreSQL or Aurora
"""

import json
import logging

import psycopg2
import psycopg2.extensions
import redis as redis_lib

from shared.constants import (
    EVENT_WEIGHTS,
    REDIS_ITEM_POPULARITY,
    REDIS_RECENT_ITEMS_MAX,
    REDIS_USER_EVENT_COUNTS,
    REDIS_USER_RECENT_ITEMS,
)
from shared.schemas import UserEvent

logger = logging.getLogger(__name__)

# Per-user last-event timestamp key.
# When the inference service needs this, move it to shared/constants.py.
_REDIS_USER_LAST_EVENT_TS = "user:{user_id}:last_event_ts"


class UserFeatureStore:
    """
    Writes per-user feature state to Redis (hot) and PostgreSQL (cold).

    Both writes happen synchronously in process(). Redis failure is logged
    but does not abort the Postgres write — a dropped Redis update is
    recoverable (stale cache); a dropped Postgres write is not (lost training data).

    Postgres uses a lazy single connection with automatic reconnect on failure.
    This is appropriate for a single-threaded consumer process. Use a pool
    if the processor is ever made multi-threaded.
    """

    def __init__(self, redis_url: str, database_url: str) -> None:
        self._redis = redis_lib.from_url(redis_url, decode_responses=True)
        self._database_url = database_url
        self._pg_conn: psycopg2.extensions.connection | None = None
        logger.info("feature_store_initialized")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update(self, event: UserEvent) -> None:
        """Persist feature updates for one event. Called once per message."""
        self._update_redis(event)
        self._write_postgres(event)

    def close(self) -> None:
        """Release connections cleanly on service shutdown."""
        try:
            self._redis.close()
        except Exception as exc:
            logger.warning("redis_close_error error=%s", exc)

        if self._pg_conn is not None and not self._pg_conn.closed:
            try:
                self._pg_conn.close()
            except Exception as exc:
                logger.warning("postgres_close_error error=%s", exc)

        logger.info("feature_store_closed")

    # ------------------------------------------------------------------
    # Redis — hot feature updates
    # ------------------------------------------------------------------

    def _update_redis(self, event: UserEvent) -> None:
        """
        Write all hot features for one event in a single pipelined round trip.

        pipeline(transaction=False): batches commands without MULTI/EXEC.
        We don't need cross-key atomicity — each key is owned by one user
        and the consumer processes that user's events sequentially.
        """
        pipe = self._redis.pipeline(transaction=False)
        ts = event.timestamp.timestamp()
        weight = EVENT_WEIGHTS.get(event.event_type.value, 0.0)

        # 1. Recent items — ZSET keyed by unix timestamp preserves arrival order.
        #    Enables session context reconstruction at inference time.
        if event.item_id is not None:
            recent_key = REDIS_USER_RECENT_ITEMS.format(user_id=event.user_id)
            pipe.zadd(recent_key, {event.item_id: ts})
            # Keep only the N most recent items. zremrangebyrank uses 0-based
            # rank from the lowest score, so -(N+1) is the last element to
            # remove: ranks 0 … -(N+1) leaves ranks -N … -1 (the N highest).
            pipe.zremrangebyrank(recent_key, 0, -(REDIS_RECENT_ITEMS_MAX + 1))

        # 2. Event type counters — HASH gives O(1) read of any single counter.
        counts_key = REDIS_USER_EVENT_COUNTS.format(user_id=event.user_id)
        pipe.hincrby(counts_key, event.event_type.value, 1)

        # 3. Last event timestamp — recency feature for inference.
        ts_key = _REDIS_USER_LAST_EVENT_TS.format(user_id=event.user_id)
        pipe.set(ts_key, event.timestamp.isoformat())

        # 4. Global item popularity — positive-weight events only.
        if event.item_id is not None and weight > 0:
            pipe.zincrby(REDIS_ITEM_POPULARITY, weight, event.item_id)

        try:
            pipe.execute()
        except redis_lib.RedisError as exc:
            logger.error(
                "redis_update_failed user_id=%s event_type=%s error=%s",
                event.user_id, event.event_type.value, exc,
            )

    # ------------------------------------------------------------------
    # PostgreSQL — cold storage writes
    # ------------------------------------------------------------------

    def _get_pg_conn(self) -> psycopg2.extensions.connection:
        """Return an open connection, reconnecting if the previous one dropped."""
        if self._pg_conn is None or self._pg_conn.closed:
            self._pg_conn = psycopg2.connect(self._database_url)
            logger.info("postgres_connected")
        return self._pg_conn

    def _write_postgres(self, event: UserEvent) -> None:
        """
        Write raw event and upsert the interaction matrix row.

        events insert uses ON CONFLICT (event_id) DO NOTHING so consumer
        restarts after a crash are fully idempotent — replayed messages
        produce no duplicate rows.

        interaction upsert calls the SQL function defined in init.sql which
        increments per-type counters and the weighted interaction score.
        """
        conn = self._get_pg_conn()
        try:
            with conn.cursor() as cur:
                # Ensure the user row exists before the FK reference in events.
                cur.execute(
                    "INSERT INTO users (user_id) VALUES (%s) ON CONFLICT DO NOTHING",
                    (event.user_id,),
                )

                # Append the raw event. Idempotent on replay.
                cur.execute(
                    """
                    INSERT INTO events
                        (event_id, user_id, event_type, item_id,
                         session_id, query, rating, metadata, timestamp)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                    ON CONFLICT (event_id) DO NOTHING
                    """,
                    (
                        str(event.event_id),
                        event.user_id,
                        event.event_type.value,
                        event.item_id,
                        event.session_id,
                        event.query,
                        float(event.rating) if event.rating is not None else None,
                        json.dumps(event.metadata),   # safe serialization — not str()
                        event.timestamp,
                    ),
                )

                # Update the interaction matrix only when an item and a
                # non-zero weight are present.
                if event.item_id is not None:
                    weight = EVENT_WEIGHTS.get(event.event_type.value, 0.0)
                    if weight != 0.0:
                        cur.execute(
                            "SELECT upsert_interaction(%s, %s, %s, %s)",
                            (event.user_id, event.item_id, weight, event.event_type.value),
                        )

            conn.commit()

        except psycopg2.Error as exc:
            logger.error(
                "postgres_write_failed event_id=%s error=%s",
                event.event_id, exc,
            )
            try:
                conn.rollback()
            except Exception:
                pass
            # Discard the connection so _get_pg_conn() reconnects on next call.
            self._pg_conn = None
