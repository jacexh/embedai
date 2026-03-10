"""Dataset Service — FastAPI application entry point."""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.routers import datasets, episodes, exports
from app.services.cache_registry import clear_mcap_cache, get_mcap_cache, init_mcap_cache


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_mcap_cache(max_size=5, ttl_seconds=300)

    async def _cleanup_loop() -> None:
        while True:
            await asyncio.sleep(60)
            try:
                await get_mcap_cache().cleanup_expired()
            except Exception:
                pass

    task = asyncio.create_task(_cleanup_loop())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    await clear_mcap_cache()


app = FastAPI(title="EmbedAI Dataset Service", version="0.1.0", lifespan=lifespan)

app.include_router(episodes.router, prefix="/api/v1")
app.include_router(datasets.router, prefix="/api/v1")
app.include_router(exports.router, prefix="/api/v1")


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}
