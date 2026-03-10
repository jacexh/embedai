"""MinIO storage client for dataset service."""
from __future__ import annotations

import asyncio
from pathlib import Path

import aioboto3
from app.config import settings


class StorageClient:
    """Async MinIO/S3 storage client."""

    def __init__(self):
        self.endpoint_url = settings.minio_endpoint
        self.bucket = settings.minio_bucket
        self.access_key = settings.minio_access_key
        self.secret_key = settings.minio_secret_key

    async def download_to_file(self, storage_path: str, local_path: str) -> None:
        """Download object from MinIO to local file."""
        session = aioboto3.Session()

        async with session.client(
            "s3",
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
        ) as s3:
            await s3.download_file(self.bucket, storage_path, local_path)

    async def get_object_stream(self, storage_path: str):
        """Get object as async stream."""
        session = aioboto3.Session()

        async with session.client(
            "s3",
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
        ) as s3:
            response = await s3.get_object(Bucket=self.bucket, Key=storage_path)
            return response["Body"]
