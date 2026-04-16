# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

StreamRec is a real-time streaming recommendation system built to demonstrate production ML patterns. It consists of four Python microservices that pass data through Kafka and store state in Redis and PostgreSQL.

## Running the Stack

```bash
# Start all infrastructure and application services
docker compose -f infra/docker-compose.yml up -d

# Seed the database with synthetic data (required before first training run)
docker compose -f infra/docker-compose.yml --profile seed run --rm seed

# Run training (one-off; writes artifacts to the model_artifacts volume)
docker compose -f infra/docker-compose.yml --profile training run --rm training

# After training, restart inference to load new artifacts
docker compose -f infra/docker-compose.yml restart inference-service
```

Service ports:
- **event-producer**: `http://localhost:8001` (POST /events, POST /events/batch, GET /health, GET /metrics)
- **inference-service**: `http://localhost:8002` (GET /recommendations, GET /health, GET /metrics)
- **Kafka**: `localhost:9092` (PLAINTEXT_HOST listener for host tools)
- **PostgreSQL**: `localhost:5432` (user/pass/db: `streamrec`/`streamrec_dev`/`streamrec`)
- **Redis**: `localhost:6379`
- **Prometheus**: `http://localhost:9090`

## Running Training Locally (outside Docker)

All local commands require `PYTHONPATH=.` (repo root) so that `shared/` resolves as a top-level package.

```bash
# Seed the database with synthetic data first (targets localhost:5432 by default)
PYTHONPATH=. python -m training.data.generate_synthetic --users 1000 --items 500 --events 100000
# Pass --db-url to override: --db-url postgresql://user:pass@host:5432/db

# Run training; writes artifacts to ./artifacts/ by default
PYTHONPATH=. python -m training.train
```

All `TRAINING_*` env vars override defaults (e.g. `TRAINING_EMBEDDING_DIM=128`).

## Architecture

```
HTTP Client
    │ POST /events
    ▼
event-producer  ──(Kafka: user-events)──►  stream-processor
(FastAPI :8001)                                  │
                                         ┌───────┴───────┐
                                         ▼               ▼
                                       Redis           PostgreSQL
                                   (hot features)   (event log +
                                                    interaction matrix)
                                         │
                                         ▼
                                  inference-service
                                   (FastAPI :8002)
                                         │
                                      loads from
                                  model_artifacts volume
                                  (written by training)
```

**event-producer** (`event-producer/app/`): Stateless FastAPI service. Validates `UserEvent` via shared schema and publishes `EventEnvelope` to the `user-events` Kafka topic, using `user_id` as the partition key to preserve per-user event ordering.

**stream-processor** (`stream-processor/app/`): Kafka consumer that calls `EventProcessor.process()` → `UserFeatureStore.update()`. Dual-writes to Redis (hot path, pipelined) and PostgreSQL (cold path, idempotent via `ON CONFLICT (event_id) DO NOTHING`). Redis failure is non-fatal; Postgres failure is not.

**training** (`training/`): Offline pipeline run on-demand. Loads interaction data from PostgreSQL, trains a popularity baseline and a dot-product Matrix Factorization model (PyTorch, BCE loss, negative sampling), evaluates with NDCG/Recall, and saves artifacts to `artifacts/mf/` and `artifacts/popularity/`. Registers runs in the `model_registry` table.

**inference-service** (`inference-service/app/`): FastAPI service that loads frozen model artifacts at startup. Request flow: Redis cache check → fetch seen items from Redis ZSET → MF scoring (falls back to popularity on cold-start) → write cache → return `RecommendationResponse`.

## Shared Package (`shared/`)

`shared/` is mounted on `PYTHONPATH` in every Dockerfile. It contains the cross-service data contract — changes here are breaking for all services:

- **`schemas.py`**: Pydantic v2 models. `UserEvent` and `EventEnvelope` are frozen (immutable). `schema_version` is a `Literal["1.0"]` — bump to `"2.0"` and run both in parallel during migration.
- **`constants.py`**: Kafka topic names, Redis key patterns, model names, `EVENT_WEIGHTS` (used by both stream-processor and training).
- **`logging_config.py`**: Structured logging setup used by all services.

## Redis Key Schema

| Key | Type | Purpose |
|-----|------|---------|
| `user:{user_id}:recent_items` | ZSET (score=unix_ts) | Last 50 interacted items; read by inference for seen-item filtering |
| `user:{user_id}:event_counts` | HASH (type→count) | Cumulative per-event-type counters |
| `user:{user_id}:last_event_ts` | STRING | ISO-8601 UTC timestamp of last event |
| `item:popularity` | ZSET (score=weighted_count) | Global popularity; backing store for popularity model |
| `recs:{user_id}:k{k}` | STRING (JSON, TTL=300s) | Cached recommendation responses |

## Model Artifacts Layout

```
artifacts/
  popularity/
    items.json      # item_id → interaction count
  mf/
    model.pth       # PyTorch state_dict (weights only)
    config.json     # {n_users, n_items, embedding_dim}
    user2idx.json   # user_id → int index
    item2idx.json   # item_id → int index
```

Inference loads these cold at startup. After retraining, restart the inference container to pick up new weights.

## Configuration Pattern

Each service uses `pydantic-settings` with an env-var prefix:

| Service | Prefix | Default source |
|---------|--------|----------------|
| event-producer | *(none)* | `.env` at repo root |
| stream-processor | *(none)* | `.env` at repo root |
| inference-service | `INFERENCE_` | `.env` at repo root |
| training | `TRAINING_` | `.env` at repo root |

Docker Compose injects the in-network container hostnames (e.g. `KAFKA_BOOTSTRAP_SERVERS=kafka:9093`) as overrides on top of any `.env` file.

## Frontend (`frontend/`)

React + Vite + TypeScript + Tailwind CSS v4 + Zustand single-page app.

```bash
cd frontend
npm install
npm run dev      # dev server on http://localhost:5173, proxies /api → localhost:8002
npm run build    # production build to frontend/dist/
```

The Vite dev proxy strips the `/api` prefix before forwarding to the inference service, so the frontend never needs CORS headers. The backend must be running on port 8002 before opening the UI.

Key files:
- `src/store.ts` — Zustand store; all API state lives here
- `src/api.ts` — `fetch` wrappers with 5s timeout and typed error classes
- `src/lib/fake-metadata.ts` — deterministic `item_id → name/category` mapping (no real catalog needed)
- `src/components/ControlBar.tsx` — user ID input, k slider, quick-pick buttons (Known/Cold Start/Random)
- `src/components/DiagnosticsPanel.tsx` — model name, latency (color-coded), cache HIT/MISS, request history

## Key Design Constraints

- **Kafka partition key = `user_id`**: All events for a given user land on the same partition and are consumed in order. The stream-processor relies on this — no reordering logic exists.
- **`UserEvent` is frozen**: Never mutate an event after creation. To enrich, produce a new derived event type.
- **`schema_version` is a Literal**: Adding a new schema version requires a union type at the consumer, not a bump-in-place.
- **Postgres write is the source of truth**: Redis is a best-effort cache. A dropped Redis update is stale cache; a dropped Postgres write is lost training data.
- **Cold-start fallback chain**: MF → popularity → HTTP 503 (only if both are unloaded).
