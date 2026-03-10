"""E2E tests — Annotation Tasks API.

Covers: create, list, get, assign, submit, approve, reject, user workload.
"""
from __future__ import annotations

import pytest

from .helpers import E2EClient


_DUMMY_EPISODE_ID = "00000000-0000-0000-0000-000000000099"


async def _make_task(client: E2EClient, task_type: str = "video_annotation") -> str:
    """Create a task and return its task_id."""
    resp = await client.task.post(
        "/api/v1/tasks",
        json={"type": task_type, "episode_id": _DUMMY_EPISODE_ID},
    )
    assert resp.status_code == 201, f"Create task ({task_type}) failed: {resp.text}"
    return resp.json()["id"]


@pytest.mark.e2e
class TestTaskCreate:
    async def test_create_task_video_annotation(
        self, gateway_client: E2EClient
    ) -> None:
        """Frontend useCreateTask sends type='video_annotation' with episode_id."""
        resp = await gateway_client.task.post(
            "/api/v1/tasks",
            json={"type": "video_annotation", "episode_id": _DUMMY_EPISODE_ID},
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
class TestTaskStateMachineBoundaries:
    """Edge cases and invalid transitions for the annotation task state machine."""

    async def test_cannot_reject_created_task(self, gateway_client: E2EClient) -> None:
        """CREATED → REJECTED is not a valid transition."""
        task_id = await _make_task(gateway_client)
        resp = await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/reject",
            json={"comment": "bad task"},
        )
        assert resp.status_code in (400, 409, 422), (
            f"Expected error rejecting a created task, got {resp.status_code}: {resp.text}"
        )

    async def test_reject_comment_is_optional(self, gateway_client: E2EClient) -> None:
        """RejectRequest.comment field is Optional[str] — empty body {} must succeed."""
        task_id = await _make_task(gateway_client)
        await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/assign",
            json={"user_id": gateway_client.user_id},
        )
        await gateway_client.task.post(f"/api/v1/tasks/{task_id}/submit")

        # Send {} — body is required by FastAPI, but comment inside is optional
        resp = await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/reject",
            json={},
        )
        assert resp.status_code == 200, (
            f"Reject with empty body {{}} should succeed (comment is optional), "
            f"got {resp.status_code}: {resp.text}"
        )
        assert resp.json()["status"] == "rejected"

    async def test_assign_to_invalid_uuid_returns_422(
        self, gateway_client: E2EClient
    ) -> None:
        """Assigning to a non-UUID string must be rejected with 422 (Pydantic validation)."""
        task_id = await _make_task(gateway_client)
        resp = await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/assign",
            json={"user_id": "not-a-uuid"},
        )
        assert resp.status_code == 422, (
            f"Expected 422 for invalid user_id UUID, got {resp.status_code}: {resp.text}"
        )

    async def test_approved_task_cannot_be_rejected(
        self, gateway_client: E2EClient
    ) -> None:
        """APPROVED is a terminal state — cannot transition to REJECTED."""
        task_id = await _make_task(gateway_client)
        await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/assign",
            json={"user_id": gateway_client.user_id},
        )
        await gateway_client.task.post(f"/api/v1/tasks/{task_id}/submit")
        resp = await gateway_client.task.post(f"/api/v1/tasks/{task_id}/approve")
        assert resp.status_code == 200, f"Approve failed: {resp.text}"

        resp = await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/reject",
            json={"comment": "too late"},
        )
        assert resp.status_code in (400, 409, 422), (
            f"Expected error rejecting an approved task, got {resp.status_code}: {resp.text}"
        )

    async def test_approved_task_cannot_be_submitted_again(
        self, gateway_client: E2EClient
    ) -> None:
        """APPROVED is a terminal state — cannot re-submit."""
        task_id = await _make_task(gateway_client)
        await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/assign",
            json={"user_id": gateway_client.user_id},
        )
        await gateway_client.task.post(f"/api/v1/tasks/{task_id}/submit")
        await gateway_client.task.post(f"/api/v1/tasks/{task_id}/approve")

        resp = await gateway_client.task.post(f"/api/v1/tasks/{task_id}/submit")
        assert resp.status_code in (400, 409, 422), (
            f"Expected error re-submitting an approved task, got {resp.status_code}: {resp.text}"
        )

    async def test_reject_and_reassign_cycle(self, gateway_client: E2EClient) -> None:
        """After reject, task goes back to 'rejected'; re-assigning then re-submitting
        must succeed and the final status must be 'submitted'."""
        task_id = await _make_task(gateway_client)
        await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/assign",
            json={"user_id": gateway_client.user_id},
        )
        await gateway_client.task.post(f"/api/v1/tasks/{task_id}/submit")
        resp = await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/reject",
            json={"comment": "needs rework"},
        )
        assert resp.status_code == 200, f"Reject failed: {resp.text}"
        assert resp.json()["status"] == "rejected"

        # Re-assign (rejected → assigned per state machine)
        resp = await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/assign",
            json={"user_id": gateway_client.user_id},
        )
        assert resp.status_code == 200, f"Re-assign failed: {resp.text}"
        assert resp.json()["status"] == "assigned"

        # Re-submit
        resp = await gateway_client.task.post(f"/api/v1/tasks/{task_id}/submit")
        assert resp.status_code == 200, f"Re-submit failed: {resp.text}"
        assert resp.json()["status"] == "submitted"

    async def test_task_list_filter_by_status_submitted(
        self, gateway_client: E2EClient
    ) -> None:
        """GET /tasks?status=submitted returns only submitted tasks."""
        task_id = await _make_task(gateway_client)
        await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/assign",
            json={"user_id": gateway_client.user_id},
        )
        await gateway_client.task.post(f"/api/v1/tasks/{task_id}/submit")

        resp = await gateway_client.task.get("/api/v1/tasks?status=submitted")
        assert resp.status_code == 200, f"List submitted tasks failed: {resp.text}"
        tasks = resp.json()
        assert isinstance(tasks, list)
        assert any(t["id"] == task_id for t in tasks), (
            f"Submitted task {task_id} not found in filtered list"
        )
        for t in tasks:
            assert t["status"] == "submitted", (
                f"Task {t['id']} has unexpected status {t['status']!r}"
            )

    async def test_task_list_unknown_status_returns_empty(
        self, gateway_client: E2EClient
    ) -> None:
        """Filtering by a nonexistent status must return empty list, not an error."""
        resp = await gateway_client.task.get(
            "/api/v1/tasks?status=nonexistent_status_xyz"
        )
        assert resp.status_code == 200, (
            f"Expected 200 for unknown status filter, got {resp.status_code}: {resp.text}"
        )
        assert resp.json() == [], (
            f"Expected empty list for unknown status, got: {resp.json()}"
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
