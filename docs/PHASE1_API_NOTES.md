# Phase 1 API Notes

Verified against the pinned versions in `uv.lock` on 2026-11-08. "Verified" means the import/signature or a minimal call was exercised locally. Live provider calls marked "not run" require API keys and are covered by `scripts/provider_smoke.py`.

## Resolved and verified versions

| Package | Version | Status |
|---|---|---|
| `langgraph` | 1.2.20 | Verified: TypedDict graph, `interrupt`, `Command(resume=...)`, `MemorySaver` |
| `langgraph-checkpoint-postgres` | 3.2.0 | Verified: `AsyncPostgresSaver.from_conn_string` + `await saver.setup()` |
| `dspy` | 3.4.1 | Imports/signatures verified; live provider call not run |
| `fastapi` | 0.162.2 | Verified via contract tests |
| `pydantic` | 2.14.3 | Verified via model tests |
| `sqlalchemy` | 2.1.8 | Verified via repository tests |
| `psycopg` | 3.3.8 | Verified async + sync |
| `pgvector` | 0.5.1 | SQL/type generation verified; extension not installed on this host |
| `fastembed` | 0.9.1 | Verified: `BAAI/bge-small-en-v1.5` loads and returns 384-dim vectors |
| `trafilatura` | 2.3.1 | Verified: `extract` + `extract_metadata` |
| `pypdf` | 6.21.4 | Verified: text extraction from a generated PDF |
| `alembic` | 1.20.1 | Verified offline SQL; apply test skipped without pgvector |

## Checklist

| Item | Verified? | Notes |
|---|---|---|
| LangGraph state schema (`TypedDict` + Pydantic fields) | Yes | `StateGraph(ResearchState)` compiles; reducers accept typed lists |
| `StateGraph` / conditional edges / `compile(checkpointer=...)` | Yes | See `docs/PHASE1_REVIEW.md` and graph spike |
| `interrupt()` / `Command(resume=...)` | Yes | First invoke returns `__interrupt__`; resume returns merged state |
| `langgraph-checkpoint-postgres` async saver | Yes | `async with AsyncPostgresSaver.from_conn_string(dsn) as saver` |
| Saver `.setup()` and table ownership | Yes | Creates `checkpoints`, `checkpoint_writes`, `checkpoint_blobs`, `checkpoint_migrations` in `public`; do not create these in Alembic |
| DSPy `LM` / `configure` / `BootstrapFewShot` | Partially | Signatures verified; no live call without keys; Phase 6 |
| DSPy structured output | Not yet | Phase 6; fallback is JSON repair + Pydantic validation |
| Groq / Gemini OpenAI-compatible URLs | Not run | Config template only; run `provider_smoke.py --live` |
| Ollama endpoint | Not run | Requires `--profile ollama` |
| fastembed on Windows | Yes | 384-dim vectors, model downloaded to cache |
| SearXNG JSON + health | Not run | Docker daemon unavailable on this host; compose config valid |
| pgvector extensions | Not run locally | CI uses `pgvector/pgvector:pg16`; local Postgres lacks `vector` |
| Wikipedia live search | Yes | Requires a descriptive User-Agent and `Accept: application/json`; without Accept it returned 403 |
| arXiv live search | Yes | Atom API returned results |
| Live fetch + HTML parse | Yes | `https://example.com/` fetched and parsed |
| Alembic offline SQL | Yes | Contains `CREATE EXTENSION ... vector` and `VECTOR(384)` |
| Alembic upgrade/downgrade | Not run locally | Skipped because pgvector is unavailable; CI should run it |

## Important environment note

psycopg's async driver cannot use Windows' default `ProactorEventLoop`. Call `configure_windows_event_loop()` at every asyncio entry point (API, worker, scripts) and in `tests/conftest.py`. Without it, `AsyncPostgresSaver` fails with `Psycopg cannot use the 'ProactorEventLoop'`.

## Remaining Phase 2 verification

- Live Groq/Gemini JSON-mode calls.
- SearXNG JSON endpoint inside Docker.
- Full Alembic upgrade/downgrade against the pgvector image.
- Ollama model availability.
- SSE + approval resume contract tests.
