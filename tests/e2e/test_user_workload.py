"""E2E tests — User workload / annotator list API.

Reproduces: GET /api/v1/users?role=annotator returns empty list because
DB roles are 'annotator_internal'/'annotator_outsource', not 'annotator'.
"""
from __future__ import annotations

import pytest

from .helpers import E2EClient


@pytest.mark.e2e
class TestAnnotatorList:
    async def test_list_annotators_returns_users(
        self, gateway_client: E2EClient
    ) -> None:
        """Frontend TasksPage calls ?role=annotator — must return annotator users.

        Seed data has annotator1@embedai.local (annotator_internal) and
        outsource1@embedai.local (annotator_outsource). Filtering by role=annotator
        should match both via prefix, not exact match.
        """
        resp = await gateway_client.task.get(
            "/api/v1/users?role=annotator&include_workload=true"
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        users = resp.json()
        assert len(users) > 0, (
            "BUG: ?role=annotator returned empty list. "
            "DB roles are 'annotator_internal'/'annotator_outsource' — "
            "backend must match by prefix, not exact string."
        )
        for u in users:
            assert "annotator" in u["role"], (
                f"Returned user {u['email']} has role {u['role']!r}, "
                "expected role containing 'annotator'"
            )
        assert "pending_task_count" in users[0], (
            f"Response missing 'pending_task_count': {users[0]}"
        )

    async def test_list_annotators_without_role_filter(
        self, gateway_client: E2EClient
    ) -> None:
        """Without role filter should return all active users in project."""
        resp = await gateway_client.task.get("/api/v1/users")
        assert resp.status_code == 200
        users = resp.json()
        assert len(users) > 0, "No users returned without filter"

    async def test_list_annotators_exact_role_still_works(
        self, gateway_client: E2EClient
    ) -> None:
        """Exact role 'annotator_internal' should still work as before."""
        resp = await gateway_client.task.get(
            "/api/v1/users?role=annotator_internal&include_workload=true"
        )
        assert resp.status_code == 200
        users = resp.json()
        assert len(users) > 0, "No annotator_internal users returned"
        for u in users:
            assert u["role"] == "annotator_internal"
