"""Raw exporter — copies original MCAP files into a flat directory structure."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from worker.exporters.webdataset import EpisodeRef, ExportResult, ShardInfo


class RawExporter:
    """Exports episodes as-is: one directory per episode with MCAP + annotations JSON."""

    def __init__(self, output_dir: str):
        self.output_dir = output_dir

    def export(self, episode_refs: list[EpisodeRef], mcap_loader=None) -> ExportResult:
        """Export episodes into a flat directory structure.

        Args:
            episode_refs: Episodes to export.
            mcap_loader: Optional callable(storage_path) -> bytes.
        """
        os.makedirs(self.output_dir, exist_ok=True)

        if mcap_loader is None:
            mcap_loader = lambda _path: b""  # noqa: E731

        result = ExportResult()

        for i, ep_ref in enumerate(episode_refs):
            mcap_data: bytes = mcap_loader(ep_ref.storage_path)
            anno_data: bytes = json.dumps(ep_ref.annotations).encode()
            sample_name = f"ep_{ep_ref.episode_id[:8]}_{i:06d}"

            mcap_path = os.path.join(self.output_dir, f"{sample_name}.mcap")
            anno_path = os.path.join(self.output_dir, f"{sample_name}.json")

            with open(mcap_path, "wb") as f:
                f.write(mcap_data)
            with open(anno_path, "wb") as f:
                f.write(anno_data)

            size = len(mcap_data) + len(anno_data)
            result.shards.append(ShardInfo(path=mcap_path, size_bytes=size, sample_count=1))

        result.manifest = {
            "format": "raw",
            "episode_count": len(episode_refs),
            "output_dir": self.output_dir,
        }
        return result
