"""Label Studio REST API client.

Wraps the Label Studio HTTP API for project/task management and
annotation retrieval. All methods are async (httpx.AsyncClient).
"""
from __future__ import annotations

import httpx

from app.config import settings


class LabelStudioClient:
    """Thin async wrapper around the Label Studio REST API."""

    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        self.base_url = (base_url or settings.label_studio_url).rstrip("/")
        self.headers = {
            "Authorization": f"Token {api_key or settings.label_studio_api_key}",
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------
    # Projects
    # ------------------------------------------------------------------

    async def create_project(self, name: str, label_config: str) -> int:
        """Create a Label Studio project and return its integer id."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/api/projects",
                headers=self.headers,
                json={"title": name, "label_config": label_config},
            )
            resp.raise_for_status()
            return resp.json()["id"]

    async def get_project(self, project_id: int) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/api/projects/{project_id}",
                headers=self.headers,
            )
            resp.raise_for_status()
            return resp.json()

    # ------------------------------------------------------------------
    # Tasks
    # ------------------------------------------------------------------

    async def create_task(self, project_id: int, data_url: str, meta: dict) -> int:
        """Create a Label Studio task and return its integer id."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/api/tasks",
                headers=self.headers,
                json={"project": project_id, "data": {"video": data_url, **meta}},
            )
            resp.raise_for_status()
            return resp.json()["id"]

    async def get_task(self, task_id: int) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/api/tasks/{task_id}",
                headers=self.headers,
            )
            resp.raise_for_status()
            return resp.json()

    async def delete_task(self, task_id: int) -> None:
        async with httpx.AsyncClient() as client:
            resp = await client.delete(
                f"{self.base_url}/api/tasks/{task_id}",
                headers=self.headers,
            )
            resp.raise_for_status()

    # ------------------------------------------------------------------
    # Annotations
    # ------------------------------------------------------------------

    async def get_annotations(self, task_id: int) -> list[dict]:
        """Fetch all annotations for a Label Studio task."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/api/tasks/{task_id}/annotations",
                headers=self.headers,
            )
            resp.raise_for_status()
            return resp.json()


def get_ls_client() -> LabelStudioClient:
    """FastAPI dependency — returns a configured LabelStudioClient."""
    return LabelStudioClient()
