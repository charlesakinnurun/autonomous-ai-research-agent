.DEFAULT_GOAL := help
PY := uv run

.PHONY: help install install-eval lock fmt lint type test cov check dev up app down logs psql migrate revision eval-smoke clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: ## Install runtime + dev dependencies
	uv sync --group dev

install-eval: ## Install runtime + dev + eval dependencies
	uv sync --all-groups

lock: ## Regenerate uv.lock
	uv lock

fmt: ## Format with ruff
	$(PY) ruff format .
	$(PY) ruff check --fix .

lint: ## Lint without modifying files
	$(PY) ruff format --check .
	$(PY) ruff check .

type: ## Type-check src with mypy (strict)
	$(PY) mypy src

test: ## Run tests that do not need live providers
	$(PY) pytest -m "not live and not slow"

cov: ## Run tests with the coverage gate
	$(PY) pytest -m "not live and not slow" --cov --cov-report=term-missing

check: lint type cov ## Everything CI runs on a PR

dev: ## Run the API locally with reload (Phase 2)
	$(PY) uvicorn research_agent.api.app:app --reload --host 127.0.0.1 --port 8000

up: ## Start Postgres + SearXNG (dev services)
	docker compose up -d postgres searxng

app: ## Build and start the app container (Phase 2+)
	docker compose --profile app up -d --build

down: ## Stop the stack
	docker compose down

logs: ## Tail service logs
	docker compose logs -f --tail=100

psql: ## Open psql against the compose database
	docker compose exec postgres psql -U research -d research

migrate: ## Apply Alembic migrations (Phase 1+)
	$(PY) alembic upgrade head

revision: ## Create an Alembic revision: make revision m="add runs"
	$(PY) alembic revision --autogenerate -m "$(m)"

eval-smoke: ## Run the replay-only smoke eval (Phase 5+)
	$(PY) pytest -m eval

clean: ## Remove local caches
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
