# syntax=docker/dockerfile:1.7
# Pin the uv image tag; bump deliberately and re-run CI.
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PIP_NO_CACHE_DIR=1

COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /uvx /bin/

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

# Dependency layer: copy only what uv needs to resolve/install.
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY config ./config
COPY alembic.ini ./alembic.ini
COPY migrations ./migrations

RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

# The API app lands in Phase 2. The `app` compose profile is opt-in until then.
CMD ["uvicorn", "research_agent.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
