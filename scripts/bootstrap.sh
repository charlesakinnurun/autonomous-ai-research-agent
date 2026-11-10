#!/usr/bin/env bash
# Bootstrap the Phase 0 scaffold on macOS/Linux. Safe to re-run.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> Checking prerequisites"
for cmd in uv docker; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Missing prerequisite: $cmd" >&2
    exit 1
  fi
done

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "==> Created .env from .env.example (fill in provider keys when ready)"
fi
if [[ ! -f config/providers.yaml ]]; then
  cp config/providers.example.yaml config/providers.yaml
  echo "==> Created config/providers.yaml; verify limits in each provider console"
fi

echo "==> Installing Python dependencies"
uv sync --group dev

echo "==> Starting Postgres + SearXNG"
docker compose up -d postgres searxng

echo "==> Waiting for Postgres"
postgres_ready=0
for _ in $(seq 1 30); do
  if docker compose exec -T postgres pg_isready -U research -d research >/dev/null 2>&1; then
    postgres_ready=1
    break
  fi
  sleep 1
done
if [[ "$postgres_ready" -ne 1 ]]; then
  echo "Postgres did not become ready" >&2
  exit 1
fi

echo "==> Waiting for SearXNG"
searxng_ready=0
for _ in $(seq 1 30); do
  if curl -fsS http://localhost:8080/ >/dev/null 2>&1; then
    searxng_ready=1
    break
  fi
  sleep 1
done
if [[ "$searxng_ready" -ne 1 ]]; then
  echo "SearXNG did not become ready" >&2
  exit 1
fi

echo "==> Applying database migrations"
uv run alembic upgrade head

echo
echo "Ready. Next:"
echo "  uv run pytest"
echo "  uv run python -m research_agent"
echo "  docker compose logs -f"
