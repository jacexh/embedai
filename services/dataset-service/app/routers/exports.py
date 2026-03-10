"""Export job API — triggers async export of a dataset version.

POST /dataset-versions/{version_id}/exports  (original route)
POST /export-jobs                            (frontend-compatible alias)
  → creates ExportJob row + publishes to Redis Stream `export-jobs:pending`

GET /export-jobs               → list all jobs (optional ?version_id= filter)
GET /export-jobs/{job_id}      → poll single job status
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query
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


class CreateExportByVersionRequest(BaseModel):
    """Body for POST /dataset-versions/{version_id}/exports."""
    format: str = "webdataset"
    target_bucket: str
    target_prefix: str | None = None


class CreateExportRequest(BaseModel):
    """Body for POST /export-jobs (frontend-compatible route, version_id in body)."""
    version_id: str
    format: str = "webdataset"
    target_bucket: str
    target_prefix: str | None = None


class ExportJobOut(BaseModel):
    id: str
    version_id: str           # frontend field name
    dataset_version_id: str   # kept for backward compat
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
    updated_at: str | None


class ExportJobListOut(BaseModel):
    items: list[ExportJobOut]
    total: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _job_out(job: ExportJob) -> dict:
    version_id_str = str(job.dataset_version_id)
    return {
        "id": str(job.id),
        "version_id": version_id_str,
        "dataset_version_id": version_id_str,
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
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
    }


async def _create_job(
    version_id: uuid.UUID,
    format: str,
    target_bucket: str,
    target_prefix: str | None,
    current_user: CurrentUser,
    db: AsyncSession,
    redis: aioredis.Redis,
) -> dict:
    if format not in ("webdataset", "raw"):
        raise HTTPException(status_code=422, detail="format must be 'webdataset' or 'raw'")

    result = await db.execute(select(DatasetVersion).where(DatasetVersion.id == version_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="dataset version not found")

    now = datetime.now(timezone.utc)
    job = ExportJob()
    job.id = uuid.uuid4()
    job.dataset_version_id = version_id
    job.triggered_by = uuid.UUID(current_user.user_id)
    job.format = format
    job.target_bucket = target_bucket
    job.target_prefix = target_prefix or f"exports/{job.id}"
    job.status = "pending"
    job.progress_pct = 0.0
    job.created_at = now
    job.updated_at = now

    db.add(job)
    await db.commit()
    await db.refresh(job)

    await redis.xadd(EXPORT_STREAM, {"job_id": str(job.id)})

    return _job_out(job)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/dataset-versions/{version_id}/exports",
    status_code=202,
    response_model=ExportJobOut,
)
async def create_export_job_by_version(
    version_id: uuid.UUID,
    body: CreateExportByVersionRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> dict:
    return await _create_job(
        version_id=version_id,
        format=body.format,
        target_bucket=body.target_bucket,
        target_prefix=body.target_prefix,
        current_user=current_user,
        db=db,
        redis=redis,
    )


@router.post("/export-jobs", status_code=202, response_model=ExportJobOut)
async def create_export_job(
    body: CreateExportRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> dict:
    """Frontend-compatible route: POST /export-jobs with version_id in body."""
    try:
        version_id = uuid.UUID(body.version_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="version_id must be a valid UUID")

    return await _create_job(
        version_id=version_id,
        format=body.format,
        target_bucket=body.target_bucket,
        target_prefix=body.target_prefix,
        current_user=current_user,
        db=db,
        redis=redis,
    )


@router.get("/export-jobs", response_model=ExportJobListOut)
async def list_export_jobs(
    version_id: str | None = Query(None),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List export jobs, optionally filtered by version_id."""
    stmt = select(ExportJob)
    if version_id:
        try:
            vid = uuid.UUID(version_id)
        except ValueError:
            raise HTTPException(status_code=422, detail="version_id must be a valid UUID")
        stmt = stmt.where(ExportJob.dataset_version_id == vid)
    stmt = stmt.order_by(ExportJob.created_at.desc())

    result = await db.execute(stmt)
    jobs = result.scalars().all()
    items = [_job_out(j) for j in jobs]
    return {"items": items, "total": len(items)}


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
