"""Database access layer for the pipeline worker."""
from __future__ import annotations

import uuid
from dataclasses import asdict
from typing import Any

from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from pipeline.extractors.models import TopicMeta


class ProjectInfo:
    def __init__(self, project_id: str, topic_schema: dict):
        self.project_id = project_id
        self.topic_schema = topic_schema


class Database:
    def __init__(self, db_url: str):
        self._engine = create_async_engine(db_url, pool_pre_ping=True)
        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)

    async def init(self):
        logger.info("Database connection pool initialised")

    async def update_episode_status(self, episode_id: str, status: str) -> None:
        async with self._session_factory() as session:
            await session.execute(
                text("UPDATE episodes SET status = :status WHERE id = :id"),
                {"status": status, "id": episode_id},
            )
            await session.commit()

    async def get_episode_project(self, episode_id: str) -> ProjectInfo:
        async with self._session_factory() as session:
            row = await session.execute(
                text(
                    "SELECT p.id, p.topic_schema FROM projects p "
                    "JOIN episodes e ON e.project_id = p.id "
                    "WHERE e.id = :id"
                ),
                {"id": episode_id},
            )
            r = row.one()
            return ProjectInfo(project_id=str(r[0]), topic_schema=r[1] or {})

    async def update_episode_ready(
        self,
        episode_id: str,
        duration: float,
        quality_score: float,
        metadata: dict,
        topics: list[TopicMeta],
    ) -> None:
        async with self._session_factory() as session:
            await session.execute(
                text(
                    "UPDATE episodes SET status='ready', duration_seconds=:duration, "
                    "quality_score=:quality_score, metadata=:metadata "
                    "WHERE id=:id"
                ),
                {
                    "id": episode_id,
                    "duration": duration,
                    "quality_score": quality_score,
                    "metadata": metadata,
                },
            )
            # Upsert topics
            for t in topics:
                await session.execute(
                    text(
                        "INSERT INTO topics (id, episode_id, name, type, start_time_offset, "
                        "end_time_offset, message_count, frequency_hz, schema_name) "
                        "VALUES (:id, :episode_id, :name, :type, :start, :end, :count, :freq, :schema)"
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "episode_id": episode_id,
                        "name": t.name,
                        "type": t.type,
                        "start": t.start_time_offset,
                        "end": t.end_time_offset,
                        "count": t.message_count,
                        "freq": t.frequency_hz,
                        "schema": t.schema_name,
                    },
                )
            await session.commit()
