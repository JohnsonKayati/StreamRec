# Build context must be the repository root.
# In docker-compose.yml:
#   build:
#     context: ..
#     dockerfile: inference-service/Dockerfile

FROM python:3.11-slim

WORKDIR /app

# No librdkafka or psycopg2 needed — this service only touches Redis and
# loads model artifacts from the local filesystem (or a mounted volume).
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY inference-service/requirements.txt ./requirements.txt

# Install CPU-only PyTorch first to avoid pulling the CUDA wheel (~2 GB extra).
# The --index-url flag is scoped to this RUN layer; subsequent pip calls use PyPI.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir -r requirements.txt

COPY inference-service/app/ ./app/
COPY shared/ ./shared/

ENV PYTHONPATH=/app \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# artifacts/ is expected to be volume-mounted at runtime with trained model files.
# Set INFERENCE_ARTIFACT_DIR to override the default path.
VOLUME ["/app/artifacts"]

EXPOSE 8002

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8002/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
