# StreamRec

A production-oriented real-time recommendation system demonstrating end-to-end ML infrastructure patterns — from event ingestion through stream processing, offline training, and live inference, to a full-featured React dashboard.

---

## Architecture

```
HTTP Client
    │ POST /events
    ▼
event-producer          Kafka: user-events          stream-processor
(FastAPI :8001)  ──────────────────────────────►  (Kafka consumer)
                   partition key = user_id               │
                                                 ┌───────┴────────┐
                                                 ▼                ▼
                                               Redis          PostgreSQL
                                           (hot features)   (event log +
                                                            interaction matrix)
                                                                   │
                                                          training pipeline
                                                          (on-demand, offline)
                                                                   │
                                                         artifacts/ (mf + popularity)
                                                                   │
                                                                   ▼
                                                        inference-service
                                                          (FastAPI :8002)
                                                                   │
                                                        Redis cache check →
                                                        MF scoring →
                                                        popularity fallback
                                                                   │
                                                                   ▼
                                                        React Dashboard
                                                          (:5173 dev)
```

**Key design decisions:**
- Kafka partition key = `user_id` — all events for a user land on the same partition, preserving causal ordering for the stream processor
- Redis is best-effort (hot cache + seen-item filter); PostgreSQL is the source of truth
- Cold-start fallback chain: MF → popularity baseline → HTTP 503

---

## Services

| Service | Port | Role |
|---|---|---|
| `event-producer` | 8001 | Ingests user events → publishes to Kafka |
| `stream-processor` | — | Consumes Kafka → dual-writes to Redis + PostgreSQL |
| `inference-service` | 8002 | Serves top-K recommendations from trained models |
| `training` | — | Offline pipeline: loads PostgreSQL → trains → saves artifacts |
| PostgreSQL | 5432 | Event log, interaction matrix, model registry |
| Redis | 6379 | Hot feature store, recommendation cache (TTL=300s) |
| Kafka | 9092 | Event streaming (3 partitions, user_id-keyed) |
| Prometheus | 9090 | Metrics scraping |

---

## Models

**Popularity Baseline** — scores items by weighted interaction count across all users. Serves all cold-start requests.

**Matrix Factorization** — dot-product MF with user/item biases, trained with BCE loss and negative sampling:

```
score(u, i) = sigmoid( <U_u, V_i> + b_u + b_i )
```

The following metrics were evaluated on a held-out split of the synthetic dataset (1,000 users, 500 items, 100,000 events):

| Model | NDCG@10 | Recall@10 |
|---|---|---|
| Popularity baseline | 0.2412 | 0.2100 |
| Matrix Factorization | **0.3351** | **0.3732** |

MF delivers ~39% NDCG improvement over the popularity baseline on this synthetic evaluation set.

---

## Tech Stack

**Backend**: Python 3.11 · FastAPI · PyTorch · Confluent Kafka · Redis · PostgreSQL · psycopg2 · Pydantic v2 · Prometheus

**Frontend**: React 18 · TypeScript · Vite · Tailwind CSS v4 · Zustand

**Infrastructure**: Docker Compose · AWS EC2 · AWS RDS · AWS S3 · AWS Amplify

---

## Getting Started

The backend is deployed on AWS (EC2 + RDS + S3). To run the dashboard locally against the live backend:

### Prerequisites

- Node.js 18+

### 1. Create a local environment file

`frontend/.env` is not committed to the repo. Create it manually:

```bash
echo "VITE_API_BASE_URL=http://3.144.144.215:8002" > frontend/.env
```

### 2. Run the frontend

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173). The frontend will connect to the live AWS backend using the URL set in `frontend/.env`.

---

## Local Training (without Docker)

All commands require `PYTHONPATH=.` from the repo root so that `shared/` resolves as a package.

```bash
# Seed
PYTHONPATH=. python -m training.data.generate_synthetic \
  --users 1000 --items 500 --events 100000

# Train (writes artifacts to ./artifacts/)
PYTHONPATH=. python -m training.train

# Override hyperparameters via TRAINING_* env vars
TRAINING_EMBEDDING_DIM=128 TRAINING_N_EPOCHS=30 PYTHONPATH=. python -m training.train
```

---

## Dashboard Features

- **Single mode** — enter any user ID, choose k, get ranked recommendations with scores and model info
- **Compare mode** — side-by-side MF vs popularity baseline for the same request
- **Quick picks** — Known User (MF path), Cold Start (popularity fallback), Random Known (samples uniformly from `user_0000`–`user_0999`)
- **Diagnostics panel** — live latency, cache HIT/MISS badge, model used, request history, zoomed latency sparkline (click to expand)
- **Offline evaluation** — NDCG@10 and Recall@10 for both models, displayed as static reference

---

## API

The inference service is accessible at the deployed AWS endpoint. Replace `<HOST>` with `localhost:8002` for local Docker use or the EC2 address for the live deployment.

```bash
# Health check
curl http://<HOST>/health

# Known user (MF model)
curl "http://<HOST>/recommendations?user_id=user_0001&k=10"

# Cold-start user (popularity fallback)
curl "http://<HOST>/recommendations?user_id=user_9999&k=10"

# Ingest an event (event-producer)
curl -X POST http://<HOST:8001>/events \
  -H "Content-Type: application/json" \
  -d '{"user_id": "user_0001", "item_id": "item_0042", "event_type": "purchase"}'
```

---

## Redis Key Schema

| Key | Type | Purpose |
|---|---|---|
| `user:{id}:recent_items` | ZSET (score=unix_ts) | Last 50 seen items; used by inference for filtering |
| `user:{id}:event_counts` | HASH | Per-type interaction counters |
| `user:{id}:last_event_ts` | STRING | ISO-8601 timestamp of last event |
| `item:popularity` | ZSET | Global popularity scores |
| `recs:{id}:k{k}` | STRING (JSON, TTL=300s) | Cached recommendation responses |

---

## Model Artifacts

```
artifacts/
  popularity/
    items.json          # item_id → weighted interaction count
  mf/
    model.pth           # PyTorch state_dict (weights only)
    config.json         # {n_users, n_items, embedding_dim}
    user2idx.json       # user_id → integer index
    item2idx.json       # item_id → integer index
```

---

## Configuration

Each service reads config from environment variables. All have sensible defaults for local Docker Compose use.

| Service | Env prefix | Key variables |
|---|---|---|
| `event-producer` | *(none)* | `KAFKA_BOOTSTRAP_SERVERS`, `KAFKA_TOPIC` |
| `stream-processor` | *(none)* | `KAFKA_BOOTSTRAP_SERVERS`, `DATABASE_URL`, `REDIS_URL` |
| `inference-service` | `INFERENCE_` | `INFERENCE_ARTIFACT_DIR`, `INFERENCE_REDIS_URL`, `INFERENCE_DB_URL` |
| `training` | `TRAINING_` | `TRAINING_DATABASE_URL`, `TRAINING_ARTIFACT_DIR`, `TRAINING_EMBEDDING_DIM` |

Docker Compose injects in-network hostnames (e.g. `KAFKA_BOOTSTRAP_SERVERS=kafka:9093`) on top of any `.env` file.

---

## AWS Deployment

The system is designed to map cleanly to managed AWS services:

| Local | AWS |
|---|---|
| PostgreSQL (Docker) | RDS PostgreSQL |
| Redis (Docker) | ElastiCache for Redis |
| Kafka + Zookeeper | Amazon MSK |
| `model_artifacts` volume | S3 |
| inference-service (EC2) | ECS Fargate or EC2 |
| Frontend (Vite build) | Amplify Hosting |

The inference service pulls model artifacts from S3 at container startup via an IAM instance role (no credentials in code). The frontend reads the backend URL from `VITE_API_BASE_URL`, set in a local `frontend/.env` file that is not committed to the repo.

---

## Project Structure

```
├── event-producer/         FastAPI event ingestion service
├── stream-processor/       Kafka consumer + feature store writer
├── inference-service/      FastAPI recommendation serving
├── training/               Offline training pipeline
│   ├── data/               Data loading + synthetic generation
│   ├── models/             MF and popularity model implementations
│   ├── evaluate.py         NDCG / Recall / Precision metrics
│   └── train.py            Main training entry point
├── shared/                 Cross-service contract (schemas, constants, logging)
├── frontend/               React + Vite dashboard
│   └── src/
│       ├── components/     UI components (13 total)
│       ├── store.ts        Zustand state store
│       ├── api.ts          Fetch wrappers with timeout
│       └── types.ts        Shared TypeScript types
└── infra/
    ├── docker-compose.yml  Full local stack
    ├── postgres/init.sql   DB schema + upsert functions
    └── prometheus.yml      Scrape config
```
