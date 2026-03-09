import asyncio
from typing import TYPE_CHECKING

from loguru import logger
from redis.asyncio import Redis

if TYPE_CHECKING:
    from pipeline.processor import EpisodeProcessor


class PipelineWorker:
    STREAM = "episodes:ingested"
    GROUP = "pipeline-workers"
    CONSUMER = "worker-1"

    def __init__(self, redis: Redis, processor: "EpisodeProcessor"):
        self.redis = redis
        self.processor = processor

    async def run(self):
        await self._ensure_group()
        logger.info("Pipeline worker started, listening on {}", self.STREAM)
        while True:
            messages = await self.redis.xreadgroup(
                self.GROUP,
                self.CONSUMER,
                {self.STREAM: ">"},
                count=1,
                block=5000,
            )
            for _, events in (messages or []):
                for msg_id, data in events:
                    await self._handle(msg_id, data)

    async def _handle(self, msg_id: str, data: dict):
        episode_id = data[b"episode_id"].decode()
        try:
            await self.processor.process(episode_id, data)
            await self.redis.xack(self.STREAM, self.GROUP, msg_id)
        except Exception as e:
            logger.error("Failed to process episode {}: {}", episode_id, e)
            # Do not ACK → message will be retried (DLQ to be added later)

    async def _ensure_group(self):
        try:
            await self.redis.xgroup_create(self.STREAM, self.GROUP, id="0", mkstream=True)
        except Exception:
            # Group already exists
            pass
