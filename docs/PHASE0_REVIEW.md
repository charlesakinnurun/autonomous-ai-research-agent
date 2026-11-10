# Phase 0 Review

| Field | Value |
|---|---|
| Status | Complete, pending approval to start Phase 1 |
| Date | 2026-11-08 |
| Scope | Design, requirements, risks, quota plan, scaffold |
| Code | Package scaffold only; no research pipeline |

---

## 1. Deliverables

| Deliverable | Location | Status |
|---|---|---|
| Design doc | [`DESIGN.md`](DESIGN.md) | ✅ |
| Requirements + traceability | [`REQUIREMENTS.md`](REQUIREMENTS.md) | ✅ |
| Risk register | [`RISKS.md`](RISKS.md) | ✅ |
| Quota plan + token math | [`QUOTA_PLAN.md`](QUOTA_PLAN.md) | ✅ |
| Evaluation plan | [`EVAL_PLAN.md`](EVAL_PLAN.md) | ✅ |
| Roadmap / exit criteria | [`ROADMAP.md`](ROADMAP.md) | ✅ |
| Limitations | [`LIMITATIONS.md`](LIMITATIONS.md) | ✅ |
| ADRs (7) | [`adr/`](adr/) | ✅ |
| API verification checklist | [`PHASE1_API_NOTES.md`](PHASE1_API_NOTES.md) | ✅ |
| Repo scaffold | `pyproject.toml`, `uv.lock`, `Makefile`, `Dockerfile`, `docker-compose.yml` | ✅ |
| Tooling | ruff, mypy strict, pytest, coverage, pre-commit | ✅ |
| CI | `.github/workflows/ci.yml`, `full-eval.yml` | ✅ |
| Config templates | `config/providers.example.yaml`, `budgets.yaml`, `retrieval.yaml` | ✅ |
| Docker services | Postgres+pgvector, SearXNG, optional Ollama | ✅ |
| Tests | 13 scaffold tests, 100% coverage of implemented code | ✅ |

---

## 2. Verification performed

```text
uv lock                     -> 167 packages resolved
uv sync --group dev         -> installed
uv run ruff check .         -> pass
uv run ruff format --check  -> pass (46 files)
uv run mypy src             -> pass (strict)
uv run pytest               -> 13 passed, 100% coverage
uv run pytest -m smoke      -> 2 passed
uv run python -m research_agent -> prints version/scaffold notice
docker compose config -q    -> valid YAML
```

**Not verified:** Docker daemon is not running on this host, so Postgres/SearXNG were not started. The compose file validates; run `docker compose up -d postgres searxng` when Docker is available.

---

## 3. Key decisions

| Decision | Alternative rejected | Why |
|---|---|---|
| LangGraph for orchestration | CrewAI, AutoGen, custom FSM | Checkpoints, interrupts, explicit typed graph |
| TypedDict of Pydantic models | Pydantic BaseModel graph state | Reducers are simpler; validation stays |
| Thin OpenAI-compatible router + Postgres quota | LiteLLM router | Full control of quotas, replay, fallback |
| Postgres + pgvector | Qdrant/Chroma | One ops surface; sufficient scale |
| Filesystem content-addressed cache | Redis/VCR | Reviewable cassettes; zero network in CI |
| SSE + Postgres queue | WebSocket + Celery/Redis | No extra service; durable reconnect |
| DSPy inside nodes | DSPy as orchestrator | LangGraph owns state/approval |
| 3 seeds on test + 1 on coverage | 3 seeds on all 50 | ~53M tokens / 7–8 weeks otherwise |

---

## 4. Assumptions

- Solo developer, ~10–15 hours/week, 6 weeks.
- Groq + Gemini free tiers are available; Ollama for local fallback.
- SearXNG runs self-hosted; Wikipedia/arXiv are the scholarly fallbacks.
- Free-tier limits are **placeholders** in `config/providers.example.yaml` and must be verified.
- LangGraph/DSPy APIs resolved (1.2.20 / 3.4.1) but not yet call-verified; Phase 1 starts with a spike.
- Public questions only; no private or sensitive data.
- Laptop has enough RAM for Postgres, SearXNG, and optionally Ollama.

---

## 5. Open questions for review

1. **Approval policy:** block export when >20% claims are `insufficient`, or flag only?
2. **Contested topics:** synthesis of positions (proposed) vs a single answer with caveats?
3. **Memory scope:** per-user preferences only, or also cross-run source-quality priors?
4. **Judge:** Gemini↔Groq cross-family judging (proposed), with local Qwen for smoke audits?
5. **Report format:** Markdown + JSON in v0.1 (proposed); HTML/PDF later?
6. **Benchmark deviation:** approve 3 seeds on the 10-question test split + 1 seed on all 50? A literal 3 seeds × 50 is ~53M tokens and 7–8 weeks.
7. **Docker:** is Docker Desktop available on the target laptop? It was not running here.

---

## 6. Risks to watch in Phase 1

- R-01: LangGraph/DSPy API mismatch. Mitigation: day-1 spike + notes before code.
- R-02: quota lower than planned. Mitigation: quota tracker, replay, Ollama-first.
- R-11: checkpoint tables vs Alembic. Mitigation: verify saver setup on empty DB.
- R-20: snapshots not truly frozen. Mitigation: content hashes + replay miss fails.

---

## 7. Recommended first Phase 1 task

Run the API spike in `docs/PHASE1_API_NOTES.md`:

1. LangGraph TypedDict state + conditional edge + `interrupt()` + Postgres checkpointer.
2. DSPy LM against Groq/Gemini + save/load a compiled program.
3. fastembed model load on Windows + Linux container.
4. SearXNG JSON query from inside Docker.
5. pgvector `vector` + `pg_trgm` extensions.

Only after that, implement models, migrations, and the tool layer.

---

## 8. Approval requested

Reply with:

- **"go"** to start Phase 1 with the stated assumptions, or
- answers to the open questions plus any scope changes.

No commits were made. All files are untracked and ready for your review.
