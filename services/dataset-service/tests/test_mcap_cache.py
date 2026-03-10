"""Unit tests for McapFileCache."""
from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.mcap_cache import McapFileCache


@pytest.fixture
def cache(tmp_path):
    """Fresh cache instance pointing at tmp dir."""
    return McapFileCache(max_size=3, ttl_seconds=300, cache_dir=str(tmp_path))


@pytest.fixture
def mock_storage():
    storage = MagicMock()
    storage.download_to_file = AsyncMock()
    return storage


class TestMcapFileCacheBasic:
    """Basic cache get/miss/hit behavior."""

    async def test_cache_miss_downloads_file(self, cache, mock_storage, tmp_path):
        """Cache miss triggers download and returns file path."""
        path = await cache.get_or_download("ep-1", "storage/ep1.mcap", mock_storage)

        assert os.path.exists(path) or mock_storage.download_to_file.called
        mock_storage.download_to_file.assert_called_once_with("storage/ep1.mcap", path)

    async def test_cache_hit_skips_download(self, cache, mock_storage, tmp_path):
        """Second request for same episode skips download."""
        path1 = await cache.get_or_download("ep-1", "storage/ep1.mcap", mock_storage)
        Path(path1).touch()

        path2 = await cache.get_or_download("ep-1", "storage/ep1.mcap", mock_storage)

        assert path1 == path2
        assert mock_storage.download_to_file.call_count == 1

    async def test_cache_hit_file_deleted_re_downloads(self, cache, mock_storage, tmp_path):
        """If cached file was deleted externally, re-download."""
        path1 = await cache.get_or_download("ep-1", "storage/ep1.mcap", mock_storage)
        # Don't create the file (simulates external deletion)

        path2 = await cache.get_or_download("ep-1", "storage/ep1.mcap", mock_storage)

        assert mock_storage.download_to_file.call_count == 2


class TestMcapFileCacheLRU:
    """LRU eviction behavior."""

    async def test_evicts_oldest_when_full(self, cache, mock_storage, tmp_path):
        """When at capacity, evict the least recently used entry."""
        for i in range(3):
            path = await cache.get_or_download(f"ep-{i}", f"storage/ep{i}.mcap", mock_storage)
            Path(path).touch()

        # Access ep-0 to make it recently used
        await cache.get_or_download("ep-0", "storage/ep0.mcap", mock_storage)

        # Add a 4th entry - should evict ep-1 (oldest not recently accessed)
        path4 = await cache.get_or_download("ep-3", "storage/ep3.mcap", mock_storage)
        Path(path4).touch()

        assert "ep-1" not in cache._cache
        assert "ep-0" in cache._cache
        assert "ep-3" in cache._cache

    async def test_evicted_file_is_deleted_from_disk(self, cache, mock_storage, tmp_path):
        """Evicted entry's temp file is removed from disk."""
        paths = []
        for i in range(3):
            path = await cache.get_or_download(f"ep-{i}", f"storage/ep{i}.mcap", mock_storage)
            Path(path).touch()
            paths.append(path)

        # Add 4th - ep-0 should be evicted (LRU)
        path4 = await cache.get_or_download("ep-3", "storage/ep3.mcap", mock_storage)

        assert not os.path.exists(paths[0])

    async def test_cache_size_never_exceeds_max(self, cache, mock_storage, tmp_path):
        """Cache size never exceeds max_size."""
        for i in range(10):
            path = await cache.get_or_download(f"ep-{i}", f"storage/ep{i}.mcap", mock_storage)
            Path(path).touch()

        assert len(cache._cache) <= 3


class TestMcapFileCacheConcurrency:
    """Concurrent download protection."""

    async def test_concurrent_requests_same_episode_download_once(self, mock_storage, tmp_path):
        """Concurrent requests for same episode only trigger one download."""
        download_count = 0

        async def slow_download(storage_path, local_path):
            nonlocal download_count
            download_count += 1
            await asyncio.sleep(0.05)
            Path(local_path).touch()

        mock_storage.download_to_file = slow_download
        cache = McapFileCache(max_size=3, ttl_seconds=300, cache_dir=str(tmp_path))

        paths = await asyncio.gather(*[
            cache.get_or_download("ep-1", "storage/ep1.mcap", mock_storage)
            for _ in range(5)
        ])

        assert download_count == 1
        assert len(set(paths)) == 1

    async def test_concurrent_requests_different_episodes_parallel(self, mock_storage, tmp_path):
        """Concurrent requests for different episodes run in parallel."""
        started = []

        async def slow_download(storage_path, local_path):
            started.append(storage_path)
            await asyncio.sleep(0.05)
            Path(local_path).touch()

        mock_storage.download_to_file = slow_download
        cache = McapFileCache(max_size=5, ttl_seconds=300, cache_dir=str(tmp_path))

        await asyncio.gather(*[
            cache.get_or_download(f"ep-{i}", f"storage/ep{i}.mcap", mock_storage)
            for i in range(3)
        ])

        assert len(started) == 3


class TestMcapFileCacheCleanup:
    """TTL-based cleanup."""

    async def test_cleanup_expired_removes_old_entries(self, tmp_path):
        """cleanup_expired removes entries older than TTL."""
        import time
        cache = McapFileCache(max_size=5, ttl_seconds=1, cache_dir=str(tmp_path))

        mock_storage = MagicMock()
        mock_storage.download_to_file = AsyncMock()

        path = await cache.get_or_download("ep-1", "storage/ep1.mcap", mock_storage)
        Path(path).touch()

        # Simulate time passing
        cache._cache["ep-1"] = (path, time.monotonic() - 2)  # 2s ago, TTL=1s

        await cache.cleanup_expired()

        assert "ep-1" not in cache._cache
        assert not os.path.exists(path)

    async def test_cleanup_keeps_fresh_entries(self, cache, mock_storage, tmp_path):
        """cleanup_expired keeps entries within TTL."""
        path = await cache.get_or_download("ep-1", "storage/ep1.mcap", mock_storage)
        Path(path).touch()

        await cache.cleanup_expired()

        assert "ep-1" in cache._cache

    async def test_clear_removes_all_files(self, cache, mock_storage, tmp_path):
        """clear() removes all cached files from disk."""
        paths = []
        for i in range(3):
            path = await cache.get_or_download(f"ep-{i}", f"storage/ep{i}.mcap", mock_storage)
            Path(path).touch()
            paths.append(path)

        await cache.clear()

        assert len(cache._cache) == 0
        for path in paths:
            assert not os.path.exists(path)
