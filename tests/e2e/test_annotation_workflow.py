"""E2E tests for the complete annotation workflow.

Covers the full journey:
  Task CREATED → ASSIGNED → SUBMITTED → REJECTED → re-ASSIGNED → re-SUBMITTED → APPROVED

And verifies that the approved state is terminal and cannot be further modified.
"""
from __future__ import annotations

import pytest

from .helpers import E2EClient

import httpx

GATEWAY_URL = "http://localhost:8000"
TASK_SERVICE_URL = "http://localhost:8002"


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


@pytest.mark.e2e
class TestAnnotationResult:
    """Submit stores annotation_result; validation; re-submission overwrites."""

    async def test_submit_with_quality_stores_annotation_result(
        self, gateway_client: E2EClient
    ) -> None:
        # Create and assign task
        task_id = await _create_task(gateway_client)
        resp = await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/assign",
            json={"user_id": gateway_client.user_id},
        )
        assert resp.status_code == 200

        # Submit with quality + notes
        resp = await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/submit",
            json={"quality": "优质数据", "notes": "clean sensor data"},
        )
        assert resp.status_code == 200, f"Submit failed: {resp.text}"
        body = resp.json()
        assert body["status"] == "submitted"
        assert body["annotation_result"] is not None
        assert body["annotation_result"]["quality"] == "优质数据"
        assert body["annotation_result"]["notes"] == "clean sensor data"

    async def test_submit_without_notes_stores_null_notes(
        self, gateway_client: E2EClient
    ) -> None:
        task_id = await _create_task(gateway_client)
        await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/assign",
            json={"user_id": gateway_client.user_id},
        )
        resp = await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/submit",
            json={"quality": "可用数据"},
        )
        assert resp.status_code == 200
        assert resp.json()["annotation_result"]["quality"] == "可用数据"
        assert resp.json()["annotation_result"]["notes"] is None

    async def test_submit_missing_quality_returns_422(
        self, gateway_client: E2EClient
    ) -> None:
        task_id = await _create_task(gateway_client)
        await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/assign",
            json={"user_id": gateway_client.user_id},
        )
        resp = await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/submit",
            json={},
        )
        assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"

    async def test_submit_invalid_quality_returns_422(
        self, gateway_client: E2EClient
    ) -> None:
        task_id = await _create_task(gateway_client)
        await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/assign",
            json={"user_id": gateway_client.user_id},
        )
        resp = await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/submit",
            json={"quality": "bad_value"},
        )
        assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"

    async def test_submit_no_body_returns_422(
        self, gateway_client: E2EClient
    ) -> None:
        task_id = await _create_task(gateway_client)
        await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/assign",
            json={"user_id": gateway_client.user_id},
        )
        resp = await gateway_client.task.post(f"/api/v1/tasks/{task_id}/submit")
        assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"

    async def test_rejected_task_can_resubmit_directly(
        self, gateway_client: E2EClient
    ) -> None:
        # Create → assign → submit → reject
        task_id = await _create_task(gateway_client)
        await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/assign",
            json={"user_id": gateway_client.user_id},
        )
        await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/submit",
            json={"quality": "可用数据"},
        )
        resp = await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/reject",
            json={"comment": "needs correction"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected"

        # Re-submit directly from rejected (no re-assign needed)
        resp = await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/submit",
            json={"quality": "优质数据", "notes": "corrected"},
        )
        assert resp.status_code == 200, f"Re-submit from rejected failed: {resp.text}"
        body = resp.json()
        assert body["status"] == "submitted"
        assert body["annotation_result"]["quality"] == "优质数据"
        assert body["annotation_result"]["notes"] == "corrected"

    async def test_resubmit_overwrites_annotation_result(
        self, gateway_client: E2EClient
    ) -> None:
        # submit with quality A, reject, re-submit with quality B
        task_id = await _create_task(gateway_client)
        await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/assign",
            json={"user_id": gateway_client.user_id},
        )
        await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/submit",
            json={"quality": "问题数据", "notes": "first attempt"},
        )
        await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/reject",
            json={"comment": "fix it"},
        )
        await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/submit",
            json={"quality": "优质数据", "notes": "second attempt"},
        )

        # Verify via GET that result is overwritten
        resp = await gateway_client.task.get(f"/api/v1/tasks/{task_id}")
        assert resp.status_code == 200
        result = resp.json()["annotation_result"]
        assert result["quality"] == "优质数据", f"Expected 优质数据, got {result['quality']}"
        assert result["notes"] == "second attempt"

    async def test_submitted_task_cannot_resubmit(
        self, gateway_client: E2EClient
    ) -> None:
        """Spec item 7: submitted → submitted is blocked (409 from state machine)."""
        task_id = await _create_task(gateway_client)
        await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/assign",
            json={"user_id": gateway_client.user_id},
        )
        await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/submit",
            json={"quality": "优质数据"},
        )
        resp = await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/submit",
            json={"quality": "可用数据"},
        )
        assert resp.status_code == 409, (
            f"Expected 409 (state machine) resubmitting a submitted task, got {resp.status_code}: {resp.text}"
        )

    async def test_approved_task_cannot_submit(
        self, gateway_client: E2EClient
    ) -> None:
        """Spec item 8: approved → submitted is blocked (409 from state machine)."""
        task_id = await _create_task(gateway_client)
        await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/assign",
            json={"user_id": gateway_client.user_id},
        )
        await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/submit",
            json={"quality": "优质数据"},
        )
        await gateway_client.task.post(f"/api/v1/tasks/{task_id}/approve")
        resp = await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/submit",
            json={"quality": "可用数据"},
        )
        assert resp.status_code == 409, (
            f"Expected 409 (state machine) submitting an approved task, got {resp.status_code}: {resp.text}"
        )

    async def test_annotator_cannot_submit_others_task(
        self, gateway_client: E2EClient
    ) -> None:
        """Spec item 9: annotator submitting another user's task gets 403."""
        import uuid as _uuid

        project_id = gateway_client.project_id
        unique = _uuid.uuid4().hex[:8]

        # Register a second annotator user
        async with httpx.AsyncClient(base_url=GATEWAY_URL, timeout=30.0) as raw:
            resp = await raw.post(
                "/auth/register",
                json={
                    "email": f"annotator2_{unique}@test.local",
                    "password": "ann_pass_123",
                    "name": f"Annotator Two {unique}",
                    "role": "annotator",
                    "project_id": project_id,
                },
            )
            assert resp.status_code in (200, 201), f"Register failed: {resp.text}"
            resp2 = await raw.post(
                "/auth/login",
                json={"email": f"annotator2_{unique}@test.local", "password": "ann_pass_123"},
            )
            assert resp2.status_code == 200
            token2 = resp2.json()["token"]

        # Create task and assign to gateway_client (admin user)
        task_id = await _create_task(gateway_client)
        resp = await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/assign",
            json={"user_id": gateway_client.user_id},
        )
        assert resp.status_code == 200

        # Try to submit as annotator2 — should get 403
        headers2 = {"Authorization": f"Bearer {token2}"}
        async with httpx.AsyncClient(
            base_url=TASK_SERVICE_URL, headers=headers2, timeout=30.0
        ) as ts2:
            resp = await ts2.post(
                f"/api/v1/tasks/{task_id}/submit",
                json={"quality": "优质数据"},
            )
        assert resp.status_code == 403, (
            f"Expected 403 when annotator submits another's task, got {resp.status_code}: {resp.text}"
        )

    async def test_rejected_to_assigned_still_valid(
        self, gateway_client: E2EClient
    ) -> None:
        # Engineer can still re-assign a rejected task
        task_id = await _create_task(gateway_client)
        await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/assign",
            json={"user_id": gateway_client.user_id},
        )
        await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/submit",
            json={"quality": "可用数据"},
        )
        await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/reject",
            json={"comment": "redo"},
        )
        resp = await gateway_client.task.post(
            f"/api/v1/tasks/{task_id}/assign",
            json={"user_id": gateway_client.user_id},
        )
        assert resp.status_code == 200, f"Re-assign from rejected failed: {resp.text}"
        assert resp.json()["status"] == "assigned"
