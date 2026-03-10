"""Tests for Dataset version management API — Task 4.2."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from tests.conftest import TEST_PROJECT_ID, TEST_USER_ID, make_dataset, make_episode, make_version


class TestListDatasets:
    def test_list_datasets(self, client, auth_headers, mock_db):
        ds = make_dataset()

        result = MagicMock()
        result.scalars.return_value.all.return_value = [ds]
        mock_db.execute = AsyncMock(return_value=result)

        resp = client.get("/api/v1/datasets", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert data["total"] == 1
        assert data["items"][0]["name"] == "test-dataset"

    def test_list_datasets_unauthenticated(self, client):
        resp = client.get("/api/v1/datasets")
        assert resp.status_code in (401, 403)


class TestCreateDataset:
    def test_create_dataset_success(self, client, auth_headers, mock_db):
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        resp = client.post(
            "/api/v1/datasets",
            json={"name": "my-dataset", "description": "A test dataset"},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "my-dataset"
        assert body["status"] == "draft"
        assert "id" in body

    def test_create_dataset_missing_name(self, client, auth_headers, mock_db):
        resp = client.post("/api/v1/datasets", json={}, headers=auth_headers)
        assert resp.status_code == 422


class TestCreateVersion:
    def test_create_version_snapshot(self, client, auth_headers, mock_db):
        ds = make_dataset()
        ep1 = make_episode(project_id=TEST_PROJECT_ID)
        ep2 = make_episode(project_id=TEST_PROJECT_ID)

        # Mock: get dataset, validate episodes, create version
        dataset_result = MagicMock()
        dataset_result.scalar_one_or_none.return_value = ds

        episode_result = MagicMock()
        episode_result.scalars.return_value.all.return_value = [ep1, ep2]

        mock_db.execute = AsyncMock(side_effect=[dataset_result, episode_result])
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        resp = client.post(
            f"/api/v1/datasets/{ds.id}/versions",
            json={
                "version_tag": "v1.0.0",
                "episode_refs": [
                    {"episode_id": str(ep1.id), "clip_start": 0.0, "clip_end": 30.0},
                    {"episode_id": str(ep2.id), "clip_start": 0.0, "clip_end": 60.0},
                ],
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["version_tag"] == "v1.0.0"
        assert body["is_immutable"] is True
        assert body["episode_count"] == 2

    def test_create_version_dataset_not_found(self, client, auth_headers, mock_db):
        dataset_result = MagicMock()
        dataset_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=dataset_result)

        resp = client.post(
            f"/api/v1/datasets/{uuid.uuid4()}/versions",
            json={"version_tag": "v1.0.0", "episode_refs": []},
            headers=auth_headers,
        )
        assert resp.status_code == 404

    def test_create_version_episode_ref_wrong_project(self, client, auth_headers, mock_db):
        """Episode belonging to different project is rejected."""
        ds = make_dataset()
        # Only 1 episode returned even though 2 were requested → 1 is foreign
        ep_valid = make_episode(project_id=TEST_PROJECT_ID)
        foreign_ep_id = str(uuid.uuid4())

        dataset_result = MagicMock()
        dataset_result.scalar_one_or_none.return_value = ds

        episode_result = MagicMock()
        episode_result.scalars.return_value.all.return_value = [ep_valid]  # only 1 of 2 found

        mock_db.execute = AsyncMock(side_effect=[dataset_result, episode_result])

        resp = client.post(
            f"/api/v1/datasets/{ds.id}/versions",
            json={
                "version_tag": "v1.0.0",
                "episode_refs": [
                    {"episode_id": str(ep_valid.id)},
                    {"episode_id": foreign_ep_id},
                ],
            },
            headers=auth_headers,
        )
        assert resp.status_code == 422
        assert "episode" in resp.json()["detail"].lower()

    def test_create_version_empty_refs(self, client, auth_headers, mock_db):
        """Version with no episodes is allowed (draft snapshot)."""
        ds = make_dataset()

        dataset_result = MagicMock()
        dataset_result.scalar_one_or_none.return_value = ds

        episode_result = MagicMock()
        episode_result.scalars.return_value.all.return_value = []

        mock_db.execute = AsyncMock(side_effect=[dataset_result, episode_result])
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        resp = client.post(
            f"/api/v1/datasets/{ds.id}/versions",
            json={"version_tag": "v0.0.1", "episode_refs": []},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        assert resp.json()["episode_count"] == 0


class TestVersionImmutability:
    def test_patch_immutable_version_returns_409(self, client, auth_headers, mock_db):
        """ADR H5: once created, dataset versions are immutable."""
        ds = make_dataset()
        version = make_version(ds, immutable=True)

        result = MagicMock()
        result.scalar_one_or_none.return_value = version
        mock_db.execute = AsyncMock(return_value=result)

        resp = client.patch(
            f"/api/v1/dataset-versions/{version.id}",
            json={"episode_refs": []},
            headers=auth_headers,
        )
        assert resp.status_code == 409
        assert "immutable" in resp.json()["error"]

    def test_patch_mutable_version_allowed(self, client, auth_headers, mock_db):
        """Non-immutable (draft) version can be updated."""
        ds = make_dataset()
        version = make_version(ds, immutable=False)

        result = MagicMock()
        result.scalar_one_or_none.return_value = version
        mock_db.execute = AsyncMock(return_value=result)
        mock_db.commit = AsyncMock()

        resp = client.patch(
            f"/api/v1/dataset-versions/{version.id}",
            json={"description": "updated"},
            headers=auth_headers,
        )
        assert resp.status_code == 200

    def test_patch_version_not_found(self, client, auth_headers, mock_db):
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=result)

        resp = client.patch(
            f"/api/v1/dataset-versions/{uuid.uuid4()}",
            json={"description": "x"},
            headers=auth_headers,
        )
        assert resp.status_code == 404


class TestListVersions:
    def test_list_versions_for_dataset(self, client, auth_headers, mock_db):
        ds = make_dataset()
        v1 = make_version(ds, tag="v1.0.0")
        v2 = make_version(ds, tag="v1.1.0")

        dataset_result = MagicMock()
        dataset_result.scalar_one_or_none.return_value = ds

        versions_result = MagicMock()
        versions_result.scalars.return_value.all.return_value = [v1, v2]

        mock_db.execute = AsyncMock(side_effect=[dataset_result, versions_result])

        resp = client.get(f"/api/v1/datasets/{ds.id}/versions", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert data["total"] == 2
        tags = [v["version_tag"] for v in data["items"]]
        assert "v1.0.0" in tags
        assert "v1.1.0" in tags

    def test_list_versions_dataset_not_found(self, client, auth_headers, mock_db):
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=result)

        resp = client.get(f"/api/v1/datasets/{uuid.uuid4()}/versions", headers=auth_headers)
        assert resp.status_code == 404
