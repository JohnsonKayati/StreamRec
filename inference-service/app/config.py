"""
inference-service/app/config.py

Environment-driven configuration for the inference service.
All values are overridable via INFERENCE_* environment variables or a .env file.

AWS equivalent:
  ECS task definition environment variables or SSM Parameter Store values
  injected at task launch time. artifact_dir would be an S3 path read by
  the container's entrypoint before starting uvicorn.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    service_name: str = "inference-service"
    service_port: int = 8002
    log_level: str = "INFO"

    # Directory containing trained model artifacts written by training/train.py.
    # Expected layout:
    #   {artifact_dir}/mf/model.pth
    #   {artifact_dir}/mf/config.json
    #   {artifact_dir}/mf/user2idx.json
    #   {artifact_dir}/mf/item2idx.json
    #   {artifact_dir}/popularity/popularity_model.json
    artifact_dir: str = "artifacts"

    # Redis — same instance as the stream processor's hot feature store.
    # Used for: user seen-item lookup and recommendation response caching.
    redis_url: str = "redis://localhost:6379/0"

    # Seconds to cache a recommendation response.  Set to 0 to disable.
    recs_cache_ttl_s: int = 300

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="INFERENCE_",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
