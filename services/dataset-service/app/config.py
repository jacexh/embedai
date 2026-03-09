"""Application configuration via environment variables."""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://embedai:embedai@localhost:5432/embedai"
    jwt_secret: str = "dev-secret-change-in-production"
    stream_token_expire_seconds: int = 3600
    redis_url: str = "redis://localhost:6379/0"

    model_config = {"env_prefix": "DATASET_"}


settings = Settings()
