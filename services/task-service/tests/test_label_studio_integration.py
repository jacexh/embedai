"""Tests for Label Studio client integration — Task 5.1."""
from __future__ import annotations

import pytest
import respx
import httpx

from app.integrations.label_studio import LabelStudioClient


LS_BASE = "http://ls-test:8080"
API_KEY = "test-api-key"


@pytest.fixture
def ls_client() -> LabelStudioClient:
    return LabelStudioClient(base_url=LS_BASE, api_key=API_KEY)


# ---------------------------------------------------------------------------
# create_project
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_project(ls_client: LabelStudioClient):
    with respx.mock:
        respx.post(f"{LS_BASE}/api/projects").mock(
            return_value=httpx.Response(201, json={"id": 7, "title": "test-project"})
        )
        project_id = await ls_client.create_project(
            name="test-project",
            label_config="<View/>",
        )
    assert project_id == 7


# ---------------------------------------------------------------------------
# create_task
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_task(ls_client: LabelStudioClient):
    with respx.mock:
        respx.post(f"{LS_BASE}/api/tasks").mock(
            return_value=httpx.Response(
                201,
                json={"id": 42, "project": 1, "data": {"video": "http://gw/ep-123"}},
            )
        )
        task_id = await ls_client.create_task(
            project_id=1,
            data_url="http://gw/ep-123",
            meta={"episode_id": "ep-123", "time_start": 0, "time_end": 30},
        )
    assert isinstance(task_id, int)
    assert task_id == 42


# ---------------------------------------------------------------------------
# get_annotations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_annotations_returns_list(ls_client: LabelStudioClient):
    annotations = [
        {"id": 1, "task": 42, "result": [{"from_name": "label", "value": {"labels": ["robot_arm"]}}]},
    ]
    with respx.mock:
        respx.get(f"{LS_BASE}/api/tasks/42/annotations").mock(
            return_value=httpx.Response(200, json=annotations)
        )
        result = await ls_client.get_annotations(task_id=42)
    assert len(result) == 1
    assert result[0]["id"] == 1


@pytest.mark.asyncio
async def test_get_annotations_empty(ls_client: LabelStudioClient):
    with respx.mock:
        respx.get(f"{LS_BASE}/api/tasks/99/annotations").mock(
            return_value=httpx.Response(200, json=[])
        )
        result = await ls_client.get_annotations(task_id=99)
    assert result == []


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_task_raises_on_server_error(ls_client: LabelStudioClient):
    with respx.mock:
        respx.post(f"{LS_BASE}/api/tasks").mock(
            return_value=httpx.Response(500, json={"detail": "internal error"})
        )
        with pytest.raises(httpx.HTTPStatusError):
            await ls_client.create_task(project_id=1, data_url="http://gw/ep", meta={})
