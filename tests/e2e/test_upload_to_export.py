"""End-to-end pipeline test: upload MCAP → process → annotate → export.

Prerequisites:
    make e2e-up        # builds and starts all services
    make migrate       # applies DB migrations
    pytest tests/e2e/ -m e2e -v --timeout=600
"""
from __future__ import annotations

import asyncio
import os
import time

import pytest

from .helpers import E2EClient


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


async def upload_file(client: E2EClient, file_path: str) -> str:
    """Chunk-upload a file through the gateway and return the episode_id."""
    size = os.path.getsize(file_path)

    # Initiate upload session.
    resp = await client.gateway.post(
        "/api/v1/episodes/upload/init",
        json={
            "filename": os.path.basename(file_path),
            "size_bytes": size,
            "format": "mcap",
        },
    )
    resp.raise_for_status()
    data = resp.json()
    episode_id = data["episode_id"]
    session_id = data["session_id"]

    # Upload single chunk (sample file is small, fits in one chunk).
    with open(file_path, "rb") as fh:
        content = fh.read()
    resp = await client.gateway.put(
        f"/api/v1/episodes/upload/{session_id}/chunk/0",
        content=content,
        headers={"Content-Type": "application/octet-stream"},
    )
    resp.raise_for_status()

    # Finalise upload.
    resp = await client.gateway.post(f"/api/v1/episodes/upload/{session_id}/complete")
    resp.raise_for_status()

    return episode_id


async def wait_for_status(
    client: E2EClient, episode_id: str, status: str, timeout: float
) -> dict:
    """Poll the dataset-service until episode reaches *status* or raises."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        resp = await client.dataset.get(f"/api/v1/episodes/{episode_id}")
        if resp.status_code == 200:
            ep = resp.json()
            if ep["status"] == status:
                return ep
            if ep["status"] == "error":
                raise AssertionError(
                    f"Episode {episode_id} entered error state during processing"
                )
        await asyncio.sleep(5)
    raise TimeoutError(
        f"Episode {episode_id} did not reach '{status}' within {timeout:.0f}s"
    )


async def create_and_approve_task(client: E2EClient, episode_id: str) -> str:
    """Create an annotation task and drive it through created→assigned→submitted→approved."""
    # Create task (Label Studio integration is best-effort; won't block on LS failure).
    resp = await client.task.post(
        "/api/v1/tasks",
        json={"episode_id": episode_id, "type": "labeling"},
    )
    resp.raise_for_status()
    task_id = resp.json()["id"]

    # Assign to ourselves (admin role allows self-assignment).
    resp = await client.task.post(
        f"/api/v1/tasks/{task_id}/assign",
        json={"user_id": client.user_id},
    )
    resp.raise_for_status()

    # Submit annotation work.
    resp = await client.task.post(f"/api/v1/tasks/{task_id}/submit")
    resp.raise_for_status()

    # Approve (requires engineer/admin role — we registered as admin).
    resp = await client.task.post(f"/api/v1/tasks/{task_id}/approve")
    resp.raise_for_status()

    return task_id


async def create_dataset_version(client: E2EClient, episode_id: str) -> str:
    """Create a dataset with one immutable version referencing the episode."""
    resp = await client.dataset.post(
        "/api/v1/datasets",
        json={
            "name": f"e2e-dataset-{episode_id[:8]}",
            "description": "Created by E2E integration test",
        },
    )
    resp.raise_for_status()
    dataset_id = resp.json()["id"]

    resp = await client.dataset.post(
        f"/api/v1/datasets/{dataset_id}/versions",
        json={
            "version_tag": "v1",
            "episode_refs": [{"episode_id": episode_id}],
        },
    )
    resp.raise_for_status()
    return resp.json()["id"]


async def trigger_export(client: E2EClient, version_id: str, format: str) -> str:
    """Enqueue an async export job and return its job_id."""
    resp = await client.dataset.post(
        f"/api/v1/dataset-versions/{version_id}/exports",
        json={"format": format},
    )
    resp.raise_for_status()
    return resp.json()["id"]


async def wait_for_export(client: E2EClient, job_id: str, timeout: float) -> dict:
    """Poll export-job status until completed/failed or timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        resp = await client.dataset.get(f"/api/v1/export-jobs/{job_id}")
        if resp.status_code == 200:
            job = resp.json()
            if job["status"] in ("completed", "failed"):
                return job
        await asyncio.sleep(5)
    raise TimeoutError(f"Export job {job_id} did not finish within {timeout:.0f}s")


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


@pytest.mark.e2e
async def test_full_pipeline(
    gateway_client: E2EClient,
    pipeline_worker: E2EClient,
    sample_mcap_file: str,
) -> None:
    """
    上传 MCAP → 处理流水线 → 创建任务 → 标注 → 数据集版本 → 导出
    验证整条链路的端到端延迟 < 5 分钟
    """
    start = time.monotonic()

    # 1. Upload MCAP file.
    episode_id = await upload_file(gateway_client, sample_mcap_file)

    # 2. Wait for pipeline to process episode (up to 5 minutes).
    episode = await wait_for_status(gateway_client, episode_id, "ready", timeout=300)
    assert episode["quality_score"] is not None, "quality_score must be set after processing"

    # 3. Create and fully approve an annotation task.
    task_id = await create_and_approve_task(gateway_client, episode_id)  # noqa: F841

    # 4. Create dataset version and trigger WebDataset export.
    version_id = await create_dataset_version(gateway_client, episode_id)
    job_id = await trigger_export(gateway_client, version_id, format="webdataset")
    job = await wait_for_export(gateway_client, job_id, timeout=300)

    assert job["status"] == "completed", f"Export failed: {job}"
    assert job["manifest_url"] is not None, "Completed export must have a manifest_url"

    elapsed = time.monotonic() - start
    assert elapsed < 300, f"Pipeline took {elapsed:.1f}s, exceeds 5-minute SLA"
