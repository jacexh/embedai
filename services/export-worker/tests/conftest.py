"""Shared test fixtures for export-worker."""
from __future__ import annotations

import pytest

from worker.exporters.webdataset import EpisodeRef


@pytest.fixture
def sample_episodes_with_annotations() -> list[EpisodeRef]:
    """Five episodes each with two approved annotations."""
    return [
        EpisodeRef(
            episode_id=f"ep-00000000-0000-0000-0000-{i:012d}",
            storage_path=f"embedai/episode_{i}.mcap",
            clip_start=0.0,
            clip_end=10.0,
            annotations=[
                {"id": f"ann-{i}-1", "labels": {"action": "pick"}, "time_start": 0.0, "time_end": 5.0},
                {"id": f"ann-{i}-2", "labels": {"action": "place"}, "time_start": 5.0, "time_end": 10.0},
            ],
        )
        for i in range(5)
    ]


@pytest.fixture
def one_episode_with_annotation() -> EpisodeRef:
    return EpisodeRef(
        episode_id="ep-00000000-0000-0000-0000-000000000001",
        storage_path="embedai/episode_1.mcap",
        clip_start=None,
        clip_end=None,
        annotations=[
            {"id": "ann-1", "labels": {"action": "grasp"}, "time_start": 1.0, "time_end": 3.0},
        ],
    )
