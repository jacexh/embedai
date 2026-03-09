"""Export worker configuration via environment variables."""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://embedai:embedai_dev@localhost:5432/embedai"

    redis_url: str = "redis://localhost:6379/0"
    export_stream: str = "export-jobs:pending"
    consumer_group: str = "export-workers"
    consumer_name: str = "worker-1"

    # MinIO / S3-compatible storage
    minio_endpoint: str = "http://localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "embedai"

    shard_size_bytes: int = 400 * 1024 * 1024  # 400 MB
    tmp_dir: str = "/tmp/export"

    model_config = {"env_prefix": "EXPORT_"}


settings = Settings()
