"""Application configuration via environment variables."""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://embedai:embedai_dev@localhost:5432/embedai"
    jwt_secret: str = "dev-secret-change-in-production"
    stream_token_expire_seconds: int = 86400 * 30  # 30 days for annotation links

    label_studio_url: str = "http://localhost:8080"
    label_studio_api_key: str = "placeholder"

    gateway_url: str = "http://localhost:8000"

    redis_url: str = "redis://localhost:6379/0"

    model_config = {"env_prefix": "TASK_"}


settings = Settings()
