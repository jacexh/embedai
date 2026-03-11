"""
RBAC Permission Tests for EmbedAI DataHub.

Rules tested:
- Annotators cannot approve/reject tasks (engineer/admin only)
- Engineers can approve/reject tasks
- Annotators cannot list users (engineer/admin only)
- Unauthenticated requests get 401
"""
from __future__ import annotations

import os

import httpx
import pytest

from .helpers import E2EClient

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8000")
TASK_SERVICE_URL = os.getenv("TASK_SERVICE_URL", "http://localhost:8002")
PROJECT_ID = os.getenv("E2E_PROJECT_ID", "36325736-7e34-4d32-a006-81bd20d50f04")


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

async def _login(email: str, password: str) -> tuple[str, str]:
    """Log in and return (token, user_id)."""
    async with httpx.AsyncClient(base_url=GATEWAY_URL, timeout=30.0) as client:
        resp = await client.post("/auth/login", json={"email": email, "password": password})
        resp.raise_for_status()
        body = resp.json()
        # Gateway login returns {"token": "...", "user": {"id": "...", ...}}
        token = body["token"]
        user_id = body["user"]["id"]
    return token, user_id


def _task_client(token: str) -> httpx.AsyncClient:
    """Return an AsyncClient pointed at the gateway's task API with auth."""
    return httpx.AsyncClient(
        base_url=GATEWAY_URL,
        headers={"Authorization": f"Bearer {token}"},
        timeout=30.0,
    )


async def _create_task(admin_token: str) -> str:
    """Create a task as admin and return its task_id."""
    async with _task_client(admin_token) as client:
        resp = await client.post(
            "/api/v1/tasks",
            json={"type": "video_annotation"},
        )
        assert resp.status_code == 201, f"Create task failed: {resp.text}"
    return resp.json()["id"]


async def _assign_task(admin_token: str, task_id: str, user_id: str) -> None:
    """Assign a task to the given user."""
    async with _task_client(admin_token) as client:
        resp = await client.post(
            f"/api/v1/tasks/{task_id}/assign",
            json={"user_id": user_id},
        )
        assert resp.status_code == 200, f"Assign task failed: {resp.text}"


async def _submit_task(token: str, task_id: str) -> None:
    """Submit a task (called by the assigned annotator)."""
    async with _task_client(token) as client:
        resp = await client.post(
            f"/api/v1/tasks/{task_id}/submit",
            json={"quality": "优质数据"},
        )
        assert resp.status_code == 200, f"Submit task failed: {resp.text}"


# ---------------------------------------------------------------------------
# Annotator permission tests
# ---------------------------------------------------------------------------

@pytest.mark.e2e
class TestRBACAnnotatorPermissions:
    async def test_annotator_cannot_approve_task(self) -> None:
        """Annotators must receive 403 when trying to approve a task."""
        admin_token, _ = await _login("admin@embedai.local", "Admin@2026!")
        annotator_token, annotator_id = await _login("annotator1@embedai.local", "Annotator@2026!")

        task_id = await _create_task(admin_token)
        await _assign_task(admin_token, task_id, annotator_id)
        await _submit_task(annotator_token, task_id)

        async with _task_client(annotator_token) as client:
            resp = await client.post(f"/api/v1/tasks/{task_id}/approve")

        assert resp.status_code == 403, (
            f"Expected 403 for annotator approve, got {resp.status_code}: {resp.text}"
        )

    async def test_annotator_cannot_reject_task(self) -> None:
        """Annotators must receive 403 when trying to reject a task."""
        admin_token, _ = await _login("admin@embedai.local", "Admin@2026!")
        annotator_token, annotator_id = await _login("annotator1@embedai.local", "Annotator@2026!")

        task_id = await _create_task(admin_token)
        await _assign_task(admin_token, task_id, annotator_id)
        await _submit_task(annotator_token, task_id)

        async with _task_client(annotator_token) as client:
            resp = await client.post(
                f"/api/v1/tasks/{task_id}/reject",
                json={"comment": "test rejection"},
            )

        assert resp.status_code == 403, (
            f"Expected 403 for annotator reject, got {resp.status_code}: {resp.text}"
        )

    async def test_annotator_cannot_list_users(self) -> None:
        """Annotators must receive 403 when listing users."""
        annotator_token, _ = await _login("annotator1@embedai.local", "Annotator@2026!")

        async with _task_client(annotator_token) as client:
            resp = await client.get("/api/v1/users")

        assert resp.status_code == 403, (
            f"Expected 403 for annotator list users, got {resp.status_code}: {resp.text}"
        )

    async def test_outsource_cannot_list_users(self) -> None:
        """Outsource users must receive 403 when listing users."""
        outsource_token, _ = await _login("outsource1@embedai.local", "Outsource@2026!")

        async with _task_client(outsource_token) as client:
            resp = await client.get("/api/v1/users")

        assert resp.status_code == 403, (
            f"Expected 403 for outsource list users, got {resp.status_code}: {resp.text}"
        )


# ---------------------------------------------------------------------------
# Engineer permission tests
# ---------------------------------------------------------------------------

@pytest.mark.e2e
class TestRBACEngineerPermissions:
    async def test_engineer_can_approve_task(self) -> None:
        """Engineers must be able to approve a submitted task."""
        admin_token, _ = await _login("admin@embedai.local", "Admin@2026!")
        engineer_token, _ = await _login("engineer@embedai.local", "Engineer@2026!")
        annotator_token, annotator_id = await _login("annotator1@embedai.local", "Annotator@2026!")

        task_id = await _create_task(admin_token)
        await _assign_task(admin_token, task_id, annotator_id)
        await _submit_task(annotator_token, task_id)

        async with _task_client(engineer_token) as client:
            resp = await client.post(f"/api/v1/tasks/{task_id}/approve")

        assert resp.status_code in (200, 204), (
            f"Expected 200/204 for engineer approve, got {resp.status_code}: {resp.text}"
        )

    async def test_engineer_can_list_users(self) -> None:
        """Engineers must be able to list users."""
        engineer_token, _ = await _login("engineer@embedai.local", "Engineer@2026!")

        async with _task_client(engineer_token) as client:
            resp = await client.get("/api/v1/users")

        assert resp.status_code == 200, (
            f"Expected 200 for engineer list users, got {resp.status_code}: {resp.text}"
        )


# ---------------------------------------------------------------------------
# Unauthenticated access tests
# ---------------------------------------------------------------------------

@pytest.mark.e2e
class TestRBACUnauthenticated:
    async def test_unauthenticated_cannot_access_episodes(self) -> None:
        """Requests without a token must get 401 on the episodes endpoint."""
        async with httpx.AsyncClient(base_url=GATEWAY_URL, timeout=30.0) as client:
            resp = await client.get("/api/v1/episodes")

        assert resp.status_code == 401, (
            f"Expected 401 for unauthenticated episodes, got {resp.status_code}: {resp.text}"
        )

    async def test_unauthenticated_cannot_access_tasks(self) -> None:
        """Requests without a token must get 401 on the tasks endpoint."""
        async with httpx.AsyncClient(base_url=GATEWAY_URL, timeout=30.0) as client:
            resp = await client.get("/api/v1/tasks")

        assert resp.status_code == 401, (
            f"Expected 401 for unauthenticated tasks, got {resp.status_code}: {resp.text}"
        )

    async def test_invalid_token_rejected(self) -> None:
        """A malformed/invalid JWT must yield 401."""
        async with httpx.AsyncClient(
            base_url=GATEWAY_URL,
            headers={"Authorization": "Bearer invalid.token.here"},
            timeout=30.0,
        ) as client:
            resp = await client.get("/api/v1/episodes")

        assert resp.status_code == 401, (
            f"Expected 401 for invalid token, got {resp.status_code}: {resp.text}"
        )
