# Build context must be the repository root.
# In docker-compose.yml:
#   build:
#     context: ..
#     dockerfile: training/Dockerfile

FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY training/requirements.txt ./requirements.txt

# CPU-only torch — training on GPU would require the CUDA base image instead.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir -r requirements.txt

COPY training/ ./training/
COPY shared/   ./shared/

ENV PYTHONPATH=/app \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

CMD ["python", "-m", "training.train"]
