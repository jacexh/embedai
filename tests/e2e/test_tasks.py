"""E2E tests — Annotation Tasks API.

Covers: create, list, get, assign, submit, approve, reject, user workload.
"""
from __future__ import annotations

import pytest

from .helpers import E2EClient


async def _make_task(client: E2EClient, task_type: str = "video_annotation") -> str:
    """Create a task and return its task_id."""
    resp = await client.task.post(
        "/api/v1/tasks",
        json={"type": task_type},
    )
    assert resp.status_code == 201, f"Create task ({task_type}) failed: {resp.text}"
    return resp.json()["id"]


@pytest.mark.e2e
class TestTaskCreate:
    async def test_create_task_video_annotation(
        self, gateway_client: E2EClient
    ) -> None:
        """Frontend useCreateTask sends type='video_annotation'."""
        resp = await gateway_client.task.post(
            "/api/v1/tasks",
            json={"type": "video_annotation"},
        )
        assert resp.status_code == 201, (
            f"Create video_annotation task failed: {resp.text}"
        )
        body = resp.json()
        assert "id" in body
        assert body["status"] == "created"
        assert body["type"] == "video_annotation"

    async def test_create_task_with_episode_id(
        self, gateway_client: E2EClient
    ) -> None:
        """Frontend useCreateTask passes episode_id."""
        resp = await gateway_client.task.post(
            "/api/v1/tasks",
            json={
                "type": "video_annotation",
                "episode_id": "00000000-0000-0000-0000-000000000001",
            },
        )
        # Either 201 or 404 (episode not found) — not 422 or 500
        assert resp.status_code in (201, 404), (
            f"Create task with episode_id got unexpected {resp.status_code}: {resp.text}"
        )

    async def test_create_task_missing_type_returns_422(
        self, gateway_client: E2EClient
    ) -> None:
        resp = await gateway_client.task.post("/api/v1/tasks", json={})
        assert resp.status_code == 422, (
            f"Expected 422 for missing type, got {resp.status_code}: {resp.text}"
        )

    async def test_task_response_schema(self, gateway_client: E2EClient) -> None:
        task_id = await _make_task(gateway_client)
        resp = await gateway_client.task.get(f"/api/v1/tasks/{task_id}")
        assert resp.status_code == 200
        body = resp.json()
        required = [
            "id", "status", "type", "project_id",
            "assigned_to", "created_at", "updated_at",
        ]
        for field in required:
            assert field in body, f"Task response missing '{field}': {body}"


@pytest.mark.e2e
class TestTaskList:
    async def test_list_tasks_returns_list(self, gateway_client: E2EClient) -> None:
        resp = await gateway_client.task.get("/api/v1/tasks")
        assert resp.status_code == 200, f"List tasks failed: {resp.text}"
        assert isinstance(resp.json(), list), f"Expected list, got: {resp.json()}"

    async def test_list_tasks_filter_by_status(
        self, gateway_client: E2EClient
    ) -> None:
        resp = await gateway_client.task.get("/api/v1/tasks?status=created")
        assert resp.status_code == 200
        for task in resp.json():
            assert task["status"] == "created", (
                f"Task {task['id']} has status {task['status']!r}, expected 'created'"
            )

    async def test_list_tasks_filter_by_assigned_to(
        self, gateway_client: E2EClient
    ) -> None:
        resp = await gateway_client.task.get(
            f"/api/v1/tasks?assigned_to={gateway_client.user_id}"
        )
        assert resp.status_code == 200


@pytest.mark.e2e
class TestTaskLifecycle:
    async def test_assign_task(self, gateway_client: E2EClient) -> None:
        task_id = await _make_task(gateway_client)

        resp = await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/assign",
            json={"user_id": gateway_client.user_id},
        )
        assert resp.status_code == 200, f"Assign task failed: {resp.text}"
        assert resp.json()["status"] == "assigned"
        assert resp.json()["assigned_to"] == gateway_client.user_id

    async def test_submit_task(self, gateway_client: E2EClient) -> None:
        task_id = await _make_task(gateway_client)
        await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/assign",
            json={"user_id": gateway_client.user_id},
        )

        resp = await gateway_client.task.post(f"/api/v1/tasks/{task_id}/submit")
        assert resp.status_code == 200, f"Submit task failed: {resp.text}"
        assert resp.json()["status"] == "submitted"

    async def test_approve_task(self, gateway_client: E2EClient) -> None:
        task_id = await _make_task(gateway_client)
        await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/assign",
            json={"user_id": gateway_client.user_id},
        )
        await gateway_client.task.post(f"/api/v1/tasks/{task_id}/submit")

        resp = await gateway_client.task.post(f"/api/v1/tasks/{task_id}/approve")
        assert resp.status_code == 200, f"Approve task failed: {resp.text}"
        assert resp.json()["status"] == "approved"

    async def test_reject_task(self, gateway_client: E2EClient) -> None:
        task_id = await _make_task(gateway_client)
        await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/assign",
            json={"user_id": gateway_client.user_id},
        )
        await gateway_client.task.post(f"/api/v1/tasks/{task_id}/submit")

        resp = await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/reject",
            json={"comment": "需要重新标注"},
        )
        assert resp.status_code == 200, f"Reject task failed: {resp.text}"
        assert resp.json()["status"] == "rejected"

    async def test_invalid_transition_raises_error(
        self, gateway_client: E2EClient
    ) -> None:
        """Cannot submit a task that hasn't been assigned."""
        task_id = await _make_task(gateway_client)

        resp = await gateway_client.task.post(f"/api/v1/tasks/{task_id}/submit")
        assert resp.status_code in (400, 409, 422), (
            f"Expected error for invalid transition (created→submitted), "
            f"got {resp.status_code}: {resp.text}"
        )

    async def test_cannot_approve_without_submission(
        self, gateway_client: E2EClient
    ) -> None:
        task_id = await _make_task(gateway_client)

        resp = await gateway_client.task.post(f"/api/v1/tasks/{task_id}/approve")
        assert resp.status_code in (400, 409, 422), (
            f"Expected error for invalid transition (created→approved), "
            f"got {resp.status_code}: {resp.text}"
        )

    async def test_get_nonexistent_task_returns_404(
        self, gateway_client: E2EClient
    ) -> None:
        resp = await gateway_client.task.get(
            "/api/v1/tasks/00000000-0000-0000-0000-000000000000"
        )
        assert resp.status_code == 404, (
            f"Expected 404 for nonexistent task, got {resp.status_code}: {resp.text}"
        )


@pytest.mark.e2e
class TestUserWorkload:
    async def test_list_users_with_workload(self, gateway_client: E2EClient) -> None:
        """Frontend useAnnotatorsWithWorkload: GET /api/v1/users?role=annotator&include_workload=true."""
        resp = await gateway_client.task.get(
            "/api/v1/users?role=annotator&include_workload=true"
        )
        assert resp.status_code == 200, f"List users failed: {resp.text}"
        users = resp.json()
        assert isinstance(users, list)
        for user in users:
            assert "pending_task_count" in user, (
                f"User workload missing 'pending_task_count': {user}"
            )
