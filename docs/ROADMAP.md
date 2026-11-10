# Roadmap — 6 Weeks, Part-Time

| Field | Value |
|---|---|
| Team | Solo developer + AI pair |
| Cadence | ~10–15 hours/week |
| Deployment | Laptop docker-compose only |
| Budget | $0 billed; 31.5M token envelope (see `QUOTA_PLAN.md`) |
| Rule | Stop at each phase, summarize, list risks/open questions, wait for approval |
| Completed | Phase 0 (design/scaffold), Phase 1 (contracts/schema/tools/cache) — see `PHASE1_REVIEW.md` |

---

## Phase overview

| Phase | Week | Deliverable | Demo |
|---|---:|---|---|
| 0 | 1 | Design, requirements, risks, quota plan, scaffold | `docker compose up`, `make check` |
| 1 | 1–2 | Models, Postgres schema, tools, record/replay cache | Search + fetch + parse + cache round-trip |
| 2 | 2 | Single-agent baseline + minimal API | One question → cited report |
| 3 | 3 | Multi-agent graph + checkpoints + approvals | Restart/resume + approve/reject |
| 4 | 3–4 | Evidence store + claim/citation verification | Every claim has a verdict + span |
| 5 | 4–5 | Eval harness + dataset + judge calibration | 5-question replay eval + calibration report |
| 6 | 5 | DSPy modules + optimization + ablations | E0–E3 with CIs + Pareto |
| 7 | 6 | Observability, cost controls, security, load tests | Trace + quota pause/resume + SSRF/injection suite |
| 8 | 6 | Docs, diagrams, final `EVALUATION.md`, release | v0.1.0 tag |

---

## Phase 0 - Design and scaffold (complete)

**Deliverables**

- Design doc, requirements, risk register, quota plan, eval plan, ADRs.
- Repo scaffold: `pyproject.toml`, uv lock, ruff/mypy/pytest/pre-commit, Dockerfile, compose, SearXNG/Postgres config, CI workflows, Makefile, `.env.example`, LICENSE, CHANGELOG, CONTRIBUTING.
- Package import + trivial test; no research logic.

**Exit criteria**

- [x] Design reviewed and approved.
- [x] `uv sync --group dev` succeeds.
- [x] `make check` green (ruff, format, mypy, pytest).
- [ ] `docker compose up -d postgres searxng` healthy. (Docker daemon unavailable on the authoring host.)
- [x] Provider limits template exists; user knows to verify them.
- [x] No Phase 1 code merged during Phase 0.

**Risks**

- Library API assumptions (R-01).
- Quota numbers are estimates (R-02).
- Scaffold may overfit to unverified APIs.

---

## Phase 1 - Data models, schema, tools, cache (complete)

**Deliverables**

- Pydantic v2 models: `Source`, `Document`, `Chunk`, `EvidenceSpan`, `Claim`, `ClaimVerdict`, `Citation`, `ResearchState`, tool I/O, API schemas.
- SQLAlchemy models + Alembic migration for all v0.1 tables (except LangGraph-managed tables).
- Repository layer with typed methods; no raw SQL in nodes.
- Tool layer: SearXNG, Wikipedia, arXiv, fetch, HTML parse, PDF parse, retrieve.
- SSRF/URL validation, robots.txt, timeouts, retries, byte caps.
- Record/replay cache for LLM/search/fetch; `record`/`replay`/`live` modes.
- Provider config loader + quota tracker skeleton.
- Unit tests with mocked HTTP; integration tests against Postgres.
- `scripts/provider_smoke.py`.

**Exit criteria**

- [x] Offline Alembic SQL verified; apply/downgrade test is skipped locally without pgvector and runs in CI's `pgvector/pgvector:pg16` service.
- [x] Search (Wikipedia + arXiv) + fetch + parse a public page in live mode.
- [x] Replay the same calls with zero network (unit tests).
- [x] Cache miss in replay fails loudly.
- [x] SSRF tests block private IPs, redirects, IPv6 loopback, and credentials.
- [x] Coverage ≥80% (87.22%).
- [x] API notes documented (`docs/PHASE1_API_NOTES.md`).
- [ ] Vector index/retrieval test against a live pgvector extension (CI-only; skipped on the authoring host).

**Demo:** unit/integration tests exercise chunking, embedding, indexing, and hybrid retrieval; pgvector-dependent tests are skipped locally and run in CI.

---

## Phase 2 — Single-agent baseline + minimal API

**Deliverables**

- `ResearchArchitecture` protocol shared by both architectures.
- Single-agent ReAct graph with `search`, `fetch`, `retrieve`, `write_report`.
- Budget ledger, loop guards, structured output validation.
- Minimal FastAPI: `POST /v1/runs`, `GET /v1/runs/{id}`, report endpoint, SSE.
- Postgres job queue + worker.
- Trace/cost endpoints (basic).
- Contract tests.

**Exit criteria**

- [ ] One live question produces a cited report.
- [ ] Same question replays deterministically.
- [ ] SSE reconnect with `Last-Event-ID` works.
- [ ] Idempotency: duplicate POST returns same run; different body → 409.
- [ ] Budget exhaustion produces a partial report, not a crash.
- [ ] Every kept claim has a citation.

**Demo:** `curl` start → stream → fetch report.

---

## Phase 3 — Multi-agent graph, checkpoints, approvals

**Deliverables**

- LangGraph multi-agent graph: intake, planner, researcher, evidence store, coverage critic, writer, claim extractor, verifier, report critic, approval gate, finalize.
- Postgres checkpointer; resume after restart.
- Approval service: expensive search, memory write, export.
- Typed state + reducers; bounded loops + no-progress guard.
- Integration tests: restart/resume, approve/reject, max loops.

**Exit criteria**

- [ ] Kill worker mid-run; resume completes without rerunning completed nodes.
- [ ] Approval persists across restart; approve/resume and reject/stop both work.
- [ ] Loop caps enforced; no-progress terminates.
- [ ] Single- and multi-agent share the same tool/budget/output contracts.
- [ ] Contract test proves fairness controls.

**Demo:** Multi-agent run pauses for approval, resumes, finishes.

---

## Phase 4 — Evidence store and citation pipeline

**Deliverables**

- Chunking, embeddings, dedupe, hybrid retrieval (vector + tsv), rerank.
- Evidence spans with offsets, quotes, quality scores.
- Claim extraction + entailment verifier; verdict persistence.
- Citation renderer/validator; unsupported-claim removal/flagging.
- Contradiction handling and "sources disagree" section.
- Tests: dangling citation, fabricated URL, unsupported claim, conflicting sources.

**Exit criteria**

- [ ] Every kept claim has ≥1 span + verdict.
- [ ] Renderer rejects dangling markers and invented URLs.
- [ ] Unsupported claims never appear in the main body.
- [ ] Contested question preserves ≥2 positions.
- [ ] Retrieval recall@10 measured on a small gold set.

**Demo:** Report with claim→span→verdict trace visible in JSON.

---

## Phase 5 — Evaluation harness, dataset, judge calibration

**Deliverables**

- 50-question dataset (30/10/10, 10 per category), gold answers/claims/evidence.
- Frozen cassettes for every question.
- Harness: run matrix, replay, metrics, bootstrap CIs, paired tests, Pareto plots.
- Judge protocol + calibration set (≥100 human labels).
- `EVALUATION.md` generator (initial version).
- PR smoke eval (5 questions) in CI.

**Exit criteria**

- [ ] Dataset validation passes; test hash frozen.
- [ ] Replay smoke eval runs in <3 min with zero network.
- [ ] Judge κ ≥0.6 on calibration, or documented remediation.
- [ ] E0/E1 results generated with CIs.
- [ ] Failure taxonomy populated.

**Demo:** `make eval-smoke` and an initial results table.

---

## Phase 6 — DSPy modules, optimization, ablations

**Deliverables**

- DSPy signatures/modules: decomposition, query gen, evidence extraction, claim extraction, verification, section writing, critic.
- Hand-written fallbacks behind the same interfaces.
- Metrics for optimization (verdict accuracy, citation precision/recall, groundedness, length/cost).
- BootstrapFewShot on the verifier; MIPROv2 only if budget allows.
- Compiled artifacts + manifests (optimizer, seed, dataset hash, scores, cost).
- Ablations: hand vs DSPy per module; E0–E3.
- Overfitting/leakage checks.

**Exit criteria**

- [ ] Compiled artifacts load and validate hashes.
- [ ] Hand-written fallback works when artifacts are missing.
- [ ] Dev/test gap reported; no test leakage.
- [ ] Optimization cost in tokens/calls reported.
- [ ] E2/E3 results with CIs and Pareto plots.

**Demo:** Side-by-side hand vs DSPy verifier on dev.

---

## Phase 7 — Observability, cost controls, security, failure tests

**Deliverables**

- OTel spans (optional exporter) + structured logs + trace UI via API.
- Quota pause/resume end-to-end; fallback chain; cooldown.
- Security suite: SSRF, prompt injection canary, secret redaction, domain deny list, byte caps.
- Load test: 5 concurrent runs, Postgres pool, SSE backpressure.
- Chaos tests: provider 500, timeout, empty search, malformed JSON, worker kill.
- Retention/prune script.

**Exit criteria**

- [ ] Quota exhaustion pauses and resumes a run.
- [ ] Injection canary cannot trigger a tool call.
- [ ] SSRF suite passes.
- [ ] 5 concurrent runs complete without deadlock.
- [ ] Failure taxonomy covers all injected failures.
- [ ] p95 status endpoint <100 ms.

**Demo:** Kill a provider mid-run; fallback completes; trace shows it.

---

## Phase 8 — Docs, final evaluation, release

**Deliverables**

- README architecture diagram + verified quickstart.
- Design doc, ADRs, API docs, CONTRIBUTING, limitations.
- Final `EVALUATION.md` with tables, plots, honest analysis.
- CHANGELOG, semver tag `v0.1.0`, license.
- Release checklist + known issues.

**Exit criteria**

- [ ] Quickstart <5 min on a clean machine.
- [ ] All CI green; replay smoke passes.
- [ ] `EVALUATION.md` generated from raw results.
- [ ] Regression gates documented.
- [ ] Limitations and future work specific, not generic.
- [ ] v0.1.0 tagged.

---

## Cut list (in order)

If time or quota runs short:

1. Drop MIPROv2; keep BootstrapFewShot.
2. Drop the 50-question coverage run; keep the 90-run test matrix.
3. Drop PDF parsing; keep HTML.
4. Drop OTel exporter; keep structured logs + run_events.
5. Drop load test; keep failure injection.
6. Drop optional supervisor/router (already out of scope).

Do not cut: evidence invariants, replay, approval persistence, judge calibration, test split.

---

## Weekly check-in template

```markdown
## Week N
- Built:
- Verified:
- Metrics/usage:
- Risks opened/closed:
- Cut or deferred:
- Questions for review:
- Next week:
```
