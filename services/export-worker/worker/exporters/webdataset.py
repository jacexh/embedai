"""WebDataset sharded TAR exporter (ADR H6).

Each sample in a shard is a pair of files:
  ep_<episode_id_prefix>_<index>.mcap   — raw MCAP bytes
  ep_<episode_id_prefix>_<index>.json   — annotation payload
"""
from __future__ import annotations

import io
import json
import os
import tarfile
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


@dataclass
class EpisodeRef:
    episode_id: str
    storage_path: str  # MinIO object key
    clip_start: float | None = None
    clip_end: float | None = None
    annotations: list[dict] = field(default_factory=list)


@dataclass
class ShardInfo:
    path: str
    size_bytes: int
    sample_count: int


@dataclass
class ExportResult:
    shards: list[ShardInfo] = field(default_factory=list)
    manifest: dict = field(default_factory=dict)


class WebDatasetExporter:
    """Exports episodes into WebDataset-compatible sharded TAR archives."""

    def __init__(self, shard_size_bytes: int, output_dir: str):
        self.shard_size = shard_size_bytes
        self.output_dir = output_dir

    def export(self, episode_refs: list[EpisodeRef], mcap_loader=None) -> ExportResult:
        """Export a list of EpisodeRef into sharded .tar files.

        Args:
            episode_refs: Episodes (with annotations attached) to export.
            mcap_loader: Optional callable(storage_path) -> bytes. When None,
                         uses a stub that returns empty bytes (for unit tests).
        """
        os.makedirs(self.output_dir, exist_ok=True)

        if mcap_loader is None:
            mcap_loader = lambda _path: b""  # noqa: E731

        result = ExportResult()
        shard_idx = 0
        current_size = 0
        current_count = 0
        current_tar: tarfile.TarFile | None = None
        current_path: str | None = None

        def _flush_shard():
            nonlocal current_tar, current_path, current_size, current_count
            if current_tar is not None:
                current_tar.close()
                result.shards.append(ShardInfo(current_path, current_size, current_count))  # type: ignore[arg-type]
            current_tar = None
            current_path = None
            current_size = 0
            current_count = 0

        for i, ep_ref in enumerate(episode_refs):
            mcap_data: bytes = mcap_loader(ep_ref.storage_path)
            anno_data: bytes = json.dumps(ep_ref.annotations).encode()
            sample_name = f"ep_{ep_ref.episode_id[:8]}_{i:06d}"

            if current_tar is None or current_size + len(mcap_data) > self.shard_size:
                _flush_shard()
                shard_idx += 1
                current_path = os.path.join(self.output_dir, f"shard-{shard_idx:06d}.tar")
                current_tar = tarfile.open(current_path, "w")

            _add_bytes(current_tar, f"{sample_name}.mcap", mcap_data)
            _add_bytes(current_tar, f"{sample_name}.json", anno_data)
            current_size += len(mcap_data) + len(anno_data)
            current_count += 1

        _flush_shard()

        result.manifest = _build_manifest(episode_refs, result.shards)
        return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _add_bytes(tar: tarfile.TarFile, name: str, data: bytes) -> None:
    info = tarfile.TarInfo(name=name)
    info.size = len(data)
    tar.addfile(info, io.BytesIO(data))


def _build_manifest(episode_refs: list[EpisodeRef], shards: list[ShardInfo]) -> dict:
    return {
        "episode_count": len(episode_refs),
        "shard_count": len(shards),
        "total_size_bytes": sum(s.size_bytes for s in shards),
        "shards": [
            {
                "path": s.path,
                "size_bytes": s.size_bytes,
                "sample_count": s.sample_count,
            }
            for s in shards
        ],
    }
