"""
event-producer/app/config.py

Environment-based configuration for the event producer service.
All values can be overridden via environment variables or a .env file.

This service does not own a database connection — raw event persistence
is the stream processor's responsibility. Config here is intentionally
scoped to what the producer actually uses.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Service identity
    service_name: str = "event-producer"
    service_port: int = 8001
    log_level: str = "INFO"

    # Kafka
    # Local:  Docker broker on localhost:9092
    # Prod:   Amazon MSK broker endpoint(s), comma-separated
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_topic_user_events: str = "user-events"
    kafka_producer_acks: str = "1"       # Use "all" for MSK in production
    kafka_producer_retries: int = 3
    kafka_producer_linger_ms: int = 5    # Small batching window; tune per throughput

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance. Cache is invalidated per process."""
    return Settings()
