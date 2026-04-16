"""
stream-processor/app/config.py

Environment-based configuration for the stream processor service.
All values can be overridden via environment variables or a .env file.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Service identity
    service_name: str = "stream-processor"
    log_level: str = "INFO"

    # Kafka consumer
    # Local:  Docker broker on localhost:9092
    # Prod:   Amazon MSK broker endpoint(s)
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_consumer_group: str = "stream-processor-v1"
    kafka_topic_user_events: str = "user-events"
    kafka_auto_offset_reset: str = "earliest"
    kafka_poll_timeout_s: float = 1.0
    # Commit offsets every N successfully processed messages.
    # Lower = more durable but more Kafka overhead.
    # Higher = fewer commits but larger replay window on crash.
    kafka_commit_interval: int = 50

    # Redis — hot feature store
    # Local:  Docker Redis on localhost:6379
    # Prod:   Amazon ElastiCache for Redis
    redis_url: str = "redis://localhost:6379/0"

    # PostgreSQL — cold event store and interaction matrix
    # Local:  Docker Postgres on localhost:5432
    # Prod:   Amazon RDS (PostgreSQL)
    database_url: str = "postgresql://streamrec:streamrec_dev@localhost:5432/streamrec"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
