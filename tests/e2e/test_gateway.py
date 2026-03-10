"""E2E tests — Gateway health, routing, and upload API.

Covers: healthcheck, routing to correct backends, upload init/chunk/complete flow.
"""
from __future__ import annotations

import os
import uuid

import httpx
import pytest

from .conftest import GATEWAY_URL
from .helpers import E2EClient


@pytest.mark.e2e
class TestGatewayHealth:
    async def test_healthz_returns_ok(self) -> None:
        async with httpx.AsyncClient(base_url=GATEWAY_URL, timeout=10.0) as client:
            resp = await client.get("/healthz")
        assert resp.status_code == 200, f"Healthz failed: {resp.text}"
        assert resp.json().get("status") == "ok"

    async def test_unknown_path_returns_404(self) -> None:
        async with httpx.AsyncClient(base_url=GATEWAY_URL, timeout=10.0) as client:
            resp = await client.get("/totally/unknown/path")
        assert resp.status_code == 404

    async def test_api_path_without_auth_returns_401(self) -> None:
        async with httpx.AsyncClient(base_url=GATEWAY_URL, timeout=10.0) as client:
            resp = await client.get("/api/v1/episodes")
        assert resp.status_code == 401

    async def test_tasks_routed_to_task_service(
        self, gateway_client: E2EClient
    ) -> None:
        """Verify /api/v1/tasks is proxied to task-service (not dataset-service)."""
        resp = await gateway_client.gateway.get("/api/v1/tasks")
        assert resp.status_code == 200, (
            f"Gateway proxy to task-service failed: {resp.text}"
        )

    async def test_episodes_routed_to_dataset_service(
        self, gateway_client: E2EClient
    ) -> None:
        """Verify /api/v1/episodes is proxied to dataset-service."""
        resp = await gateway_client.gateway.get("/api/v1/episodes")
        assert resp.status_code == 200, (
            f"Gateway proxy to dataset-service failed: {resp.text}"
        )

    async def test_export_jobs_routed_correctly(
        self, gateway_client: E2EClient
    ) -> None:
        """Verify /api/v1/export-jobs/* is proxied to dataset-service."""
        # This will 404 because the list endpoint is missing (BUG-1),
        # but it should NOT 502/503 (routing error)
        resp = await gateway_client.gateway.get("/api/v1/export-jobs")
        assert resp.status_code != 502, "Gateway is returning 502 — backend down?"
        assert resp.status_code != 503, "Gateway is returning 503 — backend down?"


@pytest.mark.e2e
class TestUploadFlow:
    async def test_upload_init_requires_auth(self) -> None:
        async with httpx.AsyncClient(base_url=GATEWAY_URL, timeout=10.0) as client:
            resp = await client.post(
                "/api/v1/episodes/upload/init",
                json={"filename": "test.mcap", "size_bytes": 100, "format": "mcap"},
            )
        assert resp.status_code == 401

    async def test_upload_init_success(self, gateway_client: E2EClient) -> None:
        resp = await gateway_client.gateway.post(
            "/api/v1/episodes/upload/init",
            json={"filename": "test.mcap", "size_bytes": 1024, "format": "mcap"},
        )
        assert resp.status_code == 201, f"Upload init failed: {resp.text}"
        body = resp.json()
        assert "episode_id" in body, f"Missing 'episode_id': {body}"
        assert "session_id" in body, f"Missing 'session_id': {body}"

    async def test_upload_init_invalid_format(
        self, gateway_client: E2EClient
    ) -> None:
        resp = await gateway_client.gateway.post(
            "/api/v1/episodes/upload/init",
            json={"filename": "test.xyz", "size_bytes": 1024, "format": "invalid"},
        )
        assert resp.status_code == 422, (
            f"Expected 422 for invalid format, got {resp.status_code}: {resp.text}"
        )

    async def test_upload_init_missing_fields(
        self, gateway_client: E2EClient
    ) -> None:
        resp = await gateway_client.gateway.post(
            "/api/v1/episodes/upload/init",
            json={"filename": "test.mcap"},
        )
        assert resp.status_code == 422, (
            f"Expected 422 for missing fields, got {resp.status_code}: {resp.text}"
        )

    async def test_upload_chunk_nonexistent_session(
        self, gateway_client: E2EClient
    ) -> None:
        fake_session = uuid.uuid4()
        resp = await gateway_client.gateway.put(
            f"/api/v1/episodes/upload/{fake_session}/chunk/0",
            content=b"fake data",
            headers={"Content-Type": "application/octet-stream"},
        )
        assert resp.status_code in (404, 400), (
            f"Expected 404/400 for nonexistent session, got {resp.status_code}: {resp.text}"
        )

    async def test_upload_complete_nonexistent_session(
        self, gateway_client: E2EClient
    ) -> None:
        fake_session = uuid.uuid4()
        resp = await gateway_client.gateway.post(
            f"/api/v1/episodes/upload/{fake_session}/complete"
        )
        assert resp.status_code in (404, 400), (
            f"Expected 404/400 for nonexistent session, got {resp.status_code}: {resp.text}"
        )

    @pytest.mark.skipif(
        not os.path.exists(
            os.path.join(
                os.path.dirname(__file__),
                "../../services/pipeline/tests/fixtures/sample.mcap",
            )
        ),
        reason="sample.mcap fixture not found — run make_fixtures.py first",
    )
    async def test_full_upload_flow(
        self, gateway_client: E2EClient, sample_mcap_file: str
    ) -> None:
        size = os.path.getsize(sample_mcap_file)

        init_resp = await gateway_client.gateway.post(
            "/api/v1/episodes/upload/init",
            json={
                "filename": os.path.basename(sample_mcap_file),
                "size_bytes": size,
                "format": "mcap",
            },
        )
        assert init_resp.status_code == 201, f"Upload init: {init_resp.text}"
        session_id = init_resp.json()["session_id"]
        episode_id = init_resp.json()["episode_id"]

        with open(sample_mcap_file, "rb") as fh:
            content = fh.read()
        chunk_resp = await gateway_client.gateway.put(
            f"/api/v1/episodes/upload/{session_id}/chunk/0",
            content=content,
            headers={"Content-Type": "application/octet-stream"},
        )
        assert chunk_resp.status_code == 200, f"Chunk upload: {chunk_resp.text}"

        complete_resp = await gateway_client.gateway.post(
            f"/api/v1/episodes/upload/{session_id}/complete"
        )
        assert complete_resp.status_code == 200, f"Upload complete: {complete_resp.text}"

        # Verify episode was created
        ep_resp = await gateway_client.dataset.get(f"/api/v1/episodes/{episode_id}")
        assert ep_resp.status_code == 200
        assert ep_resp.json()["id"] == episode_id
