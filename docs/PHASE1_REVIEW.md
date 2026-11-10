# Phase 1 Review — Data Models, Schema, Tools, Cache

| Field | Value |
|---|---|
| Status | Complete, pending approval for Phase 2 |
| Date | 2026-11-08 |
| Scope | Pydantic contracts, Postgres schema + Alembic, tool layer, record/replay cache, provider config, quota skeleton |
| Tests | 103 passed, 2 skipped (pgvector-dependent), 87.22% coverage |
| Lint/type | Ruff clean; mypy strict clean |

---

## 1. What was built

| Area | Artifacts |
|---|---|
| Contracts | `src/research_agent/models/` — sources, documents, chunks, evidence spans, claims, verdicts, citations, plan/report, approvals, tool I/O, LLM I/O, LangGraph state + reducers |
| Persistence | `src/research_agent/db/` — SQLAlchemy models for runs, events, sources, documents, chunks, claims, claim-evidence, citations, approvals, memory, idempotency, quota, jobs, provider health |
| Migrations | `alembic.ini`, `migrations/env.py`, `migrations/versions/16371720589d_initial_schema.py` (pgvector + HNSW + GIN) |
| Repositories | `RunRepository`, `SourceRepository`, `EvidenceRepository`, `PostgresQuotaStore` |
| Cache | `src/research_agent/cache/` — content-addressed record/replay/live store with typed envelopes |
| Search | SearXNG, Wikipedia, arXiv adapters with URL safety, retries, and caching |
| Fetch | Redirect-aware HTTP fetcher with SSRF checks, robots.txt, byte caps, content-type filtering |
| Parse | trafilatura HTML extraction, pypdf text extraction, parser cache |
| Embeddings | fastembed production embedder + deterministic HashEmbedder test double |
| Retrieval | Chunking with offsets/overlap, pgvector + tsvector hybrid retrieval via reciprocal rank fusion |
| LLM | OpenAI-compatible client (Groq/Gemini/Ollama), provider config loader, quota tracker, role router |
| Scripts | `provider_smoke.py`, `scan_cassettes.py` |
| Tests | 102 collected: unit, integration, contract, smoke |

---

## 2. Verification performed

```text
uv lock                         -> 167 packages resolved
uv run ruff check                -> clean
uv run ruff format --check       -> clean
uv run mypy src                  -> clean (strict)
uv run pytest                    -> 103 passed, 2 skipped
coverage                         -> 87.22%
```

Live smoke tests (public data, no paid services):

| Check | Result |
|---|---|
| Fetch `https://example.com/` | 200; parsed title "Example Domain" |
| Wikipedia search "Alan Turing" | 2 results; live API works with descriptive UA + `Accept: application/json` |
| arXiv search "retrieval augmented generation" | 2 results; Atom API works |
| fastembed `BAAI/bge-small-en-v1.5` | 384-dim vectors |
| LangGraph `interrupt` + Postgres saver | Verified against a throwaway local Postgres 18 cluster |
| Alembic offline SQL | Contains `CREATE EXTENSION vector`, `VECTOR(384)`, HNSW index |

**Not verified on this host:**

- SearXNG: Docker daemon is not running.
- pgvector migration apply/downgrade: local Postgres lacks the `vector` extension. CI uses `pgvector/pgvector:pg16` and will exercise it.
- Live Groq/Gemini/Ollama calls: no API keys configured. Run `uv run python scripts/provider_smoke.py --live --provider groq`.
- DSPy live optimization: Phase 6.

---

## 3. Key implementation decisions

| Decision | Why |
|---|---|
| SQLAlchemy async engine with `postgresql+psycopg` | Same driver for async app and sync Alembic; no extra dependency |
| `TypedDict` graph state with Pydantic payloads | LangGraph reducers stay simple; validation stays at boundaries |
| String enums + CHECK constraints | Avoid Postgres enum migration pain; Pydantic enums at the edge |
| Generated `tsvector` column | Keyword retrieval without a separate search service |
| HNSW index on `vector(384)` | Local semantic retrieval with pgvector |
| Content-addressed cache keys include tool/version/config | Prevent false hits after prompt/parser changes |
| Cache `put` only writes in `record` mode | `live` and `replay` cannot mutate fixtures |
| Quota reservations in Postgres | Restart-safe daily budget; minute windows are process-local |
| `Accept` header per search adapter | Wikipedia returned 403 for a generic client; explicit JSON/Atom Accept fixed it |
| Mypy target 3.12 | Runtime supports 3.11+, but numpy 2.5 stubs use PEP 695 syntax; CI uses 3.12 |

---

## 4. Deviations / discoveries

1. **Windows event loop.** psycopg async cannot use `ProactorEventLoop`. `configure_windows_event_loop()` must run before any async DB or LangGraph saver use. Tests set it in `conftest.py`.
2. **LangGraph Postgres saver ownership.** The saver creates `checkpoints`, `checkpoint_writes`, `checkpoint_blobs`, and `checkpoint_migrations` in `public`. The Alembic migration deliberately does **not** create them; document this in Phase 3.
3. **Wikipedia needs an explicit Accept header.** A descriptive User-Agent alone still returned 403 from `httpx`; `Accept: application/json` fixed it.
4. **pgvector unavailable locally.** The migration apply/downgrade test skips on this host. This is an environment gap, not a code gap.
5. **Pre-existing Phase 0/2 files preserved.** The repo already had `config.py`, `api/app.py`, `api/schemas.py`, and config tests; they were extended/reused rather than replaced.
6. **Mypy target changed to 3.12.** The project still supports 3.11 at runtime; the dev/CI interpreter is 3.12 and numpy 2.5's stubs cannot be parsed at 3.11.

---

## 5. Risks introduced or still open

| Risk | Status |
|---|---|
| R-01 LangGraph/DSPy churn | LangGraph verified; DSPy only import-verified |
| R-11 Saver vs Alembic table ownership | Discovered; saver owns checkpoint tables, app owns domain tables |
| R-14 SSRF | Implemented and tested (private IPs, redirects, IPv6, credentials) |
| R-20 Snapshots not frozen | Cache keys include tool/version/config; replay misses fail loudly |
| R-02 Quota capacity | Tracker skeleton works; actual limits still placeholders |
| pgvector migration | Not applied locally; CI must verify |
| SearXNG | Not started; only mocked tests |
| Live LLM | Not called; provider smoke required when keys exist |

---

## 6. Open questions for Phase 2

1. Should the API own the worker loop, or run a separate `python -m research_agent.worker` process? Proposal: separate worker; API only enqueues.
2. Should `POST /v1/runs` return 202 with a `Location` header and require `Idempotency-Key`? Proposal: yes.
3. Should the single-agent baseline use the same `LLMRouter` role (`planner`) or a dedicated `react` role? Proposal: add `react` role in config.
4. Do we need a `/readyz` that checks Postgres and the provider config before Phase 2? Proposal: yes, cheap.
5. Should migration apply run automatically in local compose, or only via `make migrate`? Proposal: explicit `make migrate`; production never auto-migrates.

---

## 7. Recommended Phase 2 first task

Build the single-agent baseline end-to-end behind the existing contracts:

1. `ResearchArchitecture` protocol + `SingleAgentGraph`.
2. Tool registry with typed `search`, `fetch`, `parse`, `retrieve`.
3. Budget ledger + loop guards.
4. Minimal API: `POST /v1/runs`, `GET /v1/runs/{id}`, report, SSE.
5. Postgres job queue + worker.
6. Contract tests and a replay smoke run.

Stop after Phase 2 with a demo run and a cost/token report.

---

## 8. Approval requested

Reply **"go"** to start Phase 2, or answer the open questions above. No commits were made; all files are untracked for review.
