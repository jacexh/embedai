"""Annotation task management API — Task 5.2.

State machine (ADR H4):
  created → assigned → submitted → approved
                    ↘            ↗
                     rejected → assigned  (re-assign for rework)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentUser, get_current_user, require_role, create_stream_token
from app.config import settings
from app.database import get_db
from app.integrations.label_studio import LabelStudioClient, get_ls_client
from app.models import AnnotationTask, User

router = APIRouter(tags=["tasks"])

# ---------------------------------------------------------------------------
# Valid state transitions (ADR H4)
# ---------------------------------------------------------------------------

_TRANSITIONS: dict[str, set[str]] = {
    "created": {"assigned"},
    "assigned": {"submitted", "created"},  # created = unassign
    "submitted": {"approved", "rejected"},
    "rejected": {"assigned"},
    "approved": set(),
}


def _assert_transition(current: str, target: str) -> None:
    allowed = _TRANSITIONS.get(current, set())
    if target not in allowed:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot transition task from '{current}' to '{target}'",
        )


# ---------------------------------------------------------------------------
# Default Label Studio label config per task type
# ---------------------------------------------------------------------------

_DEFAULT_LABEL_CONFIG: dict[str, str] = {
    "video_annotation": """
<View>
  <Video name="video" value="$video"/>
  <VideoRectangle name="box" toName="video"/>
  <Labels name="label" toName="video">
    <Label value="robot_arm" background="blue"/>
    <Label value="object" background="green"/>
    <Label value="obstacle" background="red"/>
  </Labels>
</View>
""",
    "image_classification": """
<View>
  <Image name="image" value="$image"/>
  <Choices name="label" toName="image">
    <Choice value="success"/>
    <Choice value="failure"/>
    <Choice value="uncertain"/>
  </Choices>
</View>
""",
}

_FALLBACK_LABEL_CONFIG = """
<View>
  <Video name="video" value="$video"/>
  <TextArea name="notes" toName="video" placeholder="Annotation notes"/>
</View>
"""


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class CreateTaskRequest(BaseModel):
    episode_id: str
    type: str  # video_annotation | image_classification | ...
    dataset_version_id: str | None = None
    guideline_url: str | None = None
    required_skills: list[str] = []
    deadline: datetime | None = None


class AssignRequest(BaseModel):
    user_id: uuid.UUID


class RejectRequest(BaseModel):
    comment: str | None = None


class TaskOut(BaseModel):
    id: str
    project_id: str
    episode_id: str | None
    dataset_version_id: str | None
    type: str
    guideline_url: str | None
    required_skills: list
    deadline: str | None
    status: str
    assigned_to: str | None
    label_studio_task_id: int | None
    created_by: str | None
    created_at: str | None
    updated_at: str | None


class UserWorkloadOut(BaseModel):
    id: str
    email: str
    name: str
    role: str
    skill_tags: list
    pending_task_count: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _task_out(task: AnnotationTask) -> dict:
    return {
        "id": str(task.id),
        "project_id": str(task.project_id),
        "episode_id": str(task.episode_id) if task.episode_id else None,
        "dataset_version_id": str(task.dataset_version_id) if task.dataset_version_id else None,
        "type": task.type,
        "guideline_url": task.guideline_url,
        "required_skills": task.required_skills or [],
        "deadline": task.deadline.isoformat() if task.deadline else None,
        "status": task.status,
        "assigned_to": str(task.assigned_to) if task.assigned_to else None,
        "label_studio_task_id": task.label_studio_task_id,
        "created_by": str(task.created_by) if task.created_by else None,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/tasks", response_model=list[TaskOut])
async def list_tasks(
    status: str | None = None,
    assigned_to: str | None = None,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list:
    project_id = uuid.UUID(current_user.project_id)
    q = select(AnnotationTask).where(AnnotationTask.project_id == project_id)
    if status:
        q = q.where(AnnotationTask.status == status)
    if assigned_to:
        q = q.where(AnnotationTask.assigned_to == uuid.UUID(assigned_to))
    result = await db.execute(q.order_by(AnnotationTask.created_at.desc()))
    tasks = result.scalars().all()
    return [_task_out(t) for t in tasks]


@router.post("/tasks", status_code=201, response_model=TaskOut)
async def create_task(
    body: CreateTaskRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    ls: LabelStudioClient = Depends(get_ls_client),
) -> dict:
    project_id = uuid.UUID(current_user.project_id)
    user_id = uuid.UUID(current_user.user_id)

    task = AnnotationTask()
    task.id = uuid.uuid4()
    task.project_id = project_id
    task.dataset_version_id = uuid.UUID(body.dataset_version_id) if body.dataset_version_id else None
    task.episode_id = uuid.UUID(body.episode_id) if body.episode_id else None
    task.type = body.type
    task.guideline_url = body.guideline_url
    task.required_skills = body.required_skills
    task.deadline = body.deadline
    task.status = "created"
    task.created_by = user_id
    task.created_at = datetime.now(timezone.utc)
    task.updated_at = datetime.now(timezone.utc)

    db.add(task)
    await db.flush()  # get task.id before LS call

    # Create corresponding Label Studio task
    stream_token = create_stream_token(body.episode_id)
    data_url = f"{settings.gateway_url}/api/v1/stream/{body.episode_id}?token={stream_token}"
    label_config = _DEFAULT_LABEL_CONFIG.get(body.type, _FALLBACK_LABEL_CONFIG)

    try:
        ls_project_id = await ls.create_project(
            name=f"project-{str(project_id)[:8]}-{body.type}",
            label_config=label_config,
        )
        ls_task_id = await ls.create_task(
            project_id=ls_project_id,
            data_url=data_url,
            meta={"episode_id": body.episode_id},
        )
        task.label_studio_task_id = ls_task_id
    except Exception:
        # LS integration is best-effort; log but don't block task creation
        pass

    await db.commit()
    await db.refresh(task)
    return _task_out(task)


@router.get("/tasks/{task_id}", response_model=TaskOut)
async def get_task(
    task_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    project_id = uuid.UUID(current_user.project_id)
    result = await db.execute(
        select(AnnotationTask).where(
            AnnotationTask.id == task_id,
            AnnotationTask.project_id == project_id,
        )
    )
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return _task_out(task)


@router.post("/tasks/{task_id}/assign", response_model=TaskOut)
async def assign_task(
    task_id: uuid.UUID,
    body: AssignRequest,
    current_user: Annotated[CurrentUser, Depends(require_role("engineer", "admin"))],
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(
        select(AnnotationTask).where(
            AnnotationTask.id == task_id,
            AnnotationTask.project_id == uuid.UUID(current_user.project_id),
        )
    )
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")

    _assert_transition(task.status, "assigned")

    task.assigned_to = body.user_id
    task.status = "assigned"
    task.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(task)
    return _task_out(task)


@router.post("/tasks/{task_id}/submit", response_model=TaskOut)
async def submit_task(
    task_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(
        select(AnnotationTask).where(AnnotationTask.id == task_id)
    )
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")

    # Annotator can only submit their own task
    if (
        current_user.role not in ("admin", "engineer")
        and str(task.assigned_to) != current_user.user_id
    ):
        raise HTTPException(status_code=403, detail="not assigned to this task")

    _assert_transition(task.status, "submitted")

    task.status = "submitted"
    task.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(task)
    return _task_out(task)


@router.post("/tasks/{task_id}/approve", response_model=TaskOut)
async def approve_task(
    task_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(require_role("engineer", "admin"))],
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(
        select(AnnotationTask).where(
            AnnotationTask.id == task_id,
            AnnotationTask.project_id == uuid.UUID(current_user.project_id),
        )
    )
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")

    _assert_transition(task.status, "approved")

    task.status = "approved"
    task.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(task)

    # Publish annotation-approved event via Redis Streams (best-effort)
    await _publish_annotation_approved(str(task.id))

    return _task_out(task)


@router.post("/tasks/{task_id}/reject", response_model=TaskOut)
async def reject_task(
    task_id: uuid.UUID,
    body: RejectRequest,
    current_user: Annotated[CurrentUser, Depends(require_role("engineer", "admin"))],
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(
        select(AnnotationTask).where(
            AnnotationTask.id == task_id,
            AnnotationTask.project_id == uuid.UUID(current_user.project_id),
        )
    )
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")

    _assert_transition(task.status, "rejected")

    task.status = "rejected"
    task.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(task)
    return _task_out(task)


# ---------------------------------------------------------------------------
# User workload (ADR H4: show annotator load before assignment)
# ---------------------------------------------------------------------------


@router.get("/users", response_model=list[UserWorkloadOut])
async def list_users_with_workload(
    role: str | None = None,
    include_workload: bool = False,
    current_user: Annotated[CurrentUser, Depends(require_role("engineer", "admin"))] = None,  # type: ignore[assignment]
    db: AsyncSession = Depends(get_db),
) -> list:
    project_id = uuid.UUID(current_user.project_id)
    q = select(User).where(User.project_id == project_id, User.is_active.is_(True))
    if role:
        # Prefix match: role=annotator matches annotator_internal and annotator_outsource
        q = q.where(User.role.startswith(role))
    result = await db.execute(q)
    users = result.scalars().all()

    if include_workload:
        # Count pending tasks per user in one query
        counts_result = await db.execute(
            select(AnnotationTask.assigned_to, func.count().label("cnt"))
            .where(
                AnnotationTask.project_id == project_id,
                AnnotationTask.status.in_(["assigned", "created"]),
                AnnotationTask.assigned_to.isnot(None),
            )
            .group_by(AnnotationTask.assigned_to)
        )
        workload: dict[uuid.UUID, int] = {row[0]: row[1] for row in counts_result}
    else:
        workload = {}

    return [
        {
            "id": str(u.id),
            "email": u.email,
            "name": u.name,
            "role": u.role,
            "skill_tags": u.skill_tags or [],
            "pending_task_count": workload.get(u.id, 0),
        }
        for u in users
    ]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _publish_annotation_approved(task_id: str) -> None:
    """Publish annotation-approved event to Redis Streams (best-effort)."""
    try:
        import redis.asyncio as aioredis
        from app.config import settings as cfg

        r = await aioredis.from_url(cfg.redis_url)
        await r.xadd("annotation-events", {"event": "approved", "task_id": task_id})
        await r.aclose()
    except Exception:
        pass  # non-critical
