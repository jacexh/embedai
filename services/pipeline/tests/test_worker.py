import pytest
from unittest.mock import ANY, AsyncMock

from pipeline.worker import PipelineWorker


@pytest.mark.asyncio
async def test_worker_processes_message(mock_redis, mock_processor):
    worker = PipelineWorker(mock_redis, mock_processor)
    await worker._handle("1-0", {b"episode_id": b"test-id", b"format": b"mcap", b"storage_path": b"episodes/test-id.mcap"})
    mock_processor.process.assert_called_once_with(
        "test-id",
        {b"episode_id": b"test-id", b"format": b"mcap", b"storage_path": b"episodes/test-id.mcap"},
    )
    mock_redis.xack.assert_called_once_with(PipelineWorker.STREAM, PipelineWorker.GROUP, "1-0")


@pytest.mark.asyncio
async def test_worker_does_not_ack_on_failure(mock_redis, mock_processor):
    mock_processor.process.side_effect = RuntimeError("boom")
    worker = PipelineWorker(mock_redis, mock_processor)
    # Should not raise
    await worker._handle("1-0", {b"episode_id": b"fail-id", b"format": b"mcap", b"storage_path": b"episodes/fail-id.mcap"})
    mock_redis.xack.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_group_ignores_existing(mock_redis):
    mock_redis.xgroup_create.side_effect = Exception("BUSYGROUP")
    worker = PipelineWorker(mock_redis, AsyncMock())
    # Should not raise
    await worker._ensure_group()
