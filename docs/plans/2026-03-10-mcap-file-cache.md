# MCAP File Cache Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Cache downloaded MCAP files on disk so each frame request doesn't re-download the entire file from MinIO.

**Architecture:** A module-level `McapFileCache` singleton holds an LRU dict of `episode_id → tmp_file_path`. The first request for an episode downloads the MCAP and keeps it; subsequent requests for the same episode reuse the cached file. Per-episode asyncio locks prevent duplicate downloads. The cache is wired into the `get_frame` endpoint via FastAPI lifespan startup.

**Tech Stack:** Python asyncio, `collections.OrderedDict` (LRU), FastAPI lifespan, existing `StorageClient`, pytest

---

### Task 1: Write `McapFileCache` with unit tests

**Files:**
- Create: `services/dataset-service/app/services/mcap_cache.py`
- Create: `services/dataset-service/tests/test_mcap_cache.py`

**Step 1: Write the failing tests**

Create `services/dataset-service/tests/test_mcap_cache.py`:

```python
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
        # Simulate file existing
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
        # Fill cache to max_size=3
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

        # ep-0's file should be deleted
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

        # 5 concurrent requests for same episode
        paths = await asyncio.gather(*[
            cache.get_or_download("ep-1", "storage/ep1.mcap", mock_storage)
            for _ in range(5)
        ])

        assert download_count == 1
        assert len(set(paths)) == 1  # all got same path

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
        cache._cache["ep-1"] = (path, time.time() - 2)  # 2s ago, TTL=1s

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
```

**Step 2: Run tests to verify they fail**

```bash
cd /home/xuhao/embedai/services/dataset-service
uv run pytest tests/test_mcap_cache.py -v 2>&1 | head -40
```

Expected: `ModuleNotFoundError: No module named 'app.services.mcap_cache'`

**Step 3: Implement `McapFileCache`**

Create `services/dataset-service/app/services/mcap_cache.py`:

```python
"""LRU disk cache for downloaded MCAP files."""
from __future__ import annotations

import asyncio
import os
import tempfile
import time
from collections import OrderedDict
from pathlib import Path

from loguru import logger


class McapFileCache:
    """Cache downloaded MCAP files on disk with LRU eviction and TTL.

    Thread-safe for asyncio: uses per-episode locks to prevent duplicate
    downloads and a global lock for cache metadata mutations.

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
        """Return path to cached MCAP file, downloading if necessary.

        Args:
            episode_id: Unique episode identifier (used as cache key).
            storage_path: MinIO/S3 object path to download from.
            storage: StorageClient instance with download_to_file().

        Returns:
            Absolute path to the local MCAP file.
        """
        # Fast path: check cache without locking
        async with self._global_lock:
            if episode_id in self._cache:
                path, _ = self._cache[episode_id]
                if os.path.exists(path):
                    # Refresh LRU position and access time
                    self._cache.move_to_end(episode_id)
                    self._cache[episode_id] = (path, time.monotonic())
                    return path
                else:
                    # File was deleted externally — remove stale entry
                    logger.warning("Cached MCAP file missing from disk: {}", path)
                    del self._cache[episode_id]
                    self._episode_locks.pop(episode_id, None)

            # Ensure per-episode lock exists
            if episode_id not in self._episode_locks:
                self._episode_locks[episode_id] = asyncio.Lock()
            ep_lock = self._episode_locks[episode_id]

        # Download with per-episode lock (allows parallel downloads for different episodes)
        async with ep_lock:
            # Double-check after acquiring episode lock
            async with self._global_lock:
                if episode_id in self._cache:
                    path, _ = self._cache[episode_id]
                    if os.path.exists(path):
                        self._cache.move_to_end(episode_id)
                        self._cache[episode_id] = (path, time.monotonic())
                        return path

            # Download to persistent temp file
            safe_id = episode_id.replace("-", "")[:16]
            tmp_path = os.path.join(self._cache_dir, f"mcap_{safe_id}.mcap")
            logger.info("Downloading MCAP {} -> {}", storage_path, tmp_path)
            await storage.download_to_file(storage_path, tmp_path)

            async with self._global_lock:
                # Evict LRU entries if at capacity
                while len(self._cache) >= self._max_size:
                    oldest_id, (oldest_path, _) = self._cache.popitem(last=False)
                    self._episode_locks.pop(oldest_id, None)
                    self._remove_file(oldest_path)
                    logger.debug("Evicted cached MCAP for episode {}", oldest_id)

                self._cache[episode_id] = (tmp_path, time.monotonic())

            return tmp_path

    async def cleanup_expired(self) -> None:
        """Remove cache entries older than TTL. Call periodically."""
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
        """Remove all cached files. Used for shutdown cleanup."""
        async with self._global_lock:
            for path, _ in self._cache.values():
                self._remove_file(path)
            self._cache.clear()
            self._episode_locks.clear()

    def _remove_file(self, path: str) -> None:
        try:
            os.unlink(path)
        except OSError:
            pass
```

**Step 4: Run tests to verify they pass**

```bash
cd /home/xuhao/embedai/services/dataset-service
uv run pytest tests/test_mcap_cache.py -v
```

Expected: All tests PASS.

**Step 5: Commit**

```bash
cd /home/xuhao/embedai
git add services/dataset-service/app/services/mcap_cache.py \
        services/dataset-service/tests/test_mcap_cache.py
git commit -m "feat: add LRU disk cache for MCAP files to avoid repeated downloads"
```

---

### Task 2: Wire cache into `get_frame` endpoint

**Files:**
- Modify: `services/dataset-service/app/main.py`
- Modify: `services/dataset-service/app/routers/episodes.py`
- Modify: `services/dataset-service/tests/test_frame_api.py`

**Step 1: Update `test_frame_api.py` — verify cache is used, temp file is NOT unlinked**

Replace `test_get_frame_cleans_up_temp_file` and add a new cache test. Find and replace this test in `services/dataset-service/tests/test_frame_api.py`:

```python
    def test_get_frame_uses_cache(self, client, auth_headers, mock_db):
        """Frame endpoint uses McapFileCache instead of direct download+unlink."""
        ep = make_episode(fmt="mcap", status="ready")
        ep.storage_path = "s3://bucket/test.mcap"

        result = MagicMock()
        result.scalar_one_or_none.return_value = ep
        mock_db.execute = AsyncMock(return_value=result)

        with patch("app.routers.episodes.get_mcap_cache") as mock_get_cache, \
             patch("app.routers.episodes.StorageClient") as mock_storage_cls, \
             patch("app.routers.episodes.McapFrameExtractor") as mock_extractor:

            mock_cache = AsyncMock()
            mock_cache.get_or_download = AsyncMock(return_value="/tmp/cached_ep.mcap")
            mock_get_cache.return_value = mock_cache

            mock_extractor.return_value.__enter__ = MagicMock(return_value=mock_extractor.return_value)
            mock_extractor.return_value.__exit__ = MagicMock(return_value=False)
            mock_extractor.return_value.extract_frame.return_value = MagicMock(
                data=b"jpeg", timestamp_ns=0, format="jpeg"
            )

            resp = client.get(
                f"/api/v1/episodes/{ep.id}/frame?topic=/camera&timestamp=0",
                headers=auth_headers
            )

            assert resp.status_code == 200
            mock_cache.get_or_download.assert_called_once_with(
                str(ep.id), ep.storage_path, mock_storage_cls.return_value
            )

    def test_get_frame_does_not_delete_cached_file(self, client, auth_headers, mock_db):
        """Endpoint does not unlink file — cache manages lifecycle."""
        ep = make_episode(fmt="mcap", status="ready")
        ep.storage_path = "s3://bucket/test.mcap"

        result = MagicMock()
        result.scalar_one_or_none.return_value = ep
        mock_db.execute = AsyncMock(return_value=result)

        with patch("app.routers.episodes.get_mcap_cache") as mock_get_cache, \
             patch("app.routers.episodes.StorageClient"), \
             patch("app.routers.episodes.McapFrameExtractor") as mock_extractor, \
             patch("os.unlink") as mock_unlink:

            mock_cache = AsyncMock()
            mock_cache.get_or_download = AsyncMock(return_value="/tmp/cached_ep.mcap")
            mock_get_cache.return_value = mock_cache

            mock_extractor.return_value.__enter__ = MagicMock(return_value=mock_extractor.return_value)
            mock_extractor.return_value.__exit__ = MagicMock(return_value=False)
            mock_extractor.return_value.extract_frame.return_value = MagicMock(
                data=b"jpeg", timestamp_ns=0, format="jpeg"
            )

            client.get(
                f"/api/v1/episodes/{ep.id}/frame?topic=/camera&timestamp=0",
                headers=auth_headers
            )

            mock_unlink.assert_not_called()
```

Also delete the old `test_get_frame_cleans_up_temp_file` test (it no longer applies).

**Step 2: Run the new tests to verify they fail**

```bash
cd /home/xuhao/embedai/services/dataset-service
uv run pytest tests/test_frame_api.py::TestGetFrameEndpoint::test_get_frame_uses_cache \
             tests/test_frame_api.py::TestGetFrameEndpoint::test_get_frame_does_not_delete_cached_file \
             -v
```

Expected: FAIL with `ImportError: cannot import name 'get_mcap_cache'`

**Step 3: Update `main.py` — add lifespan with cache**

Replace `services/dataset-service/app/main.py` with:

```python
"""Dataset Service — FastAPI application entry point."""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.routers import datasets, episodes, exports
from app.services.mcap_cache import McapFileCache

_mcap_cache: McapFileCache | None = None


def get_mcap_cache() -> McapFileCache:
    """Return the application-level MCAP file cache."""
    assert _mcap_cache is not None, "Cache not initialized — app not started"
    return _mcap_cache


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _mcap_cache
    _mcap_cache = McapFileCache(max_size=5, ttl_seconds=300)
    yield
    if _mcap_cache:
        await _mcap_cache.clear()


app = FastAPI(title="EmbedAI Dataset Service", version="0.1.0", lifespan=lifespan)

app.include_router(episodes.router, prefix="/api/v1")
app.include_router(datasets.router, prefix="/api/v1")
app.include_router(exports.router, prefix="/api/v1")


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}
```

**Step 4: Update `episodes.py` — replace temp-file pattern with cache**

In `services/dataset-service/app/routers/episodes.py`, add this import at the top:

```python
from app.main import get_mcap_cache
```

Then replace the entire `get_frame` endpoint body (from `# Download file to temp location` to the end of the `finally` block):

```python
@router.get("/{episode_id}/frame")
async def get_frame(
    episode_id: uuid.UUID,
    topic: str = Query(..., description="Topic name to extract frame from"),
    timestamp: int = Query(..., description="Target timestamp in nanoseconds"),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Extract a single frame from MCAP file at specified timestamp."""
    project_id = uuid.UUID(current_user.project_id)

    result = await db.execute(
        select(Episode).where(
            Episode.id == episode_id,
            Episode.project_id == project_id,
        )
    )
    ep = result.scalar_one_or_none()
    if ep is None:
        raise HTTPException(status_code=404, detail="episode not found")

    if ep.format != "mcap":
        raise HTTPException(status_code=400, detail="only MCAP format supported")

    if not ep.storage_path:
        raise HTTPException(status_code=400, detail="episode file not available")

    # Get file from cache (downloads if not cached)
    storage = StorageClient()
    cache = get_mcap_cache()
    mcap_path = await cache.get_or_download(str(episode_id), ep.storage_path, storage)

    # Extract frame (no cleanup — cache manages the file lifecycle)
    with McapFrameExtractor(mcap_path) as extractor:
        time_range = extractor.get_time_range()
        mcap_start_time_ns = time_range[0] if time_range else 0

        frame = extractor.extract_frame(
            topic, timestamp, time_offset_ns=mcap_start_time_ns
        )

    if frame is None:
        raise HTTPException(status_code=404, detail="no frame found at specified time")

    return Response(
        content=frame.data,
        media_type="image/jpeg",
        headers={
            "X-Frame-Timestamp": str(frame.timestamp_ns),
            "Cache-Control": "private, max-age=300",
        },
    )
```

Also remove the `import tempfile` and `import os` that are now unused (if no longer needed elsewhere in the file).

**Step 5: Run the new tests**

```bash
cd /home/xuhao/embedai/services/dataset-service
uv run pytest tests/test_frame_api.py -v
```

Expected: All tests PASS. If `test_get_frame_download_failure` fails (it patches `StorageClient.download_to_file` but now goes through the cache), update it to patch `get_mcap_cache` to raise instead:

```python
    def test_get_frame_download_failure(self, client, auth_headers, mock_db):
        """Download failure returns 500."""
        ep = make_episode(fmt="mcap", status="ready")
        ep.storage_path = "s3://bucket/test.mcap"

        result = MagicMock()
        result.scalar_one_or_none.return_value = ep
        mock_db.execute = AsyncMock(return_value=result)

        with patch("app.routers.episodes.get_mcap_cache") as mock_get_cache:
            mock_cache = AsyncMock()
            mock_cache.get_or_download = AsyncMock(side_effect=Exception("Download failed"))
            mock_get_cache.return_value = mock_cache

            resp = client.get(
                f"/api/v1/episodes/{ep.id}/frame?topic=/camera&timestamp=0",
                headers=auth_headers
            )

            assert resp.status_code == 500
```

**Step 6: Run full dataset-service test suite**

```bash
cd /home/xuhao/embedai/services/dataset-service
uv run pytest tests/ -v
```

Expected: All tests PASS.

**Step 7: Commit**

```bash
cd /home/xuhao/embedai
git add services/dataset-service/app/main.py \
        services/dataset-service/app/routers/episodes.py \
        services/dataset-service/tests/test_frame_api.py
git commit -m "feat: wire McapFileCache into get_frame endpoint to avoid repeated MinIO downloads"
```

---

### Task 3: Rebuild and smoke-test

**Step 1: Rebuild dataset-service**

```bash
cd /home/xuhao/embedai
docker compose -f infra/docker-compose.prod.yml up -d --build dataset-service
```

Wait ~30s for startup.

**Step 2: Check logs are clean**

```bash
docker compose -f infra/docker-compose.prod.yml logs dataset-service --tail=30
```

Expected: No import errors, `Uvicorn running on` present.

**Step 3: Smoke-test via curl**

First, get a JWT token:

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@embedai.local","password":"Admin@2026!"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
```

List episodes to find a ready MCAP:

```bash
curl -s http://localhost:8000/api/v1/episodes?format=mcap \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool | head -40
```

If a ready MCAP exists, request a frame twice and confirm the second is faster:

```bash
EPISODE_ID=<id from above>
TOPIC=<image topic name>

time curl -s "http://localhost:8000/api/v1/episodes/$EPISODE_ID/frame?topic=$TOPIC&timestamp=0" \
  -H "Authorization: Bearer $TOKEN" -o /dev/null

time curl -s "http://localhost:8000/api/v1/episodes/$EPISODE_ID/frame?topic=$TOPIC&timestamp=0" \
  -H "Authorization: Bearer $TOKEN" -o /dev/null
```

Expected: First request: ~2–10s (download). Second request: <500ms (cache hit).

**Step 4: Commit (if any fix-ups were needed)**

```bash
cd /home/xuhao/embedai
git add -p
git commit -m "fix: adjust cache integration after smoke-test"
```

---

## Summary of changes

| File | Change |
|------|--------|
| `app/services/mcap_cache.py` | New — LRU disk cache with per-episode locks |
| `app/main.py` | Add lifespan + `get_mcap_cache()` singleton accessor |
| `app/routers/episodes.py` | Replace temp-file+unlink with `cache.get_or_download()` |
| `tests/test_mcap_cache.py` | New — unit tests for cache |
| `tests/test_frame_api.py` | Update tests to mock cache, remove deleted temp-file test |

**Expected performance impact:** Frame requests for a previously-fetched episode go from 2–10s (full MinIO download) to <100ms (local disk read + MCAP scan).
