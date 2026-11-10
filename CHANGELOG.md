# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Phase 1 typed contracts: sources, documents, chunks, evidence spans, claims, verdicts, citations, plans/reports, approvals, tool I/O, LLM I/O, and LangGraph state reducers.
- Postgres schema + Alembic migration for runs, events, sources, documents, chunks, claims, claim-evidence, citations, approvals, memory, idempotency, quota, jobs, and provider health.
- pgvector HNSW and generated `tsvector` GIN indexes; local embeddings via fastembed.
- Tool layer: SearXNG/Wikipedia/arXiv adapters, SSRF-safe fetcher, robots.txt, HTML/PDF parsing, token-aware chunking, hybrid retrieval.
- Content-addressed record/replay/live cache for LLM, search, fetch, and parse calls.
- Provider config loader, OpenAI-compatible LLM client, role router, and Postgres-backed quota tracker.
- `provider_smoke.py` and `scan_cassettes.py` scripts.
- Phase 1 review and verified API notes.
- Test suite: 103 passed, 2 pgvector-dependent skips, 87.22% coverage.

### Changed

- Mypy target is Python 3.12 for dev/CI (runtime still supports 3.11+); numpy 2.5 stubs use PEP 695 syntax.
- Search adapters send explicit `Accept` headers (Wikipedia returns 403 otherwise).
- `configure_windows_event_loop()` is required for psycopg async on Windows.

### Planned

- Phase 2: single-agent baseline + minimal API.
- Phase 3: multi-agent LangGraph + checkpoints + approvals.
- Phase 4: evidence store + claim-level verification.
- Phase 5: evaluation harness + dataset + judge calibration.
- Phase 6: DSPy modules + optimization + ablations.
- Phase 7: observability, security, load/failure testing.
- Phase 8: docs, final evaluation, v0.1.0 release.

## [0.1.0] - 2026-11-07

### Added

- Phase 0 design package:
  - `docs/DESIGN.md` — architecture, data model, failure modes, tradeoffs.
  - `docs/REQUIREMENTS.md` — functional/non-functional requirements and traceability.
  - `docs/RISKS.md` — risk register.
  - `docs/QUOTA_PLAN.md` — token math and free-tier capacity plan.
  - `docs/EVAL_PLAN.md` — dataset, metrics, judge calibration, statistics.
  - `docs/ROADMAP.md` — 6-week phase plan.
  - Seven ADRs covering orchestration, LLM routing, caching, citations, benchmark design, DSPy, and the job queue.
- Repo scaffold: `uv`/hatchling package, ruff, mypy strict, pytest, coverage, pre-commit.
- Docker Compose with Postgres + pgvector and SearXNG; optional Ollama profile.
- Provider, budget, and retrieval configuration templates.
- GitHub Actions: lint/type/test CI and a guarded manual full-eval workflow.
- MIT license, README, CONTRIBUTING, and this changelog.

### Notes

- This release does **not** run research yet. It is the design and scaffold phase.
- Free-tier provider limits in `config/providers.example.yaml` are placeholders and must be verified.

[Unreleased]: https://github.com/your-org/autonomous-ai-research-agent/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/your-org/autonomous-ai-research-agent/releases/tag/v0.1.0
