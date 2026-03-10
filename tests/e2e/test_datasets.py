"""E2E tests — Datasets & Dataset Versions API.

Covers: create dataset, list datasets, create version, list versions, immutability.

Known bugs being detected:
- [BUG-3] Frontend useCreateVersion sends {episode_ids: [...]} but backend expects
          {episode_refs: [{episode_id: ...}]}. Creating versions via frontend will fail.
"""
from __future__ import annotations

import pytest

from .helpers import E2EClient


@pytest.mark.e2e
class TestDatasetCRUD:
    async def test_create_dataset_success(self, gateway_client: E2EClient) -> None:
        resp = await gateway_client.dataset.post(
            "/api/v1/datasets",
            json={"name": "e2e-test-dataset", "description": "Created by E2E test"},
        )
        assert resp.status_code == 201, f"Create dataset failed: {resp.text}"
        body = resp.json()
        assert "id" in body, f"Missing 'id': {body}"
        assert body["name"] == "e2e-test-dataset"

    async def test_create_dataset_missing_name_returns_422(
        self, gateway_client: E2EClient
    ) -> None:
        resp = await gateway_client.dataset.post(
            "/api/v1/datasets",
            json={"description": "No name here"},
        )
        assert resp.status_code == 422, (
            f"Expected 422 for missing name, got {resp.status_code}: {resp.text}"
        )

    async def test_list_datasets_returns_items(self, gateway_client: E2EClient) -> None:
        # Create one first to ensure non-empty
        await gateway_client.dataset.post(
            "/api/v1/datasets",
            json={"name": "list-test-ds", "description": ""},
        )
        resp = await gateway_client.dataset.get("/api/v1/datasets")
        assert resp.status_code == 200, f"List datasets failed: {resp.text}"
        body = resp.json()
        assert "items" in body, f"Response missing 'items': {body}"
        assert isinstance(body["items"], list)
        assert len(body["items"]) > 0

    async def test_dataset_response_schema(self, gateway_client: E2EClient) -> None:
        resp = await gateway_client.dataset.post(
            "/api/v1/datasets",
            json={"name": "schema-check-ds", "description": "test"},
        )
        assert resp.status_code == 201
        body = resp.json()
        required_fields = ["id", "name", "description", "project_id", "status", "created_at"]
        for field in required_fields:
            assert field in body, f"Dataset response missing field '{field}': {body}"


@pytest.mark.e2e
class TestDatasetVersions:
    async def test_create_version_with_correct_payload(
        self, gateway_client: E2EClient
    ) -> None:
        """Backend expects episode_refs: [{episode_id: str}], not episode_ids: [str]."""
        ds_resp = await gateway_client.dataset.post(
            "/api/v1/datasets",
            json={"name": "version-test-ds", "description": ""},
        )
        assert ds_resp.status_code == 201
        dataset_id = ds_resp.json()["id"]

        # Correct payload (as backend expects)
        resp = await gateway_client.dataset.post(
            f"/api/v1/datasets/{dataset_id}/versions",
            json={"version_tag": "v1", "episode_refs": []},
        )
        assert resp.status_code == 201, (
            f"Create version with correct payload failed: {resp.text}"
        )
        body = resp.json()
        assert body["version_tag"] == "v1"
        assert body["is_immutable"] is True, "Version should be immutable on creation"

    async def test_create_version_with_frontend_payload_bug(
        self, gateway_client: E2EClient
    ) -> None:
        """BUG-3: Frontend sends episode_ids instead of episode_refs.

        This test documents that the frontend payload format is wrong.
        Backend should either accept episode_ids OR the frontend should be fixed.
        """
        ds_resp = await gateway_client.dataset.post(
            "/api/v1/datasets",
            json={"name": "bug3-test-ds", "description": ""},
        )
        assert ds_resp.status_code == 201
        dataset_id = ds_resp.json()["id"]

        # This is what the frontend currently sends (WRONG format)
        resp = await gateway_client.dataset.post(
            f"/api/v1/datasets/{dataset_id}/versions",
            json={"version_tag": "v1", "episode_ids": []},
        )
        # If backend accepts this without error, episode_refs defaults to []; OK (lenient)
        # If backend rejects: frontend's Create Version button is broken (BUG-3)
        if resp.status_code not in (201, 200):
            pytest.fail(
                f"BUG-3: Frontend sends {{episode_ids: []}} but backend rejected it with "
                f"{resp.status_code}. Frontend useCreateVersion is broken.\n"
                f"Response: {resp.text}"
            )

    async def test_list_versions_for_dataset(self, gateway_client: E2EClient) -> None:
        ds_resp = await gateway_client.dataset.post(
            "/api/v1/datasets",
            json={"name": "list-versions-ds", "description": ""},
        )
        assert ds_resp.status_code == 201
        dataset_id = ds_resp.json()["id"]

        await gateway_client.dataset.post(
            f"/api/v1/datasets/{dataset_id}/versions",
            json={"version_tag": "v1", "episode_refs": []},
        )

        resp = await gateway_client.dataset.get(f"/api/v1/datasets/{dataset_id}/versions")
        assert resp.status_code == 200, f"List versions failed: {resp.text}"
        body = resp.json()
        assert "items" in body, f"Missing 'items': {body}"
        assert len(body["items"]) == 1

    async def test_version_immutability(self, gateway_client: E2EClient) -> None:
        """Creating two versions with the same tag should fail (or produce distinct records)."""
        ds_resp = await gateway_client.dataset.post(
            "/api/v1/datasets",
            json={"name": "immutable-test-ds", "description": ""},
        )
        assert ds_resp.status_code == 201
        dataset_id = ds_resp.json()["id"]

        r1 = await gateway_client.dataset.post(
            f"/api/v1/datasets/{dataset_id}/versions",
            json={"version_tag": "v1", "episode_refs": []},
        )
        assert r1.status_code == 201

        # ADR H5: versions are immutable — duplicate tag should fail
        r2 = await gateway_client.dataset.post(
            f"/api/v1/datasets/{dataset_id}/versions",
            json={"version_tag": "v1", "episode_refs": []},
        )
        assert r2.status_code in (409, 422, 400), (
            f"Duplicate version tag should be rejected, got {r2.status_code}: {r2.text}"
        )

    async def test_list_versions_nonexistent_dataset(
        self, gateway_client: E2EClient
    ) -> None:
        resp = await gateway_client.dataset.get(
            "/api/v1/datasets/00000000-0000-0000-0000-000000000000/versions"
        )
        assert resp.status_code == 404, (
            f"Expected 404 for nonexistent dataset, got {resp.status_code}: {resp.text}"
        )
