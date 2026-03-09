import asyncio
import os

from loguru import logger
from redis.asyncio import Redis

from pipeline.worker import PipelineWorker


async def main():
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    db_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://embedai:embedai@localhost:5432/embedai")
    minio_endpoint = os.getenv("MINIO_ENDPOINT", "localhost:9000")
    minio_access_key = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    minio_secret_key = os.getenv("MINIO_SECRET_KEY", "minioadmin")
    minio_bucket = os.getenv("MINIO_BUCKET", "embedai")

    redis = Redis.from_url(redis_url, decode_responses=False)

    # Lazy imports to avoid circular deps
    from pipeline.db import Database
    from pipeline.storage import StorageClient
    from pipeline.processor import EpisodeProcessor

    db = Database(db_url)
    await db.init()

    storage = StorageClient(minio_endpoint, minio_access_key, minio_secret_key, minio_bucket)

    processor = EpisodeProcessor(db=db, storage=storage)
    worker = PipelineWorker(redis=redis, processor=processor)

    logger.info("Starting EmbedAI pipeline worker")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
