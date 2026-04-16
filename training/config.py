"""
training/config.py

Environment-driven configuration for the training pipeline.

All fields are overridable via environment variables prefixed with TRAINING_.
Example: TRAINING_EMBEDDING_DIM=128 python -m training.train

AWS equivalent:
  SageMaker Training Job passes hyperparameters as environment variables.
  database_url would point to RDS or Aurora; artifact_dir to an S3 path.
"""

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    service_name: str = "training"
    log_level: str = "INFO"

    # Data source
    database_url: str = "postgresql://streamrec:streamrec_dev@localhost:5432/streamrec"

    # Filtering: drop users/items with fewer than this many interactions.
    # Reduces noise from one-off visitors and near-invisible catalog items.
    min_interactions: int = Field(default=5, ge=1)

    # Artifact output directory (local path or s3:// URI in production)
    artifact_dir: str = "artifacts"

    # MF hyperparameters
    embedding_dim: int = Field(default=64, ge=4)
    learning_rate: float = Field(default=1e-3, gt=0)
    weight_decay: float = Field(default=1e-5, ge=0)
    n_epochs: int = Field(default=20, ge=1)
    batch_size: int = Field(default=1024, ge=1)
    n_negatives: int = Field(default=4, ge=1)

    # Evaluation cut-off
    eval_k: int = Field(default=10, ge=1)

    # Reproducibility
    seed: int = 42

    model_config = {"env_file": ".env", "env_prefix": "TRAINING_"}


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
