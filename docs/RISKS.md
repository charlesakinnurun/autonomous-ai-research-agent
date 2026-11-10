# Risk Register

| Field | Value |
|---|---|
| Version | 0.1.0 |
| Review cadence | End of each phase |
| Scoring | Likelihood (L/M/H) × Impact (L/M/H) |

---

## 1. Top risks

| ID | Risk | L | I | Score | Mitigation | Trigger / early warning | Phase |
|---|---|---|---|---|---|---|---|
| R-01 | LangGraph or DSPy API changes break the implementation | H | H | **Critical** | Pin exact versions after a day-1 API spike; isolate behind adapters; record verified call shapes in `docs/PHASE1_API_NOTES.md`; no graph code before verification | Import errors, deprecation warnings, docs mismatch | 1 |
| R-02 | Free-tier quotas cannot support the benchmark matrix | H | H | **Critical** | Quota tracker; 10-question test matrix for 3 seeds; all-50 coverage with 1 seed; replay; batch calls; local Ollama replication; pause/resume | Daily capacity <80k tokens or >20% 429s | 0, 5 |
| R-03 | LLM-as-judge is biased or unreliable | H | H | **Critical** | Cross-family judge; randomized ordering; human-labeled calibration subset; report agreement (κ); structured verdicts with quotes; sensitivity analysis with second judge | κ <0.6 on calibration or large judge-model disagreement | 5 |
| R-04 | 10-question test split yields inconclusive results | H | H | **High** | Report CIs and effect sizes; all-50 coverage run; per-category breakdown; avoid strong claims; power analysis in EVALUATION.md | CIs overlap zero for all comparisons | 5 |
| R-05 | Prompt injection in retrieved content causes unsafe behavior | M | H | **High** | Treat content as data; spotlighting; no tool execution from content; constrained output; SSRF/allowlist; injection canary tests | Any test where page text alters tool calls | 3, 7 |
| R-06 | Citation fabrication / unsupported claims survive to the report | M | H | **High** | Source IDs only from fetched sources; renderer resolves every marker; verifier verdict required; unsupported claims removed/flagged; eval gate | Citation precision <0.9 or dangling marker | 4 |
| R-07 | Scope creep turns a 6-week project into a 6-month one | H | M | **High** | Phase exit criteria; explicit non-goals; parking lot; no UI/OCR/K8s; one architecture comparison at a time | Any phase slips >50% or new "must-have" appears | All |
| R-08 | Multi-agent is worse than single-agent and the project lacks a story | M | M | **Medium** | The benchmark is designed to detect this; report it honestly; analyze per category; the deliverable is the evaluation, not a predetermined winner | E1 accuracy < E0 with non-overlapping CI | 5 |
| R-09 | DSPy optimization overfits or leaks test data | M | H | **High** | Frozen test split; train/dev only for compile; dataset hash; no prompt edits after test run; min-delta threshold; report optimization cost | Dev-test gap >10pp | 6 |
| R-10 | DSPy optimization cost exceeds quota | M | M | **Medium** | BootstrapFewShot on verifier first; cap demos; MIPROv2 only with explicit budget; cost logged in artifact manifest; local model for dry runs | Optimization >1M tokens before dev gain | 6 |
| R-11 | Postgres checkpointer tables conflict with Alembic | M | M | **Medium** | Verify saver setup; document schema ownership; run migrations before saver setup; integration test on empty DB | Duplicate/conflicting DDL | 1, 3 |
| R-12 | SSE reconnects lose events or duplicate them | M | M | **Medium** | Durable `run_events` with monotonic ID; `Last-Event-ID`; idempotent client handling; contract test | Missing/duplicate events under reconnect | 2 |
| R-13 | Worker crash loses an in-flight run | L | H | **Medium** | LangGraph checkpoints; job lease + heartbeat; resume test; idempotent node side effects | Run stuck in `running` after restart | 3 |
| R-14 | SSRF or malicious content download | L | H | **Medium** | URL validation, DNS/IP checks, redirect re-checks, byte caps, content-type allowlist, no code execution | Any fetch to private IP or unexpected type | 1, 7 |
| R-15 | Free providers train on prompts / privacy leak | M | H | **High** | Public questions only; no secrets/PII in prompts; redaction; document in README | Any private data in cassettes/logs | All |
| R-16 | Model IDs retired mid-project | H | M | **Medium** | Model aliases in config; fallback chain; record model ID per call; replay keeps evals stable | 404/invalid model | 1, 7 |
| R-17 | pgvector retrieval quality is poor | M | M | **Medium** | Hybrid search (vector + BM25/tsvector); rerank; evaluate retrieval recall separately; chunk tuning | Retrieval recall@10 <0.7 | 4 |
| R-18 | Long reports overflow context or lose citations | M | M | **Medium** | Section-by-section writing; top-k evidence per section; token preflight; map-reduce summarization | Context errors or dropped markers | 3, 4 |
| R-19 | Docker/Windows path issues slow development | M | L | **Low** | Linux containers; `.env` paths; CI on Ubuntu; document PowerShell commands | Compose mount failures | 1 |
| R-20 | Benchmark snapshots are not truly frozen | M | H | **High** | Content-addressed cassettes; dataset hash; replay mode fails on miss; no live fallback in CI; snapshot date in metadata | Eval results change without code change | 1, 5 |
| R-21 | Cost accounting is meaningless because APIs are free | M | L | **Low** | Report tokens, calls, latency, and a clearly labeled shadow price; do not claim dollar savings | Reviewer confusion | 5 |
| R-22 | Approval gates make the demo unusable | M | M | **Medium** | Gate only high-impact actions; batch approvals; auto-approve policy for benchmarks; TTL; clear UI/API | Every run blocks on approval | 3 |
| R-23 | Test suite is slow or flaky | M | M | **Medium** | Unit tests mock HTTP; integration uses one Postgres; replay eval; no live calls in PR; deterministic seeds | CI >10 min or flaky reruns | 2 |
| R-24 | The project looks like demo-ware to reviewers | M | H | **High** | Evidence-first invariants; failure tests; benchmark honesty; design doc + ADRs; no unsourced claims | Reviewer asks "where is the eval?" | All |

---

## 2. Risk details

### R-01: Library churn (highest technical risk)

LangGraph and DSPy are fast-moving. The design deliberately avoids depending on unverified call shapes. Before Phase 1 code:

1. Create a throwaway spike branch.
2. Install pinned candidates.
3. Verify every item in `docs/PHASE1_API_NOTES.md`.
4. Write `docs/PHASE1_API_NOTES.md` with exact imports and signatures.
5. Only then implement the adapters.

If LangGraph's Pydantic state support is awkward, use `TypedDict` state with Pydantic payloads. If the Postgres saver is unstable, fall back to the SQLite saver for dev and keep Postgres for production, but document the difference. If DSPy cannot target a provider, wrap it with a custom `dspy.LM` adapter or fall back to hand-written prompts for that module.

### R-02: Quota math

The benchmark is the largest cost center. The plan in `docs/QUOTA_PLAN.md` assumes ~80k tokens per multi-agent run and a combined free-tier capacity of ~1M tokens/day. If actual capacity is lower:

- Priority 1: 90-run test matrix (10 questions × 3 architectures × 3 seeds).
- Priority 2: 50-question coverage at 1 seed.
- Priority 3: DSPy ablation.
- Priority 4: extra seeds.

The quota tracker must enforce these priorities, not hope.

### R-03: Judge hygiene

LLM judges exhibit verbosity, position, self-preference, and sycophancy biases. Mitigations:

- Judge model family differs from generator family.
- Randomize A/B order; anonymize architecture labels.
- Require a quoted span for every verdict.
- Calibrate on ≥100 human-labeled claims; report Cohen's κ and per-class agreement.
- Run a second judge on a 20% sample; report disagreement.
- Never use judge scores as ground truth without calibration.

### R-07: Scope discipline

Every phase must end with a demoable artifact and a written summary. If a phase slips, cut scope in this order:

1. Drop the optional supervisor/router.
2. Drop MIPROv2; keep BootstrapFewShot.
3. Drop the all-50 coverage run; keep the test matrix.
4. Drop PDF parsing; keep HTML.
5. Drop the web UI (already out of scope).

Do **not** cut: evidence invariants, replay, approval persistence, or the benchmark.

---

## 3. Assumptions that could invalidate the design

| Assumption | If false | Fallback |
|---|---|---|
| Free tiers remain available | No live benchmark | Local Ollama-only replication; label results as local-model |
| SearXNG returns usable JSON | Retrieval is weak | Add ddgs adapter; Wikipedia/arXiv still work |
| Gemini/Groq support JSON mode | Structured output parsing is fragile | Repair loop + constrained decoding where available |
| A 70B-class free model is good enough | Report quality is poor | Use Gemini Flash for writing; local 14B for extraction |
| 10 test questions are enough for a directional result | Inconclusive benchmark | Expand test split to 20–30 within quota; report CIs |
| Laptop has ≥16 GB RAM | fastembed/Postgres/Ollama contention | Drop Ollama profile; use API only; smaller embed model |

---

## 4. Phase gate checklist

Before moving to the next phase:

- [ ] Exit criteria in `docs/ROADMAP.md` met.
- [ ] New risks added; closed risks marked.
- [ ] Tests and CI green.
- [ ] No untyped dicts at module boundaries.
- [ ] No secrets in code, logs, or cassettes.
- [ ] Docs updated (design/ADR/README as needed).
- [ ] Cost/token impact estimated.
- [ ] User has reviewed and approved.
