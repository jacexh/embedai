"""Task Service — FastAPI application entry point."""
from fastapi import FastAPI

from app.routers import tasks, webhooks

app = FastAPI(title="EmbedAI Task Service", version="0.1.0")

app.include_router(tasks.router, prefix="/api/v1")
app.include_router(webhooks.router, prefix="/api/v1")


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}
