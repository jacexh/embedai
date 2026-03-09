"""Label Studio webhook endpoint.

Receives ANNOTATION_CREATED / ANNOTATION_UPDATED events from Label Studio
and persists them into the annotations table, then updates the task status.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.integrations.label_studio import LabelStudioClient, get_ls_client
from app.models import Annotation, AnnotationTask

router = APIRouter(tags=["webhooks"])

_HANDLED_ACTIONS = {"ANNOTATION_CREATED", "ANNOTATION_UPDATED"}


@router.post("/webhooks/label-studio", status_code=200)
async def label_studio_webhook(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    ls: LabelStudioClient = Depends(get_ls_client),
) -> dict:
    """Handle incoming Label Studio webhook payloads."""
    action = payload.get("action")
    if action not in _HANDLED_ACTIONS:
        return {"status": "ignored", "action": action}

    anno_data = payload.get("annotation")
    if not anno_data:
        raise HTTPException(status_code=422, detail="missing annotation payload")

    ls_task_id: int = anno_data["task"]
    ls_annotation_id: int = anno_data["id"]
    result_labels: list = anno_data.get("result", [])

    # Look up our task by the Label Studio task id
    task_result = await db.execute(
        select(AnnotationTask).where(AnnotationTask.label_studio_task_id == ls_task_id)
    )
    task = task_result.scalar_one_or_none()
    if task is None:
        return {"status": "ignored", "reason": "unknown ls_task_id"}

    # Upsert annotation — if one with the same ls id already exists, update it
    existing_result = await db.execute(
        select(Annotation).where(Annotation.label_studio_annotation_id == ls_annotation_id)
    )
    annotation = existing_result.scalar_one_or_none()

    if annotation is None:
        annotation = Annotation()
        annotation.id = uuid.uuid4()
        annotation.task_id = task.id
        annotation.episode_id = task.created_by or task.id  # placeholder; episode comes from task context
        annotation.annotator_id = task.assigned_to or task.created_by  # type: ignore[assignment]
        annotation.created_at = datetime.now(timezone.utc)
        db.add(annotation)

    annotation.labels = result_labels
    annotation.label_studio_annotation_id = ls_annotation_id
    annotation.status = "submitted"
    annotation.submitted_at = datetime.now(timezone.utc)

    # Advance task status to "submitted" if not already reviewed
    if task.status in ("assigned", "created"):
        task.status = "submitted"
        task.updated_at = datetime.now(timezone.utc)

    await db.commit()
    return {"status": "ok", "task_id": str(task.id)}
