"""Application-level cache registry — holds the McapFileCache singleton."""
from __future__ import annotations

from app.services.mcap_cache import McapFileCache

_mcap_cache: McapFileCache | None = None


def get_mcap_cache() -> McapFileCache:
    """Return the application-level MCAP file cache.

    If the cache has not been initialised via ``init_mcap_cache`` (e.g. in
    unit tests that bypass the FastAPI lifespan), a default instance is
    created lazily so that tests work without special setup.
    """
    global _mcap_cache
    if _mcap_cache is None:
        _mcap_cache = McapFileCache(max_size=5, ttl_seconds=300)
    return _mcap_cache


def init_mcap_cache(max_size: int = 5, ttl_seconds: int = 300) -> McapFileCache:
    """Create and register the cache singleton (called from lifespan)."""
    global _mcap_cache
    _mcap_cache = McapFileCache(max_size=max_size, ttl_seconds=ttl_seconds)
    return _mcap_cache


async def clear_mcap_cache() -> None:
    """Clear and release the cache singleton (called from lifespan shutdown)."""
    global _mcap_cache
    if _mcap_cache is not None:
        await _mcap_cache.clear()
        _mcap_cache = None
