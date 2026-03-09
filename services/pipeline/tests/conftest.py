import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    redis.xreadgroup = AsyncMock(return_value=[])
    redis.xack = AsyncMock()
    redis.xgroup_create = AsyncMock()
    return redis


@pytest.fixture
def mock_processor():
    processor = AsyncMock()
    processor.process = AsyncMock()
    return processor


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.update_episode_status = AsyncMock()
    db.update_episode_ready = AsyncMock()
    db.get_episode_project = AsyncMock()
    return db


@pytest.fixture
def mock_storage():
    storage = AsyncMock()
    storage.download_temp = AsyncMock(return_value="/tmp/test_episode.mcap")
    storage.upload = AsyncMock(return_value="thumbnails/test-id.jpg")
    return storage
