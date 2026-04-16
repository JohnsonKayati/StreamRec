"""
event-producer/app/main.py

FastAPI service: accepts user behavioral events over HTTP, validates them
against the shared schema, and publishes them to Kafka.

AWS equivalent:
  API Gateway (HTTP API) → Lambda or ECS task → Kinesis PutRecord

Endpoints:
  POST /events         — ingest a single event
  POST /events/batch   — ingest up to 100 events (for the simulator)
  GET  /health         — liveness / readiness probe
  GET  /metrics        — Prometheus metrics scrape endpoint

The service is stateless: all per-user state lives in Kafka (durable log)
and Redis (hot features, owned by the stream processor). Adding more
replicas of this service behind a load balancer requires no coordination.
"""

import logging
import time
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import Counter, Histogram, make_asgi_app

from app.config import Settings, get_settings
from app.kafka_producer import KafkaEventProducer

# shared/ is on PYTHONPATH (set via PYTHONPATH env var in Dockerfile and .env).
# No sys.path manipulation needed — keeping imports clean and IDE-friendly.
from shared.logging_config import configure_logging, get_logger
from shared.schemas import EventEnvelope, UserEvent

# ---------------------------------------------------------------------------
# Logging — configure at module load so startup messages are structured too.
# get_settings() is cached; this is safe to call here.
# ---------------------------------------------------------------------------

_settings = get_settings()
configure_logging(_settings.service_name, _settings.log_level)
logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Prometheus metrics
# ---------------------------------------------------------------------------

EVENTS_PUBLISHED = Counter(
    "streamrec_events_published_total",
    "Total events successfully published to Kafka",
    ["event_type"],
)
EVENTS_FAILED = Counter(
    "streamrec_events_failed_total",
    "Total events that failed to publish",
    ["event_type"],
)
PUBLISH_LATENCY = Histogram(
    "streamrec_event_publish_latency_seconds",
    "Latency from request receipt to Kafka enqueue",
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5],
)

# ---------------------------------------------------------------------------
# Producer lifecycle — one shared instance per process
# ---------------------------------------------------------------------------

_producer: KafkaEventProducer | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _producer
    logger.info("event_producer_starting")
    _producer = KafkaEventProducer(
        bootstrap_servers=_settings.kafka_bootstrap_servers,
        acks=_settings.kafka_producer_acks,
        retries=_settings.kafka_producer_retries,
        linger_ms=_settings.kafka_producer_linger_ms,
    )
    logger.info("event_producer_ready")
    yield
    if _producer:
        _producer.close()
    logger.info("event_producer_stopped")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="StreamRec — Event Producer",
    description="Accepts user behavioral events and publishes them to Kafka.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Prometheus metrics endpoint — mounted before routes so /metrics is never
# intercepted by application middleware.
app.mount("/metrics", make_asgi_app())

# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


def get_producer() -> KafkaEventProducer:
    if _producer is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Producer not ready. Service may be starting up.",
        )
    return _producer


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.post("/events", status_code=status.HTTP_202_ACCEPTED)
async def ingest_event(
    event: UserEvent,
    settings: Annotated[Settings, Depends(get_settings)],
    producer: Annotated[KafkaEventProducer, Depends(get_producer)],
) -> dict:
    """
    Accept one user behavioral event and publish it to Kafka.

    Validation is handled entirely by the shared UserEvent schema —
    this endpoint adds no additional business logic.

    Partition key: user_id
      All events from the same user land in the same Kafka partition,
      preserving causal ordering for the stream processor's session logic.

    Returns 202 Accepted (not 200 OK) because publishing is asynchronous —
    the message is enqueued but not yet confirmed delivered when we respond.
    """
    start = time.perf_counter()
    try:
        envelope = EventEnvelope(
            event=event,
            producer_id=settings.service_name,
        )
        producer.publish(
            topic=settings.kafka_topic_user_events,
            key=event.user_id,
            value=envelope.model_dump(mode="python"),
        )
        elapsed = time.perf_counter() - start
        EVENTS_PUBLISHED.labels(event_type=event.event_type.value).inc()
        PUBLISH_LATENCY.observe(elapsed)
        logger.info(
            "event_accepted event_id=%s user_id=%s event_type=%s latency_ms=%.2f",
            event.event_id,
            event.user_id,
            event.event_type.value,
            elapsed * 1000,
        )
        return {"event_id": str(event.event_id), "status": "accepted"}

    except HTTPException:
        raise
    except Exception as exc:
        EVENTS_FAILED.labels(event_type=event.event_type.value).inc()
        logger.error("event_publish_failed event_id=%s error=%s", event.event_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to publish event to stream.",
        ) from exc


@app.post("/events/batch", status_code=status.HTTP_202_ACCEPTED)
async def ingest_event_batch(
    events: list[UserEvent],
    settings: Annotated[Settings, Depends(get_settings)],
    producer: Annotated[KafkaEventProducer, Depends(get_producer)],
) -> dict:
    """
    Accept a batch of up to 100 events in one request.

    Used by the simulator to avoid per-event HTTP overhead when replaying
    historical sessions or driving high-throughput load tests.

    Partial failures are tolerated: the response reports accepted vs failed
    counts. Individual event errors are logged but do not abort the batch.
    """
    if len(events) > 100:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Batch size exceeds maximum of 100 events.",
        )

    start = time.perf_counter()
    accepted, failed = 0, 0
    for event in events:
        try:
            envelope = EventEnvelope(
                event=event,
                producer_id=settings.service_name,
            )
            producer.publish(
                topic=settings.kafka_topic_user_events,
                key=event.user_id,
                value=envelope.model_dump(mode="python"),
            )
            EVENTS_PUBLISHED.labels(event_type=event.event_type.value).inc()
            accepted += 1
        except Exception as exc:
            EVENTS_FAILED.labels(event_type=event.event_type.value).inc()
            logger.error(
                "batch_event_failed event_id=%s error=%s", event.event_id, exc
            )
            failed += 1

    elapsed = time.perf_counter() - start
    PUBLISH_LATENCY.observe(elapsed)
    logger.info(
        "batch_accepted accepted=%d failed=%d total=%d latency_ms=%.2f",
        accepted, failed, len(events), elapsed * 1000,
    )
    return {"accepted": accepted, "failed": failed, "total": len(events)}


@app.get("/health", status_code=status.HTTP_200_OK)
async def health() -> dict:
    """
    Liveness probe for Docker healthcheck and load balancer target group checks.
    Returns 503 if the Kafka producer is not initialized.
    """
    if _producer is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Producer not initialized.",
        )
    return {"status": "ok", "service": _settings.service_name}
