"""LRU disk cache for downloaded MCAP files."""
from __future__ import annotations

import asyncio
import hashlib
import os
import tempfile
import time
from collections import OrderedDict

from loguru import logger


class McapFileCache:
    """Cache downloaded MCAP files on disk with LRU eviction and TTL.

    Args:
        max_size: Max number of MCAP files to keep on disk simultaneously.
        ttl_seconds: Seconds before a cache entry is considered stale.
        cache_dir: Directory to store cached files (defaults to system temp).
    """

    def __init__(
        self,
        max_size: int = 5,
        ttl_seconds: int = 300,
        cache_dir: str | None = None,
    ):
        self._max_size = max_size
        self._ttl = ttl_seconds
        self._cache_dir = cache_dir or tempfile.gettempdir()
        # episode_id -> (file_path, last_access_time)
        self._cache: OrderedDict[str, tuple[str, float]] = OrderedDict()
        self._global_lock = asyncio.Lock()
        self._episode_locks: dict[str, asyncio.Lock] = {}

    async def get_or_download(
        self,
        episode_id: str,
        storage_path: str,
        storage,
    ) -> str:
        """Return path to cached MCAP file, downloading if necessary."""
        # Fast path: check cache
        async with self._global_lock:
            if episode_id in self._cache:
                path, _ = self._cache[episode_id]
                if os.path.exists(path):
                    self._cache.move_to_end(episode_id)
                    self._cache[episode_id] = (path, time.monotonic())
                    return path
                else:
                    logger.warning("Cached MCAP file missing from disk: {}", path)
                    del self._cache[episode_id]
                    self._episode_locks.pop(episode_id, None)

            if episode_id not in self._episode_locks:
                self._episode_locks[episode_id] = asyncio.Lock()
            ep_lock = self._episode_locks[episode_id]

        async with ep_lock:
            # Double-check after acquiring episode lock
            async with self._global_lock:
                if episode_id in self._cache:
                    path, _ = self._cache[episode_id]
                    if os.path.exists(path):
                        self._cache.move_to_end(episode_id)
                        self._cache[episode_id] = (path, time.monotonic())
                        return path

            safe_id = hashlib.sha256(episode_id.encode()).hexdigest()[:32]
            tmp_path = os.path.join(self._cache_dir, f"mcap_{safe_id}.mcap")
            logger.info("Downloading MCAP {} -> {}", storage_path, tmp_path)
            try:
                await storage.download_to_file(storage_path, tmp_path)
            except Exception:
                # Clean up lock and any partial file so next request can retry
                self._remove_file(tmp_path)
                async with self._global_lock:
                    self._episode_locks.pop(episode_id, None)
                raise

            async with self._global_lock:
                while len(self._cache) >= self._max_size:
                    oldest_id, (oldest_path, _) = self._cache.popitem(last=False)
                    self._episode_locks.pop(oldest_id, None)
                    self._remove_file(oldest_path)
                    logger.debug("Evicted cached MCAP for episode {}", oldest_id)

                self._cache[episode_id] = (tmp_path, time.monotonic())

            return tmp_path

    async def cleanup_expired(self) -> None:
        """Remove cache entries older than TTL."""
        now = time.monotonic()
        async with self._global_lock:
            expired = [
                eid
                for eid, (_, last_access) in self._cache.items()
                if now - last_access > self._ttl
            ]
            for eid in expired:
                path, _ = self._cache.pop(eid)
                self._episode_locks.pop(eid, None)
                self._remove_file(path)
                logger.debug("Expired cached MCAP for episode {}", eid)

    async def clear(self) -> None:
        """Remove all cached files."""
        async with self._global_lock:
            for path, _ in self._cache.values():
                self._remove_file(path)
            self._cache.clear()
            self._episode_locks.clear()

    def _remove_file(self, path: str) -> None:
        try:
            os.unlink(path)
        except OSError as e:
            logger.warning("Failed to remove cached MCAP file {}: {}", path, e)
