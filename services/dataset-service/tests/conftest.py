"""Shared pytest fixtures for dataset-service tests."""
from __future__ import annotations

import time
import uuid
from collections.abc import Generator
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from jose import jwt

from app.config import settings
from app.main import app
from app.models import Dataset, DatasetVersion, Episode, Topic
from app.services.mcap_cache import McapFileCache


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

TEST_PROJECT_ID = str(uuid.uuid4())
TEST_USER_ID = str(uuid.uuid4())


def make_token(project_id: str = TEST_PROJECT_ID, user_id: str = TEST_USER_ID, role: str = "engineer") -> str:
    payload = {
        "user_id": user_id,
        "project_id": project_id,
        "role": role,
        "exp": int(time.time()) + 3600,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token()}"}


# ---------------------------------------------------------------------------
# Cache init
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def init_cache(tmp_path):
    """Initialize McapFileCache for tests."""
    import app.services.cache_registry as registry
    registry._mcap_cache = McapFileCache(max_size=2, ttl_seconds=300, cache_dir=str(tmp_path))
    yield
    registry._mcap_cache = None


# ---------------------------------------------------------------------------
# DB mock
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_db() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def client(mock_db: AsyncMock) -> Generator[TestClient, None, None]:
    from app.database import get_db

    async def _override():
        yield mock_db

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Seed data factories
# ---------------------------------------------------------------------------

def make_episode(
    project_id: str = TEST_PROJECT_ID,
    status: str = "ready",
    fmt: str = "mcap",
    quality: float = 0.85,
) -> Episode:
    ep = Episode()
    ep.id = uuid.uuid4()
    ep.project_id = uuid.UUID(project_id)
    ep.filename = f"episode_{ep.id}.mcap"
    ep.format = fmt
    ep.size_bytes = 1024 * 1024 * 100
    ep.duration_seconds = 60.0
    ep.status = status
    ep.quality_score = quality
    ep.episode_metadata = {}
    ep.storage_path = f"s3://bucket/{ep.id}"
    ep.recorded_at = datetime(2026, 3, 1, tzinfo=timezone.utc)
    ep.ingested_at = datetime(2026, 3, 1, 1, tzinfo=timezone.utc)
    ep.created_at = datetime(2026, 3, 1, tzinfo=timezone.utc)
    ep.topics = []
    return ep


def make_topic(episode: Episode, name: str = "/camera/image_raw", type_: str = "image") -> Topic:
    t = Topic()
    t.id = uuid.uuid4()
    t.episode_id = episode.id
    t.name = name
    t.type = type_
    t.start_time_offset = 0.0
    t.end_time_offset = 60.0
    t.message_count = 1800
    t.frequency_hz = 30.0
    t.schema_name = "sensor_msgs/Image"
    return t


def make_dataset(project_id: str = TEST_PROJECT_ID, name: str = "test-dataset") -> Dataset:
    ds = Dataset()
    ds.id = uuid.uuid4()
    ds.project_id = uuid.UUID(project_id)
    ds.name = name
    ds.description = "Test dataset"
    ds.status = "draft"
    ds.created_by = uuid.UUID(TEST_USER_ID)
    ds.created_at = datetime(2026, 3, 1, tzinfo=timezone.utc)
    ds.versions = []
    return ds


def make_version(dataset: Dataset, tag: str = "v1.0.0", immutable: bool = True) -> DatasetVersion:
    v = DatasetVersion()
    v.id = uuid.uuid4()
    v.dataset_id = dataset.id
    v.version_tag = tag
    v.episode_refs = []
    v.episode_count = 0
    v.total_size_bytes = 0
    v.is_immutable = immutable
    v.created_by = uuid.UUID(TEST_USER_ID)
    v.created_at = datetime(2026, 3, 1, tzinfo=timezone.utc)
    return v
