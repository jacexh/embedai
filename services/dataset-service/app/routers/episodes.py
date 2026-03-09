"""Episode query API — Task 4.1."""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import CurrentUser, create_stream_token, get_current_user
from app.config import settings
from app.database import get_db
from app.models import Episode, Topic

router = APIRouter(prefix="/episodes", tags=["episodes"])


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class TopicOut(BaseModel):
    id: str
    name: str
    type: str | None
    start_time_offset: float | None
    end_time_offset: float | None
    message_count: int | None
    frequency_hz: float | None
    schema_name: str | None

    model_config = {"from_attributes": True}


class EpisodeOut(BaseModel):
    id: str
    project_id: str
    filename: str
    format: str
    size_bytes: int | None
    duration_seconds: float | None
    status: str
    quality_score: float | None
    storage_path: str | None
    recorded_at: str | None
    ingested_at: str | None
    created_at: str | None
    metadata: dict = {}  # serialized from episode_metadata

    model_config = {"from_attributes": True}


class EpisodeDetailOut(EpisodeOut):
    topics: list[TopicOut]


class EpisodeListOut(BaseModel):
    items: list[EpisodeOut]
    total: int
    limit: int
    offset: int


class StreamTokenOut(BaseModel):
    stream_token: str
    expires_in: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _episode_out(ep: Episode) -> dict:
    return {
        "id": str(ep.id),
        "project_id": str(ep.project_id),
        "filename": ep.filename,
        "format": ep.format,
        "size_bytes": ep.size_bytes,
        "duration_seconds": ep.duration_seconds,
        "status": ep.status,
        "quality_score": ep.quality_score,
        "storage_path": ep.storage_path,
        "recorded_at": ep.recorded_at.isoformat() if ep.recorded_at else None,
        "ingested_at": ep.ingested_at.isoformat() if ep.ingested_at else None,
        "created_at": ep.created_at.isoformat() if ep.created_at else None,
        "metadata": ep.episode_metadata or {},
    }


def _topic_out(t: Topic) -> dict:
    return {
        "id": str(t.id),
        "name": t.name,
        "type": t.type,
        "start_time_offset": t.start_time_offset,
        "end_time_offset": t.end_time_offset,
        "message_count": t.message_count,
        "frequency_hz": t.frequency_hz,
        "schema_name": t.schema_name,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=EpisodeListOut)
async def list_episodes(
    status: str | None = Query(None),
    format: str | None = Query(None),
    min_quality: float | None = Query(None, ge=0.0, le=1.0),
    search: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    project_id = uuid.UUID(current_user.project_id)

    base_query = select(Episode).where(Episode.project_id == project_id)
    if status:
        base_query = base_query.where(Episode.status == status)
    if format:
        base_query = base_query.where(Episode.format == format)
    if min_quality is not None:
        base_query = base_query.where(Episode.quality_score >= min_quality)
    if search:
        base_query = base_query.where(Episode.filename.ilike(f"%{search}%"))

    count_result = await db.execute(select(func.count()).select_from(base_query.subquery()))
    total = count_result.scalar_one()

    items_result = await db.execute(
        base_query.order_by(Episode.created_at.desc()).limit(limit).offset(offset)
    )
    episodes = items_result.scalars().all()

    return {
        "items": [_episode_out(ep) for ep in episodes],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/{episode_id}", response_model=EpisodeDetailOut)
async def get_episode_detail(
    episode_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    project_id = uuid.UUID(current_user.project_id)

    result = await db.execute(
        select(Episode)
        .where(Episode.id == episode_id, Episode.project_id == project_id)
        .options(selectinload(Episode.topics))
    )
    ep = result.scalar_one_or_none()
    if ep is None:
        raise HTTPException(status_code=404, detail="episode not found")

    data = _episode_out(ep)
    data["topics"] = [_topic_out(t) for t in ep.topics]
    return data


@router.get("/{episode_id}/stream-token", response_model=StreamTokenOut)
async def get_stream_token(
    episode_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    project_id = uuid.UUID(current_user.project_id)

    result = await db.execute(
        select(Episode).where(Episode.id == episode_id, Episode.project_id == project_id)
    )
    ep = result.scalar_one_or_none()
    if ep is None:
        raise HTTPException(status_code=404, detail="episode not found")

    expires_in = settings.stream_token_expire_seconds
    token = create_stream_token(str(episode_id), expires_in=expires_in)
    return {"stream_token": token, "expires_in": expires_in}
