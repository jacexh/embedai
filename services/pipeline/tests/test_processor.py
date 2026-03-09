import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from pipeline.db import ProjectInfo
from pipeline.processor import EpisodeProcessor

MCAP_FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "sample.mcap")
HDF5_FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "sample.hdf5")

PROJECT_SCHEMA = {
    "required_topics": ["/camera/rgb", "/imu/data"],
    "topic_frequency": {"/camera/rgb": 30.0, "/imu/data": 200.0},
}


@pytest.fixture
def project_info():
    return ProjectInfo(project_id="project-1", topic_schema=PROJECT_SCHEMA)


@pytest.fixture
def processor(mock_db, mock_storage, project_info):
    mock_db.get_episode_project.return_value = project_info
    mock_storage.download_temp.return_value = MCAP_FIXTURE
    # Override delete-on-cleanup to avoid removing fixture
    return EpisodeProcessor(db=mock_db, storage=mock_storage)


@pytest.mark.asyncio
async def test_process_mcap_episode(processor, mock_db, mock_storage):
    with patch("os.unlink"):  # Don't delete the fixture
        await processor.process(
            "episode-123",
            {b"storage_path": b"episodes/p1/episode-123.mcap", b"format": b"mcap"},
        )

    # Status transitions
    mock_db.update_episode_status.assert_called_once_with("episode-123", "processing")

    # update_episode_ready was called with sensible values
    call_kwargs = mock_db.update_episode_ready.call_args.kwargs
    assert call_kwargs["episode_id"] == "episode-123"
    assert call_kwargs["duration"] > 0
    assert 0.0 <= call_kwargs["quality_score"] <= 1.0
    assert len(call_kwargs["topics"]) == 2
    assert "quality_detail" in call_kwargs["metadata"]


@pytest.mark.asyncio
async def test_process_hdf5_episode(mock_db, mock_storage, project_info):
    mock_db.get_episode_project.return_value = ProjectInfo(project_id="p1", topic_schema={})
    mock_storage.download_temp.return_value = HDF5_FIXTURE
    processor = EpisodeProcessor(db=mock_db, storage=mock_storage)

    with patch("os.unlink"):
        await processor.process(
            "episode-hdf5",
            {b"storage_path": b"episodes/p1/episode-hdf5.hdf5", b"format": b"hdf5"},
        )

    call_kwargs = mock_db.update_episode_ready.call_args.kwargs
    assert call_kwargs["duration"] == 10.0
    assert len(call_kwargs["topics"]) > 0


@pytest.mark.asyncio
async def test_process_unsupported_format(processor, mock_db):
    with patch("os.unlink"):
        with pytest.raises(ValueError, match="Unsupported format"):
            await processor.process(
                "episode-bad",
                {b"storage_path": b"episodes/bad.rosbag", b"format": b"rosbag"},
            )

    # Status set to processing before failure
    mock_db.update_episode_status.assert_called_once_with("episode-bad", "processing")


@pytest.mark.asyncio
async def test_process_cleans_up_temp_file(mock_db, mock_storage, project_info, tmp_path):
    """Temp file must be deleted even on success."""
    mock_db.get_episode_project.return_value = project_info
    # Use a copy of the fixture to allow deletion
    import shutil
    tmp_mcap = str(tmp_path / "episode.mcap")
    shutil.copy(MCAP_FIXTURE, tmp_mcap)
    mock_storage.download_temp.return_value = tmp_mcap

    processor = EpisodeProcessor(db=mock_db, storage=mock_storage)
    await processor.process(
        "episode-cleanup",
        {b"storage_path": b"episodes/ep.mcap", b"format": b"mcap"},
    )
    assert not os.path.exists(tmp_mcap)
