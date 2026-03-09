"""Tests for annotation task management API — Task 5.2."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from tests.conftest import (
    TEST_ANNOTATOR_ID,
    TEST_PROJECT_ID,
    TEST_USER_ID,
    make_task,
    make_user,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _exec_returns(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return AsyncMock(return_value=result)


def _exec_returns_all(values):
    result = MagicMock()
    result.scalars.return_value.all.return_value = values
    return AsyncMock(return_value=result)


# ---------------------------------------------------------------------------
# List tasks
# ---------------------------------------------------------------------------


class TestListTasks:
    def test_list_tasks_returns_empty(
        self, client: TestClient, mock_db: AsyncMock, auth_headers: dict
    ):
        mock_db.execute = _exec_returns_all([])
        resp = client.get("/api/v1/tasks", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_tasks_filters_by_status(
        self, client: TestClient, mock_db: AsyncMock, auth_headers: dict
    ):
        task = make_task(status="assigned")
        mock_db.execute = _exec_returns_all([task])
        resp = client.get("/api/v1/tasks?status=assigned", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["status"] == "assigned"


# ---------------------------------------------------------------------------
# Create task
# ---------------------------------------------------------------------------


class TestCreateTask:
    def test_create_task_returns_201(
        self, client: TestClient, mock_db: AsyncMock, mock_ls: AsyncMock, auth_headers: dict
    ):
        created_task = make_task(ls_task_id=42)

        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()
        mock_db.add = MagicMock()

        # After refresh, mock_db.refresh sets ls_task_id on the task object
        async def _refresh(obj):
            obj.label_studio_task_id = 42

        mock_db.refresh.side_effect = _refresh

        # We need to return created_task after add+commit
        # The router calls db.flush(), then commit(), then refresh(task)
        # task object is created inline so we just need refresh to work

        resp = client.post(
            "/api/v1/tasks",
            json={
                "episode_id": str(uuid.uuid4()),
                "type": "video_annotation",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "created"
        assert data["type"] == "video_annotation"
        assert data["label_studio_task_id"] == 42

    def test_create_task_ls_failure_still_creates(
        self, client: TestClient, mock_db: AsyncMock, mock_ls: AsyncMock, auth_headers: dict
    ):
        """LS integration failure should not prevent task creation."""
        mock_ls.create_project.side_effect = Exception("LS unavailable")
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.refresh = AsyncMock()

        resp = client.post(
            "/api/v1/tasks",
            json={"episode_id": str(uuid.uuid4()), "type": "video_annotation"},
            headers=auth_headers,
        )
        assert resp.status_code == 201


# ---------------------------------------------------------------------------
# Assign task (state machine)
# ---------------------------------------------------------------------------


class TestAssignTask:
    def test_assign_task_success(
        self, client: TestClient, mock_db: AsyncMock, auth_headers: dict
    ):
        task = make_task(status="created")
        mock_db.execute = _exec_returns(task)
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        resp = client.post(
            f"/api/v1/tasks/{task.id}/assign",
            json={"user_id": TEST_ANNOTATOR_ID},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert task.status == "assigned"
        assert task.assigned_to == uuid.UUID(TEST_ANNOTATOR_ID)

    def test_assign_task_invalid_transition_409(
        self, client: TestClient, mock_db: AsyncMock, auth_headers: dict
    ):
        task = make_task(status="approved")
        mock_db.execute = _exc_returns_one(task)
        mock_db.commit = AsyncMock()

        resp = client.post(
            f"/api/v1/tasks/{task.id}/assign",
            json={"user_id": TEST_ANNOTATOR_ID},
            headers=auth_headers,
        )
        assert resp.status_code == 409

    def test_assign_requires_engineer_role(
        self, client: TestClient, mock_db: AsyncMock, annotator_headers: dict
    ):
        resp = client.post(
            f"/api/v1/tasks/{uuid.uuid4()}/assign",
            json={"user_id": TEST_ANNOTATOR_ID},
            headers=annotator_headers,
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Submit task
# ---------------------------------------------------------------------------


class TestSubmitTask:
    def test_submit_assigned_task(
        self, client: TestClient, mock_db: AsyncMock, annotator_headers: dict
    ):
        task = make_task(status="assigned", assigned_to=TEST_ANNOTATOR_ID)
        mock_db.execute = _exec_returns(task)
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        resp = client.post(
            f"/api/v1/tasks/{task.id}/submit",
            headers=annotator_headers,
        )
        assert resp.status_code == 200
        assert task.status == "submitted"

    def test_submit_wrong_annotator_403(
        self, client: TestClient, mock_db: AsyncMock, annotator_headers: dict
    ):
        other_user_id = str(uuid.uuid4())
        task = make_task(status="assigned", assigned_to=other_user_id)
        mock_db.execute = _exec_returns(task)

        resp = client.post(
            f"/api/v1/tasks/{task.id}/submit",
            headers=annotator_headers,
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Approve task
# ---------------------------------------------------------------------------


class TestApproveTask:
    def test_approve_submitted_task(
        self, client: TestClient, mock_db: AsyncMock, reviewer_headers: dict
    ):
        task = make_task(status="submitted")
        mock_db.execute = _exec_returns(task)
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        resp = client.post(
            f"/api/v1/tasks/{task.id}/approve",
            headers=reviewer_headers,
        )
        assert resp.status_code == 200
        assert task.status == "approved"

    def test_approve_already_approved_409(
        self, client: TestClient, mock_db: AsyncMock, reviewer_headers: dict
    ):
        task = make_task(status="approved")
        mock_db.execute = _exc_returns_one(task)

        resp = client.post(
            f"/api/v1/tasks/{task.id}/approve",
            headers=reviewer_headers,
        )
        assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Workload listing
# ---------------------------------------------------------------------------


class TestUserWorkload:
    def test_list_annotators_with_workload(
        self, client: TestClient, mock_db: AsyncMock, auth_headers: dict
    ):
        user = make_user()

        users_result = MagicMock()
        users_result.scalars.return_value.all.return_value = [user]

        counts_result = MagicMock()
        counts_result.__iter__ = MagicMock(return_value=iter([(user.id, 3)]))

        mock_db.execute = AsyncMock(side_effect=[users_result, counts_result])

        resp = client.get(
            "/api/v1/users?role=annotator_internal&include_workload=true",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert "pending_task_count" in data[0]
        assert data[0]["pending_task_count"] == 3


# ---------------------------------------------------------------------------
# Helper — intentional typo alias to test invalid transitions
# ---------------------------------------------------------------------------


def _exc_returns_one(value):
    """Alias of _exec_returns for clarity in transition-failure tests."""
    return _exec_returns(value)
