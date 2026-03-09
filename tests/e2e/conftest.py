"""E2E test fixtures — requires all services running (make e2e-up)."""
from __future__ import annotations

import os
import uuid

import httpx
import pytest

from .helpers import E2EClient

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8000")
DATASET_SERVICE_URL = os.getenv("DATASET_SERVICE_URL", "http://localhost:8001")
TASK_SERVICE_URL = os.getenv("TASK_SERVICE_URL", "http://localhost:8002")

# Reuse the sample fixture created by the pipeline service tests.
_SAMPLE_MCAP = os.path.join(
    os.path.dirname(__file__),
    "../../services/pipeline/tests/fixtures/sample.mcap",
)


@pytest.fixture(scope="session")
async def gateway_client() -> E2EClient:  # type: ignore[override]
    """Register an admin user, log in, and return authenticated clients."""
    unique = uuid.uuid4().hex[:8]
    project_id = str(uuid.uuid4())
    email = f"e2e_{unique}@test.local"
    password = "e2e_pass_123"

    # Register then login via the gateway auth endpoints.
    async with httpx.AsyncClient(base_url=GATEWAY_URL, timeout=30.0) as raw:
        resp = await raw.post(
            "/auth/register",
            json={
                "email": email,
                "password": password,
                "name": f"E2E Admin {unique}",
                "role": "admin",
                "project_id": project_id,
            },
        )
        resp.raise_for_status()

        resp = await raw.post(
            "/auth/login",
            json={"email": email, "password": password},
        )
        resp.raise_for_status()
        token = resp.json()["token"]
        user_id = resp.json()["user"]["id"]

    headers = {"Authorization": f"Bearer {token}"}
    gw = httpx.AsyncClient(base_url=GATEWAY_URL, headers=headers, timeout=60.0)
    ds = httpx.AsyncClient(base_url=DATASET_SERVICE_URL, headers=headers, timeout=60.0)
    ts = httpx.AsyncClient(base_url=TASK_SERVICE_URL, headers=headers, timeout=60.0)

    try:
        yield E2EClient(gateway=gw, dataset=ds, task=ts, user_id=user_id, project_id=project_id)
    finally:
        await gw.aclose()
        await ds.aclose()
        await ts.aclose()


@pytest.fixture(scope="session")
async def pipeline_worker(gateway_client: E2EClient) -> E2EClient:
    """Smoke-check the gateway healthz endpoint before E2E tests run."""
    resp = await gateway_client.gateway.get("/healthz")
    assert resp.status_code == 200, f"Gateway healthcheck failed: {resp.text}"
    return gateway_client


@pytest.fixture
def sample_mcap_file() -> str:
    """Return the absolute path to the sample MCAP fixture."""
    path = os.path.abspath(_SAMPLE_MCAP)
    assert os.path.exists(path), (
        f"Sample MCAP fixture not found at {path}. "
        "Run 'cd services/pipeline && python tests/make_fixtures.py' first."
    )
    return path
