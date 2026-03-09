"""Tests for Label Studio webhook endpoint — Task 5.1."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine.result import ChunkedIteratorResult

from tests.conftest import TEST_PROJECT_ID, TEST_USER_ID, make_task, make_user


def _mock_scalar_one_or_none(value):
    """Return an AsyncMock whose scalar_one_or_none() returns value."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    mock_exec = AsyncMock(return_value=result)
    return mock_exec


class TestLSWebhook:
    def test_annotation_created_updates_task(
        self, client: TestClient, mock_db: AsyncMock, auth_headers: dict
    ):
        task = make_task(status="assigned", ls_task_id=42)

        # First execute call: find task by ls_task_id
        # Second execute call: find existing annotation (none)
        task_result = MagicMock()
        task_result.scalar_one_or_none.return_value = task

        anno_result = MagicMock()
        anno_result.scalar_one_or_none.return_value = None

        mock_db.execute = AsyncMock(side_effect=[task_result, anno_result])
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()

        payload = {
            "action": "ANNOTATION_CREATED",
            "annotation": {
                "id": 99,
                "task": 42,
                "result": [{"from_name": "label", "value": {"labels": ["robot_arm"]}}],
                "completed_by": 5,
            },
        }
        resp = client.post("/api/v1/webhooks/label-studio", json=payload)
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        assert resp.json()["task_id"] == str(task.id)

        # Task status should be updated to submitted
        assert task.status == "submitted"

    def test_unknown_action_is_ignored(self, client: TestClient, mock_db: AsyncMock):
        payload = {"action": "PROJECT_CREATED", "project": {"id": 1}}
        resp = client.post("/api/v1/webhooks/label-studio", json=payload)
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"

    def test_unknown_ls_task_id_is_ignored(
        self, client: TestClient, mock_db: AsyncMock
    ):
        task_result = MagicMock()
        task_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=task_result)

        payload = {
            "action": "ANNOTATION_CREATED",
            "annotation": {"id": 1, "task": 9999, "result": [], "completed_by": 1},
        }
        resp = client.post("/api/v1/webhooks/label-studio", json=payload)
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"

    def test_missing_annotation_returns_422(self, client: TestClient, mock_db: AsyncMock):
        payload = {"action": "ANNOTATION_CREATED"}
        resp = client.post("/api/v1/webhooks/label-studio", json=payload)
        assert resp.status_code == 422
