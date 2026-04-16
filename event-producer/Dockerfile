# Build context must be the repository root, not this service directory.
# In docker-compose.yml:
#   build:
#     context: ..          <- repo root
#     dockerfile: event-producer/Dockerfile

FROM python:3.11-slim

WORKDIR /app

# librdkafka is the C library backing confluent-kafka.
# gcc is required to compile the Python extension against it.
RUN apt-get update && apt-get install -y --no-install-recommends \
    librdkafka-dev \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps before copying source for better layer caching.
COPY event-producer/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy service source
COPY event-producer/app/ ./app/

# Copy shared package alongside app/ so `from shared.schemas import ...` resolves.
# PYTHONPATH=/app means Python searches /app first, finding both app/ and shared/.
COPY shared/ ./shared/

ENV PYTHONPATH=/app \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

EXPOSE 8001

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
