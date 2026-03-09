"""Export job API — triggers async export of a dataset version.

POST /dataset-versions/{version_id}/exports
  → creates ExportJob row + publishes to Redis Stream `export-jobs:pending`

GET /export-jobs/{job_id}
  → polls job status + progress
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentUser, get_current_user
from app.config import settings
from app.database import get_db
from app.models import DatasetVersion, ExportJob

router = APIRouter(tags=["exports"])

EXPORT_STREAM = "export-jobs:pending"


# ---------------------------------------------------------------------------
# Redis dependency
# ---------------------------------------------------------------------------


async def get_redis() -> aioredis.Redis:
    r = aioredis.from_url(settings.redis_url, decode_responses=True)
    try:
        yield r
    finally:
        await r.aclose()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class CreateExportRequest(BaseModel):
    format: str = "webdataset"  # webdataset | raw
    target_bucket: str
    target_prefix: str | None = None


class ExportJobOut(BaseModel):
    id: str
    dataset_version_id: str
    format: str
    target_bucket: str
    target_prefix: str | None
    status: str
    progress_pct: float | None
    manifest_url: str | None
    error_message: str | None
    started_at: str | None
    completed_at: str | None
    created_at: str | None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _job_out(job: ExportJob) -> dict:
    return {
        "id": str(job.id),
        "dataset_version_id": str(job.dataset_version_id),
        "format": job.format,
        "target_bucket": job.target_bucket,
        "target_prefix": job.target_prefix,
        "status": job.status,
        "progress_pct": job.progress_pct,
        "manifest_url": job.manifest_url,
        "error_message": job.error_message,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "created_at": job.created_at.isoformat() if job.created_at else None,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/dataset-versions/{version_id}/exports", status_code=202, response_model=ExportJobOut)
async def create_export_job(
    version_id: uuid.UUID,
    body: CreateExportRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> dict:
    if body.format not in ("webdataset", "raw"):
        raise HTTPException(status_code=422, detail="format must be 'webdataset' or 'raw'")

    # Verify version exists
    result = await db.execute(select(DatasetVersion).where(DatasetVersion.id == version_id))
    version = result.scalar_one_or_none()
    if version is None:
        raise HTTPException(status_code=404, detail="dataset version not found")

    job = ExportJob()
    job.id = uuid.uuid4()
    job.dataset_version_id = version_id
    job.triggered_by = uuid.UUID(current_user.user_id)
    job.format = body.format
    job.target_bucket = body.target_bucket
    job.target_prefix = body.target_prefix or f"exports/{job.id}"
    job.status = "pending"
    job.progress_pct = 0.0
    job.created_at = datetime.now(timezone.utc)

    db.add(job)
    await db.commit()
    await db.refresh(job)

    # Enqueue to Redis Stream
    await redis.xadd(EXPORT_STREAM, {"job_id": str(job.id)})

    return _job_out(job)


@router.get("/export-jobs/{job_id}", response_model=ExportJobOut)
async def get_export_job(
    job_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(select(ExportJob).where(ExportJob.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="export job not found")
    return _job_out(job)
