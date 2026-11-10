# Requirements

| Field | Value |
|---|---|
| Version | 0.1.0 (Phase 0) |
| Status | Draft |
| Scope | v0.1 laptop-only, $0 budget |

Requirement IDs are stable. Every requirement maps to a design section and a verification method. "Must" = release blocker; "Should" = release quality; "May" = future.

---

## 1. Functional requirements

### 1.1 Research workflow

| ID | Requirement | Priority | Verification |
|---|---|---|---|
| FR-01 | Accept a natural-language research question and optional constraints (`as_of`, max budget, domain allow/deny, report style). | Must | API contract test |
| FR-02 | Decompose the question into bounded sub-questions (≤6) with explicit dependencies and search queries. | Must | Unit test on planner output; integration test |
| FR-03 | Execute plan → act → observe → reflect loops with hard caps on loops, steps, tool calls, tokens, and wall-clock. | Must | Graph integration test; budget unit tests |
| FR-04 | Retrieve sources via SearXNG, Wikipedia, and arXiv behind one search interface. | Must | Tool unit tests with mocked HTTP |
| FR-05 | Fetch and parse HTML and text-layer PDFs; enforce timeouts, size caps, content-type allowlist, and SSRF protection. | Must | Unit/integration tests; SSRF test suite |
| FR-06 | Normalize, chunk, embed, dedupe, and rank evidence; persist chunks in pgvector. | Must | Integration test with Postgres |
| FR-07 | Extract atomic claims from the draft and verify each against its cited span. | Must | Unit tests + eval |
| FR-08 | Produce a structured report with inline citations and a references table. | Must | Contract test; golden report |
| FR-09 | Remove or explicitly flag unsupported claims; never silently keep them. | Must | Renderer test; eval gate |
| FR-10 | Preserve conflicting sources and report disagreement rather than forcing consensus. | Should | Eval on contested category |
| FR-11 | Support `as_of` dates for time-sensitive questions. | Should | Dataset + eval |
| FR-12 | Return a partial report with limitations when budget or evidence is insufficient. | Must | Budget-exhaustion test |

### 1.2 Architectures

| ID | Requirement | Priority | Verification |
|---|---|---|---|
| FR-13 | Implement a single-agent ReAct baseline behind the same interface as the multi-agent graph. | Must | Shared contract test |
| FR-14 | Implement the multi-agent graph with planner, researcher, evidence store, fact-checker, writer, and critic. | Must | Integration test |
| FR-15 | Both architectures use the same tools, model router, budget, evidence store, and output schema. | Must | Code review + contract tests |
| FR-16 | Architecture and prompt mode are selectable per run and recorded in run metadata. | Must | API test |
| FR-17 | Support hand-written prompts and DSPy-compiled modules per LLM step. | Must | Module interface tests |
| FR-18 | Fall back to hand-written prompts if a compiled artifact is missing or invalid. | Must | Loader test |

### 1.3 Evidence and citations

| ID | Requirement | Priority | Verification |
|---|---|---|---|
| FR-19 | Every source stores URL, canonical URL, fetched timestamp, content hash, HTTP status, and provenance. | Must | Schema test |
| FR-20 | Every kept claim references ≥1 source span with quote/offsets and a verifier verdict. | Must | Invariant test; eval |
| FR-21 | Verdicts are exactly `supported`, `contradicted`, or `insufficient`. | Must | Pydantic enum test |
| FR-22 | Citation markers resolve to fetched sources only; invented URLs are rejected. | Must | Renderer test |
| FR-23 | URL validity is checked against recorded content (replay) or live HTTP (live mode). | Should | Tool test |
| FR-24 | The report exposes a machine-readable claim→citation mapping. | Must | Report schema test |
| FR-25 | Low-confidence or contradicted claims are listed in an "Unverified claims" appendix when retained. | Must | Golden report test |

### 1.4 Memory and approvals

| ID | Requirement | Priority | Verification |
|---|---|---|---|
| FR-26 | Persist runs, events, sources, claims, verdicts, citations, and usage in Postgres. | Must | Migration + integration test |
| FR-27 | Persist LangGraph checkpoints so a run resumes after process restart. | Must | Restart/resume test |
| FR-28 | Long-term memory supports namespaces, TTL, provenance, and embedding retrieval. | Should | Integration test |
| FR-29 | Memory writes require approval by default. | Must | Approval policy test |
| FR-30 | Expensive searches over budget require approval (configurable). | Must | Interrupt test |
| FR-31 | Report export/publish requires approval (configurable). | Must | Interrupt test |
| FR-32 | Approvals are persisted, auditable, and resumable; rejections include a reason. | Must | API + graph tests |
| FR-33 | Expired approvals do not silently proceed. | Must | TTL test |

### 1.5 API

| ID | Requirement | Priority | Verification |
|---|---|---|---|
| FR-34 | `POST /v1/runs` starts a run and requires an `Idempotency-Key`. | Must | Contract test |
| FR-35 | SSE streams progress with reconnect via `Last-Event-ID`. | Must | Contract test |
| FR-36 | Fetch status, report, trace, and cost per run. | Must | Contract test |
| FR-37 | List/approve/reject pending approvals. | Must | Contract test |
| FR-38 | Auth is a bearer-token stub; unauthenticated requests are rejected. | Must | Contract test |
| FR-39 | OpenAPI schema is generated and documented. | Must | CI check |
| FR-40 | `/healthz` and `/readyz` report liveness and dependency readiness. | Must | Contract test |

### 1.6 LLM and quota

| ID | Requirement | Priority | Verification |
|---|---|---|---|
| FR-41 | One OpenAI-compatible client supports Groq, Gemini, OpenRouter, Cerebras, Mistral, and Ollama via config. | Must | Adapter tests |
| FR-42 | Per-provider RPM/RPD/TPM/TPD limits are loaded from config, not hardcoded. | Must | Config test + grep |
| FR-43 | Quota reservations and usage are persisted; exhausted providers are skipped. | Must | Quota tests |
| FR-44 | Runs pause when all providers are exhausted and resume after reset (or use Ollama if allowed). | Must | Integration test |
| FR-45 | Exponential backoff with jitter on 429/5xx; no retry on 4xx except 408/409. | Must | Unit test |
| FR-46 | Every LLM/search/fetch call is cached with record/replay modes. | Must | Cache round-trip test |
| FR-47 | Replay mode performs zero network calls and fails on cache miss. | Must | CI smoke eval |
| FR-48 | Token/cost accounting is recorded per node and per run. | Must | Integration test |

### 1.7 Evaluation

| ID | Requirement | Priority | Verification |
|---|---|---|---|
| FR-49 | A 50-question public dataset exists: 30 train / 10 dev / 10 frozen test, stratified by category. | Must | Dataset validation script |
| FR-50 | Frozen search/page snapshots replay deterministically. | Must | Replay test |
| FR-51 | Metrics cover accuracy, citation precision/recall, URL validity, groundedness, completion, hallucination, cost, latency, steps, tool calls. | Must | Metric unit tests |
| FR-52 | Experiments compare single-agent, multi-agent, and DSPy-optimized multi-agent. | Must | Harness config |
| FR-53 | Report 95% bootstrap CIs, paired tests, and Pareto plots. | Must | Report generation test |
| FR-54 | Judge is a different model family where possible; ordering randomized; calibration subset human-labeled. | Must | Harness audit |
| FR-55 | CI runs a 5-question replay smoke eval on every PR. | Must | GitHub Actions |
| FR-56 | Full eval runs on release, generates `EVALUATION.md`, and applies regression gates. | Should | Manual workflow |
| FR-57 | DSPy artifacts record optimizer, seed, dataset hash, metric scores, and token cost. | Must | Artifact manifest test |

---

## 2. Non-functional requirements

| ID | Requirement | Target | Verification |
|---|---|---|---|
| NFR-01 | Typed contracts at module boundaries | Pydantic v2 models; no bare `dict` across modules | mypy strict; review |
| NFR-02 | Deterministic replay | Same inputs → same outputs in replay mode | Replay test with golden output |
| NFR-03 | Test coverage | ≥80% statements/branches on `src/research_agent` (core modules ≥90%) | pytest-cov gate |
| NFR-04 | Lint/type | Ruff clean; mypy strict on core | CI |
| NFR-05 | API latency (non-LLM) | p95 <100 ms for status/report reads on laptop | Load test (Phase 7) |
| NFR-06 | Run wall-clock | ≤600 s default hard cap | Budget test |
| NFR-07 | Cost | $0 billed; shadow cost reported | Quota/cost tests |
| NFR-08 | Observability | 100% of runs have trace_id, node timings, token usage | Integration test |
| NFR-09 | Security | SSRF, prompt-injection canary, secret redaction tests pass | Security test suite |
| NFR-10 | Portability | Linux container + Windows dev host | CI matrix / manual |
| NFR-11 | Quickstart | <5 minutes on a warm machine | Timed manual check |
| NFR-12 | Documentation | Design, ADRs, API, eval, limitations current | Release checklist |
| NFR-13 | Migrations | Alembic upgrade/downgrade on empty DB | CI |
| NFR-14 | Idempotency | Duplicate POST returns same run; conflicting body returns 409 | Contract test |
| NFR-15 | Crash safety | Worker crash mid-run resumes from checkpoint | Integration test |
| NFR-16 | Data privacy | Public questions only; no secrets in cassettes/logs; PII scrub on memory | Review + test |

---

## 3. Traceability matrix

| Mission requirement | Design section | Requirements | Phase |
|---|---|---|---|
| Planning, tool calling, iterative reasoning | 5.3–5.7 | FR-02–FR-05, FR-13–FR-14 | 2–3 |
| Specialized agents | 5.4 | FR-14 | 3 |
| Source retrieval, evidence verification, citation tracking | 5.7–5.8 | FR-19–FR-25 | 1, 4 |
| Persistent memory + human approval | 5.9, 5.3 | FR-26–FR-33 | 1, 3 |
| Evaluation of accuracy, citations, completion, cost | 8 | FR-49–FR-57 | 5 |
| Single-agent baseline | 5.6 | FR-13, FR-15 | 2 |
| DSPy optimization | 5.4, ADR-0006 | FR-17–FR-18, FR-57 | 6 |
| $0 / free-tier operation | 3, 5.10 | FR-41–FR-48 | 1, 7 |
| Observability | 5.12 | NFR-08 | 2, 7 |
| Safety/guardrails | 5.13 | NFR-09 | 3, 7 |

---

## 4. Definition of done (v0.1.0)

- [ ] `docker compose up` starts app, Postgres+pgvector, and SearXNG; health checks pass.
- [ ] `make check` passes: ruff, mypy strict, unit/integration/contract tests, coverage ≥80%.
- [ ] One live research question completes end-to-end and produces a cited report.
- [ ] Replay of the same question produces an identical structured report (modulo timestamps/IDs).
- [ ] Every kept claim has a source span and verdict; renderer rejects dangling citations.
- [ ] Approval approve/reject and process-restart resume are demonstrated.
- [ ] 50-question benchmark dataset and frozen snapshots are committed.
- [ ] `EVALUATION.md` reports E0–E3 with CIs, paired tests, cost/latency, and honest failure analysis.
- [ ] README quickstart verified on a clean machine.
- [ ] Limitations and future work documented.
- [ ] MIT license, CHANGELOG, semver tag `v0.1.0`.

---

## 5. Out-of-scope requests (parking lot)

These are explicitly deferred. Do not merge them into v0.1 without an ADR.

- Web UI / dashboard
- User accounts, OAuth, RBAC
- PDF/HTML export
- Real-time news monitoring
- Multi-language reports
- Fine-tuning
- Kubernetes manifests
- Paid search or tracing
- Autonomous publishing to external sites
- OCR
- Mobile client
