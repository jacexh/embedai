# ── Build stage: install dependencies with uv ───────────────────────────────
FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim AS builder

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN uv sync --frozen --no-dev

# ── Runtime stage ───────────────────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

COPY --from=builder /app /app

ENV PATH="/app/.venv/bin:$PATH"

CMD ["python", "-m", "worker.main"]
