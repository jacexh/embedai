"""Shared pytest fixtures for task-service tests."""
from __future__ import annotations

import time
import uuid
from collections.abc import Generator
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from jose import jwt

from app.config import settings
from app.main import app
from app.models import AnnotationTask, User


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

TEST_PROJECT_ID = str(uuid.uuid4())
TEST_USER_ID = str(uuid.uuid4())
TEST_ANNOTATOR_ID = str(uuid.uuid4())


def make_token(
    project_id: str = TEST_PROJECT_ID,
    user_id: str = TEST_USER_ID,
    role: str = "engineer",
) -> str:
    payload = {
        "user_id": user_id,
        "project_id": project_id,
        "role": role,
        "exp": int(time.time()) + 3600,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token()}"}


@pytest.fixture
def annotator_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(user_id=TEST_ANNOTATOR_ID, role='annotator_internal')}"}


@pytest.fixture
def reviewer_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(role='engineer')}"}


# ---------------------------------------------------------------------------
# DB / LS mocks
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_ls() -> AsyncMock:
    ls = AsyncMock()
    ls.create_project.return_value = 1
    ls.create_task.return_value = 42
    ls.get_annotations.return_value = []
    return ls


@pytest.fixture
def client(mock_db: AsyncMock, mock_ls: AsyncMock) -> Generator[TestClient, None, None]:
    from app.database import get_db
    from app.integrations.label_studio import get_ls_client

    async def _override_db():
        yield mock_db

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_ls_client] = lambda: mock_ls

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Seed data factories
# ---------------------------------------------------------------------------


def make_task(
    project_id: str = TEST_PROJECT_ID,
    status: str = "created",
    task_type: str = "video_annotation",
    assigned_to: str | None = None,
    ls_task_id: int | None = None,
) -> AnnotationTask:
    t = AnnotationTask()
    t.id = uuid.uuid4()
    t.project_id = uuid.UUID(project_id)
    t.dataset_version_id = None
    t.type = task_type
    t.guideline_url = "https://docs.example.com/guide"
    t.required_skills = ["video_annotation"]
    t.deadline = None
    t.status = status
    t.assigned_to = uuid.UUID(assigned_to) if assigned_to else None
    t.label_studio_task_id = ls_task_id
    t.created_by = uuid.UUID(TEST_USER_ID)
    t.created_at = datetime(2026, 3, 1, tzinfo=timezone.utc)
    t.updated_at = datetime(2026, 3, 1, tzinfo=timezone.utc)
    return t


def make_user(
    user_id: str = TEST_ANNOTATOR_ID,
    project_id: str = TEST_PROJECT_ID,
    role: str = "annotator_internal",
) -> User:
    u = User()
    u.id = uuid.UUID(user_id)
    u.project_id = uuid.UUID(project_id)
    u.email = f"{user_id[:8]}@test.com"
    u.name = "Test User"
    u.hashed_password = "hashed"
    u.role = role
    u.skill_tags = ["video_annotation"]
    u.is_active = True
    u.created_at = datetime(2026, 3, 1, tzinfo=timezone.utc)
    return u
