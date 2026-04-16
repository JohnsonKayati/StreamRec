"""
inference-service/app/main.py

FastAPI inference service: loads trained model artifacts at startup and serves
top-K recommendations via a single GET endpoint.

Endpoints:
  GET /recommendations   — primary serving endpoint
  GET /health            — liveness / readiness probe
  GET /metrics           — Prometheus scrape endpoint

Request flow:
  1. Check Redis cache (recs:{user_id}:k{k}).  Cache hit → return immediately.
  2. Fetch user's seen items from Redis (user:{user_id}:recent_items ZSET).
  3. Try MF recommender.  Cold-start (user unknown) → fall back to popularity.
  4. Build RecommendationResponse from shared schema.
  5. Write to Redis cache with TTL.

Cold-start handling:
  User not in MF index → PopularityRecommender (still filtered by seen items).
  Neither model loaded  → HTTP 503.

AWS equivalent:
  ECS Fargate task behind an ALB target group, or Lambda with Function URL
  for sub-100ms p99 latency. Redis → ElastiCache for Redis (same API).
  Model artifacts loaded from EFS mount or S3 at container start.
"""

import json
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

import redis as redis_lib
from fastapi import FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import Counter, Histogram, make_asgi_app

from app.config import get_settings
from app.models import load_mf, load_popularity
from app.recommender import MFRecommender, PopularityRecommender
from shared.constants import REDIS_USER_RECENT_ITEMS, REDIS_USER_RECS_CACHE
from shared.logging_config import configure_logging, get_logger
from shared.schemas import RecommendedItem, RecommendationResponse

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

_settings = get_settings()
configure_logging(_settings.service_name, _settings.log_level)
logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Prometheus metrics
# ---------------------------------------------------------------------------

RECS_SERVED = Counter(
    "streamrec_recommendations_served_total",
    "Total recommendation requests served",
    ["model_name", "cache_hit"],
)
RECS_LATENCY = Histogram(
    "streamrec_recommendation_latency_seconds",
    "End-to-end recommendation serving latency",
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
)
COLD_START_TOTAL = Counter(
    "streamrec_cold_start_total",
    "Requests where user was unknown to MF model (fell back to popularity)",
)

# ---------------------------------------------------------------------------
# Service state — set in lifespan, read in route handlers
# ---------------------------------------------------------------------------

_mf_rec:  MFRecommender | None         = None
_pop_rec: PopularityRecommender | None = None
_redis:   redis_lib.Redis | None        = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _mf_rec, _pop_rec, _redis
    settings     = get_settings()
    artifact_dir = Path(settings.artifact_dir)

    logger.info("inference_service_starting artifact_dir=%s", artifact_dir)

    # Load models — each is optional; service degrades if artifacts are absent
    mf_bundle:  MFBundle | None         = load_mf(artifact_dir)
    pop_bundle: PopularityBundle | None = load_popularity(artifact_dir)

    _mf_rec  = MFRecommender(mf_bundle)   if mf_bundle  else None
    _pop_rec = PopularityRecommender(pop_bundle) if pop_bundle else None

    if _mf_rec is None and _pop_rec is None:
        logger.error(
            "no_models_loaded — run training/train.py first, "
            "then restart this service pointing artifact_dir at the output"
        )

    # Connect to Redis
    _redis = redis_lib.from_url(settings.redis_url, decode_responses=True)
    try:
        _redis.ping()
        logger.info("redis_connected url=%s", settings.redis_url)
    except redis_lib.RedisError as exc:
        # Redis failure is non-fatal at startup — seen-item lookup and caching
        # are best-effort.  Log clearly and continue.
        logger.warning("redis_unavailable_at_startup error=%s", exc)

    logger.info(
        "inference_service_ready mf=%s popularity=%s",
        "loaded" if _mf_rec  else "unavailable",
        "loaded" if _pop_rec else "unavailable",
    )

    yield

    if _redis:
        _redis.close()
    logger.info("inference_service_stopped")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="StreamRec — Inference Service",
    description="Serves personalised top-K recommendations from trained MF and popularity models.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.mount("/metrics", make_asgi_app())

# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


def get_models() -> tuple[MFRecommender | None, PopularityRecommender | None]:
    return _mf_rec, _pop_rec


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_seen_items(user_id: str) -> set[str]:
    """
    Fetch the user's recently seen items from Redis (recent_items ZSET).

    Returns an empty set on any Redis error — graceful degradation means
    we may occasionally recommend an already-seen item rather than failing.
    """
    if _redis is None:
        return set()
    key = REDIS_USER_RECENT_ITEMS.format(user_id=user_id)
    try:
        return set(_redis.zrange(key, 0, -1))
    except redis_lib.RedisError as exc:
        logger.warning("redis_seen_items_failed user_id=%s error=%s", user_id, exc)
        return set()


def _read_cache(cache_key: str) -> dict | None:
    """Return parsed cached payload or None on miss / Redis error."""
    if _redis is None:
        return None
    try:
        raw = _redis.get(cache_key)
        return json.loads(raw) if raw else None
    except (redis_lib.RedisError, json.JSONDecodeError) as exc:
        logger.warning("cache_read_failed key=%s error=%s", cache_key, exc)
        return None


def _write_cache(cache_key: str, payload: dict, ttl_s: int) -> None:
    """Write payload to Redis cache, silently ignoring errors."""
    if _redis is None or ttl_s <= 0:
        return
    try:
        _redis.set(cache_key, json.dumps(payload), ex=ttl_s)
    except redis_lib.RedisError as exc:
        logger.warning("cache_write_failed key=%s error=%s", cache_key, exc)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get(
    "/recommendations",
    response_model=RecommendationResponse,
    summary="Get top-K recommendations for a user",
)
async def get_recommendations(
    user_id:      Annotated[str,  Query(min_length=1, max_length=64, description="Target user ID")],
    k:            Annotated[int,  Query(ge=1, le=100, description="Number of items to return")] = 10,
    exclude_seen: Annotated[bool, Query(description="Filter out items the user has already seen")] = True,
) -> RecommendationResponse:
    """
    Return top-K item recommendations for a user.

    - Uses the MF model when the user has a training history.
    - Falls back to the global popularity baseline for cold-start users.
    - Responses are cached in Redis for `recs_cache_ttl_s` seconds.
    """
    settings = get_settings()
    start    = time.perf_counter()

    mf_rec, pop_rec = get_models()
    if mf_rec is None and pop_rec is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No recommendation models are loaded. The service is starting or training has not run.",
        )

    # ------------------------------------------------------------------
    # Cache check (only when exclude_seen=True to keep key space simple)
    # ------------------------------------------------------------------
    cache_key = REDIS_USER_RECS_CACHE.format(user_id=user_id, k=k)
    if exclude_seen:
        cached = _read_cache(cache_key)
        if cached is not None:
            elapsed_ms = (time.perf_counter() - start) * 1000
            RECS_SERVED.labels(model_name=cached["model_name"], cache_hit="true").inc()
            logger.debug("cache_hit user_id=%s k=%d", user_id, k)
            return RecommendationResponse(
                user_id=user_id,
                recommendations=cached["recommendations"],
                model_name=cached["model_name"],
                served_from_cache=True,
                latency_ms=round(elapsed_ms, 2),
            )

    # ------------------------------------------------------------------
    # Seen items — fetch from Redis for real-time filtering
    # ------------------------------------------------------------------
    seen_items: set[str] = _get_seen_items(user_id) if exclude_seen else set()

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------
    model_name: str
    raw_results: list[tuple[str, float]]

    if mf_rec is not None:
        mf_result = mf_rec.recommend(user_id=user_id, k=k, seen_items=seen_items)
        if mf_result is not None:
            raw_results = mf_result
            model_name  = "mf"
        else:
            # Cold start — user not in training index; fall back to popularity
            COLD_START_TOTAL.inc()
            logger.info("cold_start_fallback user_id=%s — serving popularity baseline", user_id)
            if pop_rec is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"User '{user_id}' is unknown to the MF model and no popularity fallback is loaded.",
                )
            raw_results = pop_rec.recommend(k=k, seen_items=seen_items)
            model_name  = "popularity"
    else:
        # MF not loaded — serve popularity for all users
        assert pop_rec is not None   # guarded by the 503 check above
        raw_results = pop_rec.recommend(k=k, seen_items=seen_items)
        model_name  = "popularity"

    # ------------------------------------------------------------------
    # Build response
    # ------------------------------------------------------------------
    elapsed_ms = (time.perf_counter() - start) * 1000
    recommendations = [
        RecommendedItem(item_id=item_id, score=score, rank=rank + 1, model_version="v1")
        for rank, (item_id, score) in enumerate(raw_results)
    ]
    response = RecommendationResponse(
        user_id=user_id,
        recommendations=recommendations,
        model_name=model_name,
        served_from_cache=False,
        latency_ms=round(elapsed_ms, 2),
    )

    # ------------------------------------------------------------------
    # Cache write (only for exclude_seen=True responses)
    # ------------------------------------------------------------------
    if exclude_seen:
        _write_cache(
            cache_key,
            {"model_name": model_name, "recommendations": [r.model_dump() for r in recommendations]},
            settings.recs_cache_ttl_s,
        )

    RECS_SERVED.labels(model_name=model_name, cache_hit="false").inc()
    RECS_LATENCY.observe(elapsed_ms / 1000)
    logger.info(
        "recommendations_served user_id=%s k=%d model=%s latency_ms=%.2f",
        user_id, k, model_name, elapsed_ms,
    )
    return response


@app.get("/health", status_code=status.HTTP_200_OK)
async def health() -> dict:
    """
    Liveness and readiness probe.

    Returns 200 if at least one model is loaded.
    Returns 503 if no models are available (service is degraded).
    Redis connectivity is reported but does not affect the status code —
    the service can still serve recommendations without Redis (no caching,
    no seen-item filtering).
    """
    redis_ok = False
    if _redis is not None:
        try:
            _redis.ping()
            redis_ok = True
        except redis_lib.RedisError:
            pass

    checks = {
        "mf_loaded":         _mf_rec  is not None,
        "popularity_loaded": _pop_rec is not None,
        "redis":             redis_ok,
    }
    any_model_loaded = checks["mf_loaded"] or checks["popularity_loaded"]

    if not any_model_loaded:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "degraded", "checks": checks},
        )

    return {"status": "ok", "service": _settings.service_name, "checks": checks}
