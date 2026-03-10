"""E2E tests — Episodes API.

Covers: list (with filters), get detail, stream token, delete.

Known bugs being detected:
- [BUG-1] DELETE /api/v1/episodes/{id} — backend may not implement this endpoint
"""
from __future__ import annotations

import pytest

from .helpers import E2EClient


@pytest.mark.e2e
class TestEpisodeList:
    async def test_list_episodes_returns_paginated_response(
        self, gateway_client: E2EClient
    ) -> None:
        resp = await gateway_client.dataset.get("/api/v1/episodes")
        assert resp.status_code == 200, f"List episodes failed: {resp.text}"
        body = resp.json()
        assert "items" in body, f"Response missing 'items': {body}"
        assert "total" in body, f"Response missing 'total': {body}"
        assert "limit" in body, f"Response missing 'limit': {body}"
        assert "offset" in body, f"Response missing 'offset': {body}"
        assert isinstance(body["items"], list)

    async def test_list_episodes_filter_by_status(
        self, gateway_client: E2EClient
    ) -> None:
        resp = await gateway_client.dataset.get("/api/v1/episodes?status=ready")
        assert resp.status_code == 200, f"Filter by status failed: {resp.text}"
        body = resp.json()
        for ep in body["items"]:
            assert ep["status"] == "ready", (
                f"Episode {ep['id']} has status {ep['status']!r}, expected 'ready'"
            )

    async def test_list_episodes_filter_by_format(
        self, gateway_client: E2EClient
    ) -> None:
        resp = await gateway_client.dataset.get("/api/v1/episodes?format=mcap")
        assert resp.status_code == 200, f"Filter by format failed: {resp.text}"
        body = resp.json()
        for ep in body["items"]:
            assert ep["format"] == "mcap", (
                f"Episode {ep['id']} has format {ep['format']!r}, expected 'mcap'"
            )

    async def test_list_episodes_filter_by_min_quality(
        self, gateway_client: E2EClient
    ) -> None:
        resp = await gateway_client.dataset.get("/api/v1/episodes?min_quality=0.5")
        assert resp.status_code == 200, f"Filter by min_quality failed: {resp.text}"
        body = resp.json()
        for ep in body["items"]:
            if ep["quality_score"] is not None:
                assert ep["quality_score"] >= 0.5, (
                    f"Episode {ep['id']} quality {ep['quality_score']} < 0.5"
                )

    async def test_list_episodes_pagination(
        self, gateway_client: E2EClient
    ) -> None:
        page1 = await gateway_client.dataset.get("/api/v1/episodes?limit=2&offset=0")
        page2 = await gateway_client.dataset.get("/api/v1/episodes?limit=2&offset=2")
        assert page1.status_code == 200
        assert page2.status_code == 200

        ids1 = {ep["id"] for ep in page1.json()["items"]}
        ids2 = {ep["id"] for ep in page2.json()["items"]}
        if ids1 and ids2:
            assert not ids1.intersection(ids2), "Paginated pages share episode IDs"

    async def test_list_episodes_invalid_status_returns_422_or_empty(
        self, gateway_client: E2EClient
    ) -> None:
        resp = await gateway_client.dataset.get("/api/v1/episodes?status=invalid_status")
        # Should either 422 (strict validation) or 200 with empty list (lenient)
        assert resp.status_code in (200, 422), (
            f"Unexpected status {resp.status_code}: {resp.text}"
        )


@pytest.mark.e2e
class TestEpisodeDetail:
    async def test_get_nonexistent_episode_returns_404(
        self, gateway_client: E2EClient
    ) -> None:
        resp = await gateway_client.dataset.get(
            "/api/v1/episodes/00000000-0000-0000-0000-000000000000"
        )
        assert resp.status_code == 404, (
            f"Expected 404 for nonexistent episode, got {resp.status_code}: {resp.text}"
        )

    async def test_get_episode_detail_includes_topics(
        self, gateway_client: E2EClient
    ) -> None:
        """If any episodes exist, verify detail includes topics list."""
        list_resp = await gateway_client.dataset.get("/api/v1/episodes?limit=1")
        assert list_resp.status_code == 200
        items = list_resp.json()["items"]
        if not items:
            pytest.skip("No episodes available to test detail")

        episode_id = items[0]["id"]
        resp = await gateway_client.dataset.get(f"/api/v1/episodes/{episode_id}")
        assert resp.status_code == 200, f"Episode detail failed: {resp.text}"
        body = resp.json()
        assert "topics" in body, f"Episode detail missing 'topics': {body}"
        assert isinstance(body["topics"], list)

    async def test_stream_token_for_nonexistent_episode_returns_404(
        self, gateway_client: E2EClient
    ) -> None:
        resp = await gateway_client.dataset.get(
            "/api/v1/episodes/00000000-0000-0000-0000-000000000000/stream-token"
        )
        assert resp.status_code == 404, (
            f"Expected 404 for nonexistent stream token, got {resp.status_code}: {resp.text}"
        )


@pytest.mark.e2e
class TestEpisodeDelete:
    """BUG-1: Frontend calls DELETE /api/v1/episodes/{id} but backend may not have this route."""

    async def test_delete_nonexistent_episode(
        self, gateway_client: E2EClient
    ) -> None:
        resp = await gateway_client.dataset.delete(
            "/api/v1/episodes/00000000-0000-0000-0000-000000000000"
        )
        # 404 is correct; 405 Method Not Allowed means route is missing (BUG-1)
        assert resp.status_code != 405, (
            "BUG-1: DELETE /api/v1/episodes/{id} is not implemented (405 Method Not Allowed). "
            "Frontend useDeleteEpisode calls this endpoint."
        )
        assert resp.status_code in (404, 204), (
            f"Expected 404, got {resp.status_code}: {resp.text}"
        )
