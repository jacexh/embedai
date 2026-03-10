"""Application configuration via environment variables."""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://embedai:embedai@localhost:5432/embedai"
    jwt_secret: str = "dev-secret-change-in-production"
    stream_token_expire_seconds: int = 3600
    redis_url: str = "redis://localhost:6379/0"

    # MinIO
    minio_endpoint: str = "http://minio:9000"
    minio_bucket: str = "episodes"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin123"

    model_config = {"env_prefix": "DATASET_"}


settings = Settings()
