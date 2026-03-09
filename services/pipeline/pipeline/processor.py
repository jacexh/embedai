"""EpisodeProcessor — orchestrates extraction, scoring, thumbnail, and DB write."""
from __future__ import annotations

import os
from dataclasses import asdict
from typing import TYPE_CHECKING

from loguru import logger

from pipeline.db import Database
from pipeline.extractors.hdf5_extractor import extract_hdf5_meta
from pipeline.extractors.mcap_extractor import McapExtractor
from pipeline.extractors.models import EpisodeMeta
from pipeline.quality.scorer import QualityScorer
from pipeline.storage import StorageClient


class EpisodeProcessor:
    def __init__(self, db: Database, storage: StorageClient):
        self.db = db
        self.storage = storage

    async def process(self, episode_id: str, event_data: dict) -> None:
        storage_path = event_data[b"storage_path"].decode()
        fmt = event_data[b"format"].decode()

        logger.info("Processing episode {} (format={})", episode_id, fmt)

        # 1. Mark as processing
        await self.db.update_episode_status(episode_id, "processing")

        # 2. Download to local temp file
        local_path = await self.storage.download_temp(storage_path)

        try:
            # 3. Extract metadata
            meta = self._extract(local_path, fmt)

            # 4. Quality scoring
            project = await self.db.get_episode_project(episode_id)
            scorer = QualityScorer(project.topic_schema)
            score, detail = scorer.score(meta, local_path)

            # 5. Generate thumbnail (best-effort)
            thumb_url = await self._generate_thumbnail(local_path, fmt, episode_id)

            # 6. Persist results to DB
            await self.db.update_episode_ready(
                episode_id=episode_id,
                duration=meta.duration_seconds,
                quality_score=score,
                metadata={
                    "quality_detail": asdict(detail),
                    "thumbnail_url": thumb_url,
                    "topic_count": len(meta.topics),
                },
                topics=meta.topics,
            )
            logger.info(
                "Episode {} ready: duration={:.1f}s score={:.3f} topics={}",
                episode_id, meta.duration_seconds, score, len(meta.topics),
            )
        finally:
            try:
                os.unlink(local_path)
            except OSError:
                pass

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _extract(self, local_path: str, fmt: str) -> EpisodeMeta:
        if fmt == "mcap":
            return McapExtractor(local_path).extract()
        elif fmt == "hdf5":
            return extract_hdf5_meta(local_path)
        else:
            raise ValueError(f"Unsupported format: {fmt}")

    async def _generate_thumbnail(self, local_path: str, fmt: str, episode_id: str) -> str:
        """Extract first image frame and upload as thumbnail. Returns storage URL or empty string."""
        try:
            if fmt == "mcap":
                return await self._thumbnail_from_mcap(local_path, episode_id)
        except Exception as e:
            logger.warning("Thumbnail generation failed for {}: {}", episode_id, e)
        return ""

    async def _thumbnail_from_mcap(self, local_path: str, episode_id: str) -> str:
        import tempfile

        import cv2
        import numpy as np
        from mcap.reader import make_reader

        # Find first image topic and grab first frame
        with open(local_path, "rb") as f:
            reader = make_reader(f)
            for schema, channel, message in reader.iter_messages():
                if "Image" in (schema.name if schema else ""):
                    raw = np.frombuffer(message.data, dtype=np.uint8)
                    img = cv2.imdecode(raw, cv2.IMREAD_COLOR)
                    if img is not None:
                        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
                        tmp.close()
                        cv2.imwrite(tmp.name, img)
                        dest = f"thumbnails/{episode_id}.jpg"
                        await self.storage.upload(tmp.name, dest, content_type="image/jpeg")
                        os.unlink(tmp.name)
                        return dest
        return ""
