"""Async Export Worker — consumes export jobs from Redis Streams.

Flow:
  1. XREADGROUP from `export-jobs:pending` consumer group.
  2. Load ExportJob + DatasetVersion from PostgreSQL.
  3. Resolve episode refs and attached annotations.
  4. Run WebDataset or Raw exporter.
  5. Upload shards to MinIO via aioboto3 (S3-compatible).
  6. Update job status + progress in DB.
  7. ACK the Redis message.
"""
from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import datetime, timezone

import redis.asyncio as aioredis
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from worker.config import settings
from worker.database import get_session
from worker.exporters.raw import RawExporter
from worker.exporters.webdataset import EpisodeRef, WebDatasetExporter
from worker.models import Annotation, DatasetVersion, Episode, ExportJob


class ExportWorker:
    BLOCK_MS = 5_000  # block up to 5 s waiting for new messages

    def __init__(self):
        self._redis: aioredis.Redis | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self):
        self._redis = aioredis.from_url(settings.redis_url, decode_responses=True)
        await self._ensure_consumer_group()
        logger.info("Export worker started — listening on stream '{}'", settings.export_stream)
        await self.run()

    async def run(self):
        assert self._redis is not None
        while True:
            try:
                messages = await self._redis.xreadgroup(
                    groupname=settings.consumer_group,
                    consumername=settings.consumer_name,
                    streams={settings.export_stream: ">"},
                    count=1,
                    block=self.BLOCK_MS,
                )
                for _stream, entries in (messages or []):
                    for msg_id, fields in entries:
                        await self._handle_message(msg_id, fields)
            except Exception as exc:
                logger.exception("Error reading stream: {}", exc)
                await asyncio.sleep(2)

    # ------------------------------------------------------------------
    # Message handling
    # ------------------------------------------------------------------

    async def _handle_message(self, msg_id: str, fields: dict):
        job_id_str = fields.get("job_id")
        if not job_id_str:
            logger.warning("Message {} missing job_id, acking and skipping", msg_id)
            await self._ack(msg_id)
            return

        job_id = uuid.UUID(job_id_str)
        logger.info("Processing export job {}", job_id)

        async with get_session() as db:
            try:
                await self._execute_job(db, job_id)
                await self._ack(msg_id)
            except Exception as exc:
                logger.exception("Export job {} failed: {}", job_id, exc)
                async with get_session() as db2:
                    await _fail_job(db2, job_id, str(exc))

    async def _execute_job(self, db: AsyncSession, job_id: uuid.UUID):
        job = await _get_job(db, job_id)
        if job is None:
            logger.warning("Export job {} not found in DB", job_id)
            return

        await _update_job_status(db, job, "running", started_at=datetime.now(timezone.utc))

        version = await _get_version(db, job.dataset_version_id)
        if version is None:
            raise ValueError(f"DatasetVersion {job.dataset_version_id} not found")

        ep_refs = await self._resolve_episode_refs(db, version.episode_refs or [])

        output_dir = os.path.join(settings.tmp_dir, str(job_id))

        if job.format == "webdataset":
            exporter = WebDatasetExporter(
                shard_size_bytes=settings.shard_size_bytes,
                output_dir=output_dir,
            )
        else:
            exporter = RawExporter(output_dir=output_dir)  # type: ignore[assignment]

        mcap_loader = _make_minio_loader()
        result = exporter.export(ep_refs, mcap_loader=mcap_loader)

        target_prefix = job.target_prefix or str(job_id)
        uploader = _make_uploader(job.target_bucket, target_prefix)

        for i, shard in enumerate(result.shards):
            shard_key = f"{target_prefix}/shard-{i:06d}.tar"
            await uploader(shard.path, shard_key)
            progress = (i + 1) / len(result.shards) * 100
            await _update_job_progress(db, job, progress)
            logger.info("Job {} — shard {}/{} uploaded ({:.0f}%)", job_id, i + 1, len(result.shards), progress)

        manifest_key = f"{target_prefix}/manifest.json"
        manifest_bytes = json.dumps(result.manifest).encode()
        await _upload_bytes(job.target_bucket, manifest_key, manifest_bytes)

        manifest_url = f"s3://{job.target_bucket}/{manifest_key}"
        await _complete_job(db, job, manifest_url)
        logger.info("Export job {} completed — manifest at {}", job_id, manifest_url)

    # ------------------------------------------------------------------
    # Episode resolution
    # ------------------------------------------------------------------

    async def _resolve_episode_refs(
        self, db: AsyncSession, raw_refs: list[dict]
    ) -> list[EpisodeRef]:
        if not raw_refs:
            return []

        episode_ids = [uuid.UUID(r["episode_id"]) for r in raw_refs]

        ep_result = await db.execute(select(Episode).where(Episode.id.in_(episode_ids)))
        episodes_by_id = {str(ep.id): ep for ep in ep_result.scalars().all()}

        anno_result = await db.execute(
            select(Annotation).where(
                Annotation.episode_id.in_(episode_ids),
                Annotation.status == "approved",
            )
        )
        annos_by_episode: dict[str, list[dict]] = {}
        for anno in anno_result.scalars().all():
            key = str(anno.episode_id)
            annos_by_episode.setdefault(key, []).append(
                {
                    "id": str(anno.id),
                    "time_start": anno.time_start,
                    "time_end": anno.time_end,
                    "labels": anno.labels,
                    "version": anno.version,
                }
            )

        refs = []
        for raw in raw_refs:
            ep_id = raw["episode_id"]
            ep = episodes_by_id.get(ep_id)
            if ep is None:
                logger.warning("Episode {} not found, skipping", ep_id)
                continue
            refs.append(
                EpisodeRef(
                    episode_id=ep_id,
                    storage_path=ep.storage_path or "",
                    clip_start=raw.get("clip_start"),
                    clip_end=raw.get("clip_end"),
                    annotations=annos_by_episode.get(ep_id, []),
                )
            )
        return refs

    # ------------------------------------------------------------------
    # Redis helpers
    # ------------------------------------------------------------------

    async def _ensure_consumer_group(self):
        assert self._redis is not None
        try:
            await self._redis.xgroup_create(
                settings.export_stream, settings.consumer_group, id="0", mkstream=True
            )
        except aioredis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise

    async def _ack(self, msg_id: str):
        assert self._redis is not None
        await self._redis.xack(settings.export_stream, settings.consumer_group, msg_id)


# ------------------------------------------------------------------
# DB helpers
# ------------------------------------------------------------------


async def _get_job(db: AsyncSession, job_id: uuid.UUID) -> ExportJob | None:
    result = await db.execute(select(ExportJob).where(ExportJob.id == job_id))
    return result.scalar_one_or_none()


async def _get_version(db: AsyncSession, version_id: uuid.UUID) -> DatasetVersion | None:
    result = await db.execute(select(DatasetVersion).where(DatasetVersion.id == version_id))
    return result.scalar_one_or_none()


async def _update_job_status(
    db: AsyncSession,
    job: ExportJob,
    status: str,
    started_at: datetime | None = None,
):
    job.status = status
    if started_at:
        job.started_at = started_at
    await db.commit()


async def _update_job_progress(db: AsyncSession, job: ExportJob, progress_pct: float):
    job.progress_pct = progress_pct
    await db.commit()


async def _complete_job(db: AsyncSession, job: ExportJob, manifest_url: str):
    job.status = "completed"
    job.progress_pct = 100.0
    job.manifest_url = manifest_url
    job.completed_at = datetime.now(timezone.utc)
    await db.commit()


async def _fail_job(db: AsyncSession, job_id: uuid.UUID, error: str):
    job = await _get_job(db, job_id)
    if job:
        job.status = "failed"
        job.error_message = error
        await db.commit()


# ------------------------------------------------------------------
# Storage helpers (MinIO / S3-compatible via boto3)
# ------------------------------------------------------------------


def _make_minio_loader():
    """Return a sync function that downloads an object from MinIO."""
    import boto3

    s3 = boto3.client(
        "s3",
        endpoint_url=settings.minio_endpoint,
        aws_access_key_id=settings.minio_access_key,
        aws_secret_access_key=settings.minio_secret_key,
    )

    def _load(storage_path: str) -> bytes:
        if not storage_path:
            return b""
        bucket, _, key = storage_path.partition("/")
        obj = s3.get_object(Bucket=bucket, Key=key)
        return obj["Body"].read()

    return _load


def _make_uploader(bucket: str, prefix: str):
    """Return an async function that uploads a local file to MinIO."""
    import boto3

    s3 = boto3.client(
        "s3",
        endpoint_url=settings.minio_endpoint,
        aws_access_key_id=settings.minio_access_key,
        aws_secret_access_key=settings.minio_secret_key,
    )

    async def _upload(local_path: str, key: str):
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: s3.upload_file(local_path, bucket, key))

    return _upload


async def _upload_bytes(bucket: str, key: str, data: bytes):
    import io

    import boto3

    s3 = boto3.client(
        "s3",
        endpoint_url=settings.minio_endpoint,
        aws_access_key_id=settings.minio_access_key,
        aws_secret_access_key=settings.minio_secret_key,
    )
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: s3.upload_fileobj(io.BytesIO(data), bucket, key))


# ------------------------------------------------------------------
# Entrypoint
# ------------------------------------------------------------------


if __name__ == "__main__":
    asyncio.run(ExportWorker().start())
