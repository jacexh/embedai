"""Dataset Service — FastAPI application entry point."""
from fastapi import FastAPI

from app.routers import datasets, episodes

app = FastAPI(title="EmbedAI Dataset Service", version="0.1.0")

app.include_router(episodes.router, prefix="/api/v1")
app.include_router(datasets.router, prefix="/api/v1")


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}
