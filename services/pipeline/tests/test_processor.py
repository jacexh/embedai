import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from pipeline.db import ProjectInfo
from pipeline.processor import EpisodeProcessor
from pipeline.quality.scorer import QualityDetail

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


class TestProcessorFailurePaths:
    """Failure path tests: exceptions must mark episode as FAILED and clean up temp files."""

    @pytest.mark.asyncio
    async def test_process_extraction_failure_marks_episode_failed(
        self, mock_db, mock_storage, project_info, tmp_path
    ):
        """RuntimeError during extraction must propagate; temp file must be deleted."""
        mock_db.get_episode_project.return_value = project_info

        tmp_file = tmp_path / "episode.mcap"
        tmp_file.write_bytes(b"fake content")
        mock_storage.download_temp.return_value = str(tmp_file)

        processor = EpisodeProcessor(db=mock_db, storage=mock_storage)

        with patch("pipeline.processor.McapExtractor") as mock_extractor:
            mock_extractor.return_value.extract.side_effect = RuntimeError("corrupt file")
            with pytest.raises(RuntimeError, match="corrupt file"):
                await processor.process(
                    "ep-fail",
                    {b"storage_path": b"episodes/ep.mcap", b"format": b"mcap"},
                )

        mock_db.update_episode_status.assert_called_once_with("ep-fail", "processing")
        mock_db.update_episode_ready.assert_not_called()
        assert not tmp_file.exists(), "temp file must be cleaned up even on failure"

    @pytest.mark.asyncio
    async def test_process_storage_download_failure(
        self, mock_db, mock_storage, project_info
    ):
        """ConnectionError during download must propagate; update_episode_ready must not be called."""
        mock_db.get_episode_project.return_value = project_info
        mock_storage.download_temp.side_effect = ConnectionError("S3 unavailable")

        processor = EpisodeProcessor(db=mock_db, storage=mock_storage)

        with pytest.raises(ConnectionError, match="S3 unavailable"):
            await processor.process(
                "ep-dl-fail",
                {b"storage_path": b"episodes/ep.mcap", b"format": b"mcap"},
            )

        # Step 1 (mark processing) ran before download attempt
        mock_db.update_episode_status.assert_called_once_with("ep-dl-fail", "processing")
        mock_db.update_episode_ready.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_unsupported_format_cleans_up(
        self, mock_db, mock_storage, project_info, tmp_path
    ):
        """ValueError for unsupported format must be raised and temp file must be deleted."""
        mock_db.get_episode_project.return_value = project_info

        tmp_file = tmp_path / "episode.rosbag"
        tmp_file.write_bytes(b"fake content")
        mock_storage.download_temp.return_value = str(tmp_file)

        processor = EpisodeProcessor(db=mock_db, storage=mock_storage)

        with pytest.raises(ValueError, match="Unsupported format"):
            await processor.process(
                "ep-fmt-fail",
                {b"storage_path": b"episodes/ep.rosbag", b"format": b"rosbag"},
            )

        assert not tmp_file.exists(), "temp file must be cleaned up on unsupported format"

    @pytest.mark.asyncio
    async def test_process_db_update_failure_still_cleans_up(
        self, mock_db, mock_storage, project_info, tmp_path
    ):
        """Exception from update_episode_ready must propagate but temp file must still be deleted."""
        mock_db.get_episode_project.return_value = project_info
        mock_db.update_episode_ready.side_effect = Exception("DB connection lost")

        tmp_file = tmp_path / "episode.mcap"
        tmp_file.write_bytes(b"fake content")
        mock_storage.download_temp.return_value = str(tmp_file)

        processor = EpisodeProcessor(db=mock_db, storage=mock_storage)

        _detail = QualityDetail(frame_rate_stability=1.0, sensor_completeness=1.0,
                                signal_quality=1.0, total_score=0.9)

        with patch("pipeline.processor.McapExtractor") as mock_extractor:
            mock_meta = MagicMock()
            mock_meta.duration_seconds = 5.0
            mock_meta.topics = []
            mock_extractor.return_value.extract.return_value = mock_meta

            with patch("pipeline.processor.QualityScorer") as mock_scorer_cls:
                mock_scorer_cls.return_value.score.return_value = (0.9, _detail)

                with patch.object(processor, "_generate_thumbnail", return_value=""):
                    with pytest.raises(Exception, match="DB connection lost"):
                        await processor.process(
                            "ep-db-fail",
                            {b"storage_path": b"episodes/ep.mcap", b"format": b"mcap"},
                        )

        assert not tmp_file.exists(), "temp file must be cleaned up even when DB update fails"

    @pytest.mark.asyncio
    async def test_process_thumbnail_failure_does_not_prevent_ready(
        self, mock_db, mock_storage, project_info, tmp_path
    ):
        """Thumbnail generation failure must not prevent episode from being marked ready."""
        mock_db.get_episode_project.return_value = project_info

        tmp_file = tmp_path / "episode.mcap"
        tmp_file.write_bytes(b"fake content")
        mock_storage.download_temp.return_value = str(tmp_file)

        processor = EpisodeProcessor(db=mock_db, storage=mock_storage)

        _detail = QualityDetail(frame_rate_stability=1.0, sensor_completeness=1.0,
                                signal_quality=1.0, total_score=0.75)

        with patch("pipeline.processor.McapExtractor") as mock_extractor:
            mock_meta = MagicMock()
            mock_meta.duration_seconds = 3.0
            mock_meta.topics = []
            mock_extractor.return_value.extract.return_value = mock_meta

            with patch("pipeline.processor.QualityScorer") as mock_scorer_cls:
                mock_scorer_cls.return_value.score.return_value = (0.75, _detail)

                # Patch the internal method that _generate_thumbnail delegates to,
                # forcing it to raise so the outer best-effort wrapper catches it.
                with patch.object(
                    processor, "_thumbnail_from_mcap", side_effect=Exception("thumbnail boom")
                ):
                    await processor.process(
                        "ep-thumb-fail",
                        {b"storage_path": b"episodes/ep.mcap", b"format": b"mcap"},
                    )

        # Despite thumbnail failure, update_episode_ready must have been called
        mock_db.update_episode_ready.assert_called_once()
        call_kwargs = mock_db.update_episode_ready.call_args.kwargs
        assert call_kwargs["episode_id"] == "ep-thumb-fail"
