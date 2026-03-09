"""MinIO storage client for downloading episode files and uploading thumbnails."""
from __future__ import annotations

import asyncio
import os
import tempfile

from loguru import logger
from minio import Minio


class StorageClient:
    def __init__(self, endpoint: str, access_key: str, secret_key: str, bucket: str):
        self._client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=False)
        self._bucket = bucket

    async def download_temp(self, storage_path: str) -> str:
        """Download object to a temp file; caller must delete."""
        suffix = os.path.splitext(storage_path)[-1] or ".bin"
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        tmp.close()

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: self._client.fget_object(self._bucket, storage_path, tmp.name),
        )
        logger.debug("Downloaded {} → {}", storage_path, tmp.name)
        return tmp.name

    async def upload(self, local_path: str, dest_path: str, content_type: str = "application/octet-stream") -> str:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: self._client.fput_object(self._bucket, dest_path, local_path, content_type=content_type),
        )
        return dest_path
