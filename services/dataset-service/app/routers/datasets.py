"""Dataset version management API — Task 4.2.

ADR H5: Dataset versions are immutable once created.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentUser, get_current_user
from app.database import get_db
from app.models import Dataset, DatasetVersion, Episode

router = APIRouter(tags=["datasets"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class EpisodeRefIn(BaseModel):
    episode_id: str
    clip_start: float | None = None
    clip_end: float | None = None


class CreateDatasetRequest(BaseModel):
    name: str
    description: str | None = None


class CreateVersionRequest(BaseModel):
    version_tag: str
    episode_refs: list[EpisodeRefIn] = []


class PatchVersionRequest(BaseModel):
    description: str | None = None


class DatasetOut(BaseModel):
    id: str
    project_id: str
    name: str
    description: str | None
    status: str
    created_by: str | None
    created_at: str | None


class DatasetVersionOut(BaseModel):
    id: str
    dataset_id: str
    version_tag: str
    episode_refs: list
    episode_count: int | None
    total_size_bytes: int | None
    is_immutable: bool
    created_by: str | None
    created_at: str | None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dataset_out(ds: Dataset) -> dict:
    return {
        "id": str(ds.id),
        "project_id": str(ds.project_id),
        "name": ds.name,
        "description": ds.description,
        "status": ds.status,
        "created_by": str(ds.created_by) if ds.created_by else None,
        "created_at": ds.created_at.isoformat() if ds.created_at else None,
    }


def _version_out(v: DatasetVersion) -> dict:
    return {
        "id": str(v.id),
        "dataset_id": str(v.dataset_id),
        "version_tag": v.version_tag,
        "episode_refs": v.episode_refs or [],
        "episode_count": v.episode_count,
        "total_size_bytes": v.total_size_bytes,
        "size_estimate_bytes": v.total_size_bytes,  # frontend field name alias
        "is_immutable": v.is_immutable,
        "created_by": str(v.created_by) if v.created_by else None,
        "created_at": v.created_at.isoformat() if v.created_at else None,
    }


# ---------------------------------------------------------------------------
# Dataset endpoints
# ---------------------------------------------------------------------------


@router.get("/datasets")
async def list_datasets(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    project_id = uuid.UUID(current_user.project_id)
    result = await db.execute(
        select(Dataset).where(Dataset.project_id == project_id).order_by(Dataset.created_at.desc())
    )
    datasets = result.scalars().all()
    items = [_dataset_out(ds) for ds in datasets]
    return {"items": items, "total": len(items)}


@router.post("/datasets", status_code=201, response_model=DatasetOut)
async def create_dataset(
    body: CreateDatasetRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    project_id = uuid.UUID(current_user.project_id)
    user_id = uuid.UUID(current_user.user_id)

    ds = Dataset()
    ds.id = uuid.uuid4()
    ds.project_id = project_id
    ds.name = body.name
    ds.description = body.description
    ds.status = "draft"
    ds.created_by = user_id
    ds.created_at = datetime.now(timezone.utc)

    db.add(ds)
    await db.commit()
    await db.refresh(ds)
    return _dataset_out(ds)


# ---------------------------------------------------------------------------
# Version endpoints
# ---------------------------------------------------------------------------


@router.get("/datasets/{dataset_id}/versions")
async def list_versions(
    dataset_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    project_id = uuid.UUID(current_user.project_id)

    ds_result = await db.execute(
        select(Dataset).where(Dataset.id == dataset_id, Dataset.project_id == project_id)
    )
    ds = ds_result.scalar_one_or_none()
    if ds is None:
        raise HTTPException(status_code=404, detail="dataset not found")

    v_result = await db.execute(
        select(DatasetVersion).where(DatasetVersion.dataset_id == dataset_id).order_by(DatasetVersion.created_at.desc())
    )
    versions = v_result.scalars().all()
    items = [_version_out(v) for v in versions]
    return {"items": items, "total": len(items)}


@router.post("/datasets/{dataset_id}/versions", status_code=201, response_model=DatasetVersionOut)
async def create_version(
    dataset_id: uuid.UUID,
    body: CreateVersionRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    project_id = uuid.UUID(current_user.project_id)
    user_id = uuid.UUID(current_user.user_id)

    # Verify dataset belongs to this project
    ds_result = await db.execute(
        select(Dataset).where(Dataset.id == dataset_id, Dataset.project_id == project_id)
    )
    ds = ds_result.scalar_one_or_none()
    if ds is None:
        raise HTTPException(status_code=404, detail="dataset not found")

    # Validate all episode_refs belong to the same project
    episode_refs = body.episode_refs
    ref_ids = [uuid.UUID(ref.episode_id) for ref in episode_refs]

    if ref_ids:
        ep_result = await db.execute(
            select(Episode).where(Episode.id.in_(ref_ids), Episode.project_id == project_id)
        )
        found_episodes = ep_result.scalars().all()
        if len(found_episodes) != len(ref_ids):
            raise HTTPException(
                status_code=422,
                detail="one or more episode ids not found in this project",
            )
        total_size = sum(ep.size_bytes or 0 for ep in found_episodes)
    else:
        found_episodes = []
        total_size = 0

    # Build serializable episode refs
    refs_data = [
        {
            "episode_id": ref.episode_id,
            "clip_start": ref.clip_start,
            "clip_end": ref.clip_end,
        }
        for ref in episode_refs
    ]

    version = DatasetVersion()
    version.id = uuid.uuid4()
    version.dataset_id = dataset_id
    version.version_tag = body.version_tag
    version.episode_refs = refs_data
    version.episode_count = len(episode_refs)
    version.total_size_bytes = total_size
    version.is_immutable = True  # ADR H5: versions are immutable on creation
    version.created_by = user_id
    version.created_at = datetime.now(timezone.utc)

    db.add(version)
    await db.commit()
    await db.refresh(version)
    return _version_out(version)


@router.patch("/dataset-versions/{version_id}")
async def patch_version(
    version_id: uuid.UUID,
    body: PatchVersionRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(
        select(DatasetVersion).where(DatasetVersion.id == version_id)
    )
    version = result.scalar_one_or_none()
    if version is None:
        raise HTTPException(status_code=404, detail="version not found")

    if version.is_immutable:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=409, content={"error": "Dataset version is immutable"})

    # Apply mutable updates (only description-level metadata in this context)
    await db.commit()
    return _version_out(version)
