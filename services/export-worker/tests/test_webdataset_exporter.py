"""Tests for WebDatasetExporter — Task 6.1 Step 1."""
from __future__ import annotations

import json
import tarfile

import pytest

from worker.exporters.webdataset import EpisodeRef, WebDatasetExporter


def _stub_loader(size_bytes: int):
    """Return a loader that always yields `size_bytes` of zeros."""

    def _load(_path: str) -> bytes:
        return b"\x00" * size_bytes

    return _load


# ---------------------------------------------------------------------------
# Basic TAR/shard structure
# ---------------------------------------------------------------------------


def test_webdataset_export_creates_shards(tmp_path, sample_episodes_with_annotations):
    exporter = WebDatasetExporter(
        shard_size_bytes=200 * 1024 * 1024,  # 200 MB — all 5 episodes fit in 1 shard
        output_dir=str(tmp_path),
    )
    result = exporter.export(sample_episodes_with_annotations)

    assert len(result.shards) > 0
    for shard in result.shards:
        assert tarfile.is_tarfile(shard.path)
    assert result.manifest["episode_count"] == len(sample_episodes_with_annotations)


def test_shard_contains_mcap_and_json(tmp_path, one_episode_with_annotation):
    exporter = WebDatasetExporter(shard_size_bytes=500 * 1024 * 1024, output_dir=str(tmp_path))
    result = exporter.export([one_episode_with_annotation])

    with tarfile.open(result.shards[0].path) as tar:
        names = tar.getnames()
        assert any(n.endswith(".mcap") for n in names)
        assert any(n.endswith(".json") for n in names)


# ---------------------------------------------------------------------------
# Annotations are embedded in the JSON member
# ---------------------------------------------------------------------------


def test_annotation_payload_in_json_member(tmp_path, one_episode_with_annotation):
    exporter = WebDatasetExporter(shard_size_bytes=500 * 1024 * 1024, output_dir=str(tmp_path))
    result = exporter.export([one_episode_with_annotation])

    with tarfile.open(result.shards[0].path) as tar:
        json_members = [m for m in tar.getmembers() if m.name.endswith(".json")]
        assert len(json_members) == 1
        payload = json.loads(tar.extractfile(json_members[0]).read())
        assert len(payload) == 1
        assert payload[0]["labels"]["action"] == "grasp"


# ---------------------------------------------------------------------------
# Sharding behaviour
# ---------------------------------------------------------------------------


def test_multiple_shards_when_episodes_exceed_limit(tmp_path):
    """Each episode provides 150 MB of MCAP; limit is 200 MB → 2 shards for 3 episodes."""
    episodes = [
        EpisodeRef(episode_id=f"ep-{i:032d}", storage_path=f"bucket/ep_{i}.mcap")
        for i in range(3)
    ]
    loader = _stub_loader(150 * 1024 * 1024)
    exporter = WebDatasetExporter(shard_size_bytes=200 * 1024 * 1024, output_dir=str(tmp_path))
    result = exporter.export(episodes, mcap_loader=loader)

    assert len(result.shards) >= 2
    for shard in result.shards:
        assert tarfile.is_tarfile(shard.path)


def test_manifest_counts_match(tmp_path, sample_episodes_with_annotations):
    exporter = WebDatasetExporter(shard_size_bytes=100 * 1024 * 1024, output_dir=str(tmp_path))
    result = exporter.export(sample_episodes_with_annotations)

    assert result.manifest["episode_count"] == len(sample_episodes_with_annotations)
    assert result.manifest["shard_count"] == len(result.shards)
    assert result.manifest["total_size_bytes"] == sum(s.size_bytes for s in result.shards)


# ---------------------------------------------------------------------------
# Empty input
# ---------------------------------------------------------------------------


def test_empty_episode_list(tmp_path):
    exporter = WebDatasetExporter(shard_size_bytes=400 * 1024 * 1024, output_dir=str(tmp_path))
    result = exporter.export([])

    assert result.shards == []
    assert result.manifest["episode_count"] == 0
    assert result.manifest["shard_count"] == 0
