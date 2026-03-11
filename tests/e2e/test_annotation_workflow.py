"""E2E tests for the complete annotation workflow.

Covers the full journey:
  Task CREATED → ASSIGNED → SUBMITTED → REJECTED → re-ASSIGNED → re-SUBMITTED → APPROVED

And verifies that the approved state is terminal and cannot be further modified.
"""
from __future__ import annotations

import pytest

from .helpers import E2EClient


async def _create_task(client: E2EClient, task_type: str = "bbox2d") -> str:
    """Create a task and return its task_id."""
    resp = await client.task.post(
        "/api/v1/tasks",
        json={"type": task_type, "episode_id": "00000000-0000-0000-0000-000000000099"},
    )
    assert resp.status_code == 201, f"Create task ({task_type}) failed: {resp.text}"
    return resp.json()["id"]


async def _run_full_approve(client: E2EClient, task_id: str) -> None:
    """Drive a task through the full approve path: assign → submit → approve."""
    resp = await client.task.post(
        f"/api/v1/tasks/{task_id}/assign",
        json={"user_id": client.user_id},
    )
    assert resp.status_code == 200, f"Assign failed: {resp.text}"

    resp = await client.task.post(
        f"/api/v1/tasks/{task_id}/submit",
        json={"quality": "优质数据"},
    )
    assert resp.status_code == 200, f"Submit failed: {resp.text}"

    resp = await client.task.post(f"/api/v1/tasks/{task_id}/approve")
    assert resp.status_code == 200, f"Approve failed: {resp.text}"


@pytest.mark.e2e
class TestFullApproveWorkflow:
    """Complete happy-path: CREATED → ASSIGNED → SUBMITTED → APPROVED."""

    async def test_full_approve_workflow(self, gateway_client: E2EClient) -> None:
        # Step 1 — Create task
        resp = await gateway_client.task.post(
            "/api/v1/tasks",
            json={"type": "bbox2d", "episode_id": "00000000-0000-0000-0000-000000000099"},
        )
        assert resp.status_code == 201, f"Create task failed: {resp.text}"
        body = resp.json()
        task_id = body["id"]

        # Step 2 — Verify initial status
        assert body["status"] == "created", (
            f"Expected status='created' after creation, got {body['status']!r}"
        )

        # Step 3 — Assign to self
        resp = await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/assign",
            json={"user_id": gateway_client.user_id},
        )
        assert resp.status_code == 200, f"Assign failed: {resp.text}"
        body = resp.json()

        # Step 4 — Verify assigned state
        assert body["status"] == "assigned", (
            f"Expected status='assigned' after assign, got {body['status']!r}"
        )
        assert body["assigned_to"] == gateway_client.user_id, (
            f"Expected assigned_to={gateway_client.user_id!r}, got {body['assigned_to']!r}"
        )

        # Step 5 — Submit
        resp = await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/submit",
            json={"quality": "优质数据"},
        )
        assert resp.status_code == 200, f"Submit failed: {resp.text}"

        # Step 6 — Verify submitted state
        assert resp.json()["status"] == "submitted", (
            f"Expected status='submitted' after submit, got {resp.json()['status']!r}"
        )

        # Step 7 — Approve
        resp = await gateway_client.task.post(f"/api/v1/tasks/{task_id}/approve")
        assert resp.status_code == 200, f"Approve failed: {resp.text}"

        # Step 8 — Verify approved state from response
        assert resp.json()["status"] == "approved", (
            f"Expected status='approved' after approve, got {resp.json()['status']!r}"
        )

        # Step 9 — Verify persisted via GET
        resp = await gateway_client.task.get(f"/api/v1/tasks/{task_id}")
        assert resp.status_code == 200, f"GET task failed: {resp.text}"
        assert resp.json()["status"] == "approved", (
            f"GET /tasks/{{id}} shows status {resp.json()['status']!r}, expected 'approved'"
        )


@pytest.mark.e2e
class TestRejectionAndReworkCycle:
    """Full rejection-rework cycle ending in APPROVED, with terminal state check."""

    async def test_full_rejection_and_rework_cycle(
        self, gateway_client: E2EClient
    ) -> None:
        # Step 1 — Create → assign → submit
        task_id = await _create_task(gateway_client)

        resp = await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/assign",
            json={"user_id": gateway_client.user_id},
        )
        assert resp.status_code == 200, f"Initial assign failed: {resp.text}"

        resp = await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/submit",
            json={"quality": "可用数据"},
        )
        assert resp.status_code == 200, f"Initial submit failed: {resp.text}"

        # Step 2 — Reject with a descriptive comment
        resp = await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/reject",
            json={"comment": "bbox coordinates off"},
        )
        assert resp.status_code == 200, f"Reject failed: {resp.text}"

        # Step 3 — Verify rejected status
        assert resp.json()["status"] == "rejected", (
            f"Expected status='rejected' after reject, got {resp.json()['status']!r}"
        )

        # Step 4 — Re-assign (rejected → assigned per state machine)
        resp = await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/assign",
            json={"user_id": gateway_client.user_id},
        )
        assert resp.status_code == 200, f"Re-assign failed: {resp.text}"

        # Step 5 — Verify re-assigned status
        assert resp.json()["status"] == "assigned", (
            f"Expected status='assigned' after re-assign, got {resp.json()['status']!r}"
        )

        # Step 6 — Re-submit
        resp = await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/submit",
            json={"quality": "优质数据"},
        )
        assert resp.status_code == 200, f"Re-submit failed: {resp.text}"

        # Step 7 — Verify re-submitted status
        assert resp.json()["status"] == "submitted", (
            f"Expected status='submitted' after re-submit, got {resp.json()['status']!r}"
        )

        # Step 8 — Approve
        resp = await gateway_client.task.post(f"/api/v1/tasks/{task_id}/approve")
        assert resp.status_code == 200, f"Final approve failed: {resp.text}"

        # Step 9 — Verify final approved status
        assert resp.json()["status"] == "approved", (
            f"Expected final status='approved', got {resp.json()['status']!r}"
        )

        # Step 10 — Verify approved is terminal: re-submitting must fail
        resp = await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/submit",
            json={"quality": "优质数据"},
        )
        assert resp.status_code in (400, 409, 422), (
            f"Expected error trying to submit an approved task (terminal state), "
            f"got {resp.status_code}: {resp.text}"
        )


@pytest.mark.e2e
class TestTaskToDatasetVersionPipeline:
    """End-to-end pipeline: approved task feeds a new immutable dataset version."""

    async def test_task_to_dataset_version_pipeline(
        self, gateway_client: E2EClient
    ) -> None:
        # Step 1 — Create a task and run the full approve workflow
        task_id = await _create_task(gateway_client)
        await _run_full_approve(gateway_client, task_id)

        # Confirm task is approved before proceeding
        resp = await gateway_client.task.get(f"/api/v1/tasks/{task_id}")
        assert resp.status_code == 200, f"GET task failed: {resp.text}"
        assert resp.json()["status"] == "approved", (
            f"Task must be approved before creating a dataset version, "
            f"got status={resp.json()['status']!r}"
        )

        # Step 2 — Create a dataset
        resp = await gateway_client.dataset.post(
            "/api/v1/datasets",
            json={"name": "approved-data-test", "description": "Linked to approved task"},
        )
        assert resp.status_code == 201, f"Create dataset failed: {resp.text}"
        dataset_id = resp.json()["id"]
        assert dataset_id, "Dataset id must not be empty"

        # Step 3 — Create a version (empty refs — no real episodes in test env)
        resp = await gateway_client.dataset.post(
            f"/api/v1/datasets/{dataset_id}/versions",
            json={"version_tag": "v1.0.0", "episode_refs": []},
        )
        assert resp.status_code == 201, f"Create dataset version failed: {resp.text}"
        version_body = resp.json()

        # Step 4 — Verify version is immutable
        assert version_body.get("is_immutable") is True, (
            f"Dataset version should be immutable on creation: {version_body}"
        )

        # Step 5 — Verify version_tag matches
        assert version_body.get("version_tag") == "v1.0.0", (
            f"Expected version_tag='v1.0.0', got {version_body.get('version_tag')!r}"
        )

        # Step 6 — Verify the complete pipeline: task approved + dataset version created
        resp = await gateway_client.task.get(f"/api/v1/tasks/{task_id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "approved", (
            "Task approval must persist throughout the dataset version creation step"
        )
        assert version_body.get("id"), "Dataset version id must not be empty"
