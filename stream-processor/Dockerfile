# Build context must be the repository root.
# In docker-compose.yml:
#   build:
#     context: ..
#     dockerfile: stream-processor/Dockerfile

FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    librdkafka-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY stream-processor/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY stream-processor/app/ ./app/
COPY shared/ ./shared/

ENV PYTHONPATH=/app \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

CMD ["python", "-m", "app.main"]
