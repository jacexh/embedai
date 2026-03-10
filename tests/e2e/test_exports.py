"""E2E tests — Export Jobs API.

Covers: create export job, get job, poll status.

Known bugs being detected:
- [BUG-1-EXPORT] GET /api/v1/export-jobs — list endpoint does not exist in backend.
                 Frontend useExportJobs() will always 404.
- [BUG-2-EXPORT] POST /api/v1/export-jobs — this route does not exist.
                 Backend route is POST /api/v1/dataset-versions/{id}/exports.
                 Frontend useCreateExportJob() will always 404.
- [BUG-4-SCHEMA] Backend returns 'dataset_version_id', frontend expects 'version_id'.
                 ExportJobRow will fail to match jobs to versions.
"""
from __future__ import annotations

import pytest

from .helpers import E2EClient


async def _create_dataset_version(client: E2EClient) -> str:
    """Helper: create a dataset with one version and return version_id."""
    ds_resp = await client.dataset.post(
        "/api/v1/datasets",
        json={"name": "export-test-ds", "description": "for export tests"},
    )
    assert ds_resp.status_code == 201, f"Create dataset: {ds_resp.text}"
    dataset_id = ds_resp.json()["id"]

    v_resp = await client.dataset.post(
        f"/api/v1/datasets/{dataset_id}/versions",
        json={"version_tag": "v1", "episode_refs": []},
    )
    assert v_resp.status_code == 201, f"Create version: {v_resp.text}"
    return v_resp.json()["id"]


@pytest.mark.e2e
class TestExportJobCreate:
    async def test_create_export_job_via_correct_backend_route(
        self, gateway_client: E2EClient
    ) -> None:
        """Backend route: POST /api/v1/dataset-versions/{id}/exports."""
        version_id = await _create_dataset_version(gateway_client)

        resp = await gateway_client.dataset.post(
            f"/api/v1/dataset-versions/{version_id}/exports",
            json={"format": "webdataset", "target_bucket": "s3://test-bucket/"},
        )
        assert resp.status_code in (201, 202), (
            f"Create export job (backend route) failed: {resp.text}"
        )
        body = resp.json()
        assert "id" in body, f"Missing 'id': {body}"
        assert body["status"] == "pending"
        # BUG-4: backend returns 'dataset_version_id', not 'version_id'
        assert "dataset_version_id" in body, (
            f"Backend returns field 'dataset_version_id' — "
            f"but frontend ExportJob type expects 'version_id'. "
            f"Response: {body}"
        )

    async def test_create_export_job_via_frontend_route_bug(
        self, gateway_client: E2EClient
    ) -> None:
        """BUG-2: Frontend calls POST /api/v1/export-jobs — route does not exist."""
        version_id = await _create_dataset_version(gateway_client)

        resp = await gateway_client.dataset.post(
            "/api/v1/export-jobs",
            json={
                "version_id": version_id,
                "format": "webdataset",
                "target_bucket": "s3://test-bucket/",
            },
        )
        assert resp.status_code != 404, (
            "BUG-2: POST /api/v1/export-jobs returns 404. "
            "Frontend useCreateExportJob() will always fail. "
            "Fix: either add this route to backend OR update frontend to use "
            "POST /api/v1/dataset-versions/{version_id}/exports."
        )

    async def test_create_export_job_invalid_format(
        self, gateway_client: E2EClient
    ) -> None:
        version_id = await _create_dataset_version(gateway_client)

        resp = await gateway_client.dataset.post(
            f"/api/v1/dataset-versions/{version_id}/exports",
            json={"format": "invalid_format", "target_bucket": "s3://test/"},
        )
        assert resp.status_code == 422, (
            f"Expected 422 for invalid format, got {resp.status_code}: {resp.text}"
        )

    async def test_create_export_job_missing_bucket(
        self, gateway_client: E2EClient
    ) -> None:
        version_id = await _create_dataset_version(gateway_client)

        resp = await gateway_client.dataset.post(
            f"/api/v1/dataset-versions/{version_id}/exports",
            json={"format": "webdataset"},
        )
        assert resp.status_code == 422, (
            f"Expected 422 for missing target_bucket, got {resp.status_code}: {resp.text}"
        )

    async def test_create_export_job_nonexistent_version(
        self, gateway_client: E2EClient
    ) -> None:
        resp = await gateway_client.dataset.post(
            "/api/v1/dataset-versions/00000000-0000-0000-0000-000000000000/exports",
            json={"format": "webdataset", "target_bucket": "s3://test/"},
        )
        assert resp.status_code == 404, (
            f"Expected 404 for nonexistent version, got {resp.status_code}: {resp.text}"
        )


@pytest.mark.e2e
class TestExportJobList:
    async def test_list_export_jobs_frontend_route_bug(
        self, gateway_client: E2EClient
    ) -> None:
        """BUG-1: Frontend calls GET /api/v1/export-jobs — route does not exist.

        Frontend ExportPage uses useExportJobs() which calls:
          GET /api/v1/export-jobs          (all jobs)
          GET /api/v1/export-jobs?version_id=xxx  (filtered)

        Backend only has GET /api/v1/export-jobs/{job_id} (single job by ID).
        """
        resp = await gateway_client.dataset.get("/api/v1/export-jobs")
        assert resp.status_code != 404, (
            "BUG-1: GET /api/v1/export-jobs returns 404. "
            "Frontend ExportPage export history list will always be broken. "
            "Fix: add GET /api/v1/export-jobs endpoint to dataset-service exports router."
        )
        assert resp.status_code == 200, (
            f"List export jobs endpoint returned {resp.status_code}: {resp.text}"
        )

    async def test_list_export_jobs_filtered_by_version(
        self, gateway_client: E2EClient
    ) -> None:
        """BUG-1 variant: GET /api/v1/export-jobs?version_id=xxx also 404s."""
        version_id = await _create_dataset_version(gateway_client)

        # Create a job to filter
        await gateway_client.dataset.post(
            f"/api/v1/dataset-versions/{version_id}/exports",
            json={"format": "webdataset", "target_bucket": "s3://filter-test/"},
        )

        resp = await gateway_client.dataset.get(
            f"/api/v1/export-jobs?version_id={version_id}"
        )
        assert resp.status_code != 404, (
            "BUG-1: GET /api/v1/export-jobs?version_id=... returns 404. "
            "ExportPage cannot filter jobs by version."
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body, f"Missing 'items': {body}"
        assert any(
            j.get("dataset_version_id") == version_id or j.get("version_id") == version_id
            for j in body["items"]
        ), f"Job for version {version_id} not in response: {body}"


@pytest.mark.e2e
class TestExportJobGet:
    async def test_get_export_job_by_id(self, gateway_client: E2EClient) -> None:
        version_id = await _create_dataset_version(gateway_client)

        create_resp = await gateway_client.dataset.post(
            f"/api/v1/dataset-versions/{version_id}/exports",
            json={"format": "raw", "target_bucket": "s3://get-test/"},
        )
        assert create_resp.status_code in (201, 202)
        job_id = create_resp.json()["id"]

        resp = await gateway_client.dataset.get(f"/api/v1/export-jobs/{job_id}")
        assert resp.status_code == 200, f"Get export job failed: {resp.text}"
        body = resp.json()
        assert body["id"] == job_id
        assert body["status"] in ("pending", "running", "completed", "failed")

    async def test_get_nonexistent_export_job(
        self, gateway_client: E2EClient
    ) -> None:
        resp = await gateway_client.dataset.get(
            "/api/v1/export-jobs/00000000-0000-0000-0000-000000000000"
        )
        assert resp.status_code == 404, (
            f"Expected 404 for nonexistent job, got {resp.status_code}: {resp.text}"
        )

    async def test_export_job_schema_has_required_frontend_fields(
        self, gateway_client: E2EClient
    ) -> None:
        """BUG-4: Frontend ExportJob type expects 'version_id' and 'updated_at'.
        Backend returns 'dataset_version_id' with no 'updated_at'.
        """
        version_id = await _create_dataset_version(gateway_client)
        create_resp = await gateway_client.dataset.post(
            f"/api/v1/dataset-versions/{version_id}/exports",
            json={"format": "webdataset", "target_bucket": "s3://schema-test/"},
        )
        assert create_resp.status_code in (201, 202)
        job_id = create_resp.json()["id"]

        resp = await gateway_client.dataset.get(f"/api/v1/export-jobs/{job_id}")
        assert resp.status_code == 200
        body = resp.json()

        # Document the schema mismatch
        assert "dataset_version_id" in body, "Backend should return 'dataset_version_id'"
        if "version_id" not in body:
            pytest.fail(
                "BUG-4: ExportJob response missing 'version_id' field. "
                "Frontend type ExportJob expects 'version_id' but backend returns "
                "'dataset_version_id'. ExportJobRow will fail to correlate jobs."
            )
        if "updated_at" not in body:
            pytest.fail(
                "BUG-4: ExportJob response missing 'updated_at' field. "
                "Frontend ExportJob type declares updated_at: string."
            )
