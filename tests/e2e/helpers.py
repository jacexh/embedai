"""E2E client wrapper carrying JWT auth for all services."""
from __future__ import annotations

import httpx


class E2EClient:
    """Multi-service HTTP client with shared JWT auth."""

    gateway: httpx.AsyncClient   # gateway (upload + auth)
    dataset: httpx.AsyncClient   # dataset-service (episodes, datasets, exports)
    task: httpx.AsyncClient      # task-service (annotation tasks)
    user_id: str
    project_id: str

    def __init__(
        self,
        gateway: httpx.AsyncClient,
        dataset: httpx.AsyncClient,
        task: httpx.AsyncClient,
        user_id: str,
        project_id: str,
    ) -> None:
        self.gateway = gateway
        self.dataset = dataset
        self.task = task
        self.user_id = user_id
        self.project_id = project_id
