# Quota Plan — Operating a Research Benchmark on Free Tiers

| Field | Value |
|---|---|
| Version | 0.1.0 |
| Budget | **$0 billed** |
| Principle | Treat **tokens per day** and **requests per day** as the real budget |
| Status | Planning estimates; replace with measured numbers after Phase 2 |

> **Do not trust the limits in this document.** Free-tier limits change without notice and vary by model, region, and account. Every number in §2 is a *planning assumption* to be verified in each provider console and written into `config/providers.yaml`. The code must never hardcode them.

---

## 1. Token budget per run

These are **design targets** for the first implementation, not measurements. We will replace them with observed usage from `run_events` after Phase 2.

### 1.1 Assumptions

- Evidence budget: 10–12 fetched sources, 3–5 chunks per sub-question, 6 sub-questions max.
- Output caps: 600 tokens per section, 1,500 tokens for the final report, 200 tokens per verdict.
- Batching: evidence extraction and verification are batched (3–5 items per call) to reduce request count.
- Retry overhead: 15%.
- Prompt demos (DSPy): +15% input tokens.

### 1.2 Per-run estimates

| Node | Calls | Input tokens | Output tokens | Notes |
|---|---:|---:|---:|---|
| Planner | 1 | 1,200 | 600 | Includes constraints + memory |
| Query generation | 1 | 1,800 | 800 | Batched for all sub-questions |
| Evidence extraction | 3 | 15,000 | 3,000 | 5 pages per call, truncated |
| Coverage critic | 2 | 4,000 | 800 | Loop 1 + loop 2 |
| Writer | 4 | 14,000 | 2,000 | Section-by-section |
| Claim extraction | 1 | 3,000 | 800 | Structured output |
| Verifier | 4 | 18,000 | 2,400 | 5 claims per call |
| Report critic | 2 | 4,000 | 800 | Stop/revise |
| **Subtotal** | **18** | **61,000** | **11,200** | |
| Retry overhead (15%) | | 9,150 | 1,680 | 429/5xx, repairs |
| **Multi-agent total** | **~22** | **70,150** | **12,880** | **~83k tokens** |

| Architecture | Calls/run | Tokens/run (target) | Notes |
|---|---:|---:|---|
| Single-agent ReAct | 18–25 | **45k** | Longer context, fewer structured passes |
| Multi-agent, hand-written | 20–30 | **80k** | Table above |
| Multi-agent, DSPy | 25–35 | **92k** | +15% demos |
| Judge (per report) | 2–4 | **8–12k** | 10 claims + cited spans, sampled |
| Embeddings | 0 API | 0 | Local fastembed |

**Planning number:** 72k tokens per run averaged across the three architectures; **80k for the multi-agent** in quota calculations.

---

## 2. Provider capacity (verify these)

Fill this table from each provider console on the day you start. Record the verification date and model ID. The example values are conservative placeholders.

| Provider | Model role | RPM | RPD | TPM | TPD | Verified? |
|---|---|---:|---:|---:|---:|---|
| Groq | fast extraction / verifier | 20 | 500 | 6,000 | 400,000 | ☐ |
| Gemini | writer / planner / judge | 10 | 250 | 250,000 | 1,000,000 | ☐ |
| OpenRouter `:free` | overflow | 10 | 50 | 20,000 | 200,000 | ☐ |
| Cerebras | overflow | 10 | 100 | 60,000 | 500,000 | ☐ |
| Mistral free | overflow | 10 | 100 | 20,000 | 200,000 | ☐ |
| Ollama (local) | dev / CI / fallback | ∞ | ∞ | ∞ | ∞ | n/a |

**Combined planning capacity:**

| Scenario | Effective tokens/day | Runs/day at 72k | Feasible? |
|---|---:|---:|---|
| Conservative (Groq only) | 400k | 5.5 | Tight |
| Base (Groq + Gemini) | 1.4M | 19 | Good |
| Realistic with RPD caps | 0.8–1.0M | 11–14 | Workable |
| Optimistic (all providers) | 2.3M | 32 | Comfortable |

**RPD is often the binding constraint, not TPD.** At ~22 calls/run, a combined 750 RPD supports ~34 runs/day in request count, but token caps bring it closer to 14–19. The quota tracker must enforce both.

---

## 3. Workload budget

### 3.1 Phased workload

| Phase | Work | Runs | Tokens/run | Gross tokens | Effective API tokens | Notes |
|---|---|---:|---:|---:|---:|---|
| 1 | Tool/dev smoke | 30 | 20k | 0.6M | 0.2M | 2/3 Ollama/replay |
| 2 | Single-agent bring-up | 30 | 45k | 1.35M | 0.7M | 50% replay |
| 3 | Multi-agent bring-up | 30 | 80k | 2.4M | 1.2M | 50% replay |
| 4 | Evidence/verification tuning | 20 | 80k | 1.6M | 0.8M | Half replay |
| 5 | Dataset + judge calibration | 20 | 80k | 1.6M | 1.0M | +0.2M judge |
| 6 | DSPy BootstrapFewShot (verifier) | — | — | 0.6M | 0.6M | 30 train examples, capped |
| 6 | DSPy MIPROv2 (optional) | — | — | 3.0M | 3.0M | Separate approval only |
| 6 | Main matrix: 10 test × 3 arch × 3 seeds | 90 | 72k | 6.5M | 6.5M | Priority 1 |
| 6 | Coverage: 50 × 3 arch × 1 seed | 150 | 72k | 10.8M | 10.8M | Priority 2 |
| 5–6 | Judge: main matrix | 90 | 10k | 0.9M | 0.9M | 10 claims/report |
| 5–6 | Judge: coverage | 150 | 10k | 1.5M | 1.5M | Priority 2 |
| 5 | Human calibration + second judge sample | — | — | 0.4M | 0.4M | 20% sample |
| — | Reruns/repairs (25%) | — | — | 6.4M | 6.4M | Worst case |

**Development envelope check:** phases 1–5 effective usage is ~4.1M. Round up to 4.5M.

### 3.2 Recommended budget envelopes

| Envelope | Cap | Contents |
|---|---:|---|
| Development | **4.5M** | Phases 1–5, Ollama-first, replay, 50% of bring-up |
| DSPy | **1.0M** | BootstrapFewShot verifier only; MIPRO needs a separate approval |
| Main matrix | **8.0M** | 90 runs + judge |
| Coverage (optional) | **13.0M** | 50-question single-seed + judge |
| Contingency | **5.0M** | Reruns, provider churn, repairs |
| **Total (recommended)** | **31.5M** | ~32 days at 1M/day; fits 6 weeks with pause/resume |

The optional MIPROv2 run (3.0M) is **outside** this envelope and requires a separate approval. If approved, the total becomes 34.5M.

### 3.3 Deviation from the brief (needs explicit approval)

The brief says "50 questions (30/10/10), 3 seeds". A literal full matrix is:

```text
50 questions × 3 architectures × 3 seeds = 450 generation runs
450 × 72k = 32.4M generation tokens
+ 4.5M judge tokens
+ 4.5M development
+ 1.0M DSPy
+ ~25% reruns
≈ 53M tokens
```

At ~1M tokens/day, that is **7–8 weeks**, not 6, and it assumes the optimistic capacity scenario. The proposed compromise in this plan is:

- **3 seeds on the 10-question test split** (90 runs) for the main comparison.
- **1 seed on all 50 questions** (150 runs) for coverage.
- E2 and A1/A3 ablations only if quota remains.

This preserves the paired, multi-seed test comparison and the 50-question coverage while fitting the budget. If 3 seeds across all 50 is non-negotiable, the options are: extend to 8 weeks, add more providers, or cut evidence/verification depth. Do not silently claim the full matrix was run.

If the measured capacity is below 800k tokens/day, **cut in this order**:

1. Drop the optional MIPROv2 run.
2. Drop the all-50 coverage run; keep the 90-run test matrix.
3. Reduce development runs by using Ollama and replay.
4. Reduce seeds on the single-agent baseline (keep 3 seeds for the two multi-agent variants).
5. Extend the collection window rather than lowering evidence quality.

Never cut: replay, citation verification, judge calibration, or the test split.

---

## 4. Collection schedule (6 weeks, part-time)

| Week | Focus | Daily cap (avg) | Collection strategy |
|---|---|---:|---|
| 1 | Phase 1: models, schema, tools, cache | 0.7M | Ollama + mocked HTTP; live calls only for provider smoke tests |
| 2 | Phase 2–3: single/multi bring-up | 1.0M | 1 seed; replay half the runs; stop at 80% daily cap |
| 3 | Phase 4–5: evidence, citations, dataset | 1.0M | Freeze snapshots; judge calibration; no benchmark yet |
| 4 | Phase 5–6: DSPy BFS + dev tuning | 1.0M | Optimize on train; evaluate on dev; log cost |
| 5 | Phase 6: main matrix | 1.2M | 90 runs, 3 seeds, quota-aware; 8–12 runs/day |
| 6 | Phase 6–8: coverage (if budget), docs, release | 1.0M | Coverage run + final judge + buffer |

**Daily operating rule:** pause benchmark collection at 80% of any provider's daily cap, leaving 20% for interactive debugging and retries. The weekly numbers are caps, not targets; unused quota rolls into contingency.

---

## 5. Quota tracker design

### 5.1 State

```text
quota_usage(provider, model, day_utc) -> requests, tokens_in, tokens_out, reserved
quota_reservations(id, provider, model, tokens, expires_at, run_id)
provider_health(provider, cooldown_until, last_error, updated_at)
```

### 5.2 Call lifecycle

1. **Estimate** tokens for the request (prompt tokens + `max_tokens`).
2. **Reserve** in a single transaction:
   ```sql
   INSERT INTO quota_usage (...) VALUES (...)
   ON CONFLICT (provider, model, day_utc) DO UPDATE
     SET reserved = quota_usage.reserved + EXCLUDED.reserved;
   ```
   Reject if `requests + 1 > rpd`, `tokens_in + prompt > tpd`, `tokens_out + max_tokens > tpd`, or the RPM/TPM bucket is empty.
3. **Call** the provider with a timeout.
4. **Commit** actual usage; release the unused reservation.
5. **On 429/5xx:** record cooldown (honor `Retry-After`), fall back to the next provider.
6. **On exhaustion:** set the run to `paused_quota`, schedule `run_jobs.available_at` at the next UTC reset, release the worker.

Reservations expire after 10 minutes so a crashed worker cannot leak quota.

### 5.3 Rate limiting

| Limit | Algorithm | Scope |
|---|---|---|
| RPM | Token bucket, refill 1/min | provider |
| TPM | Sliding 60 s window | provider |
| RPD | Fixed UTC day counter | provider + model |
| TPD | Fixed UTC day counter | provider + model |
| Per-run | Budget ledger | run |

Use a Postgres advisory lock or `SELECT ... FOR UPDATE` for atomic counters. At laptop scale, a single worker avoids most contention, but correctness must not depend on that.

### 5.4 Reset and resume

- Reset at `quota.reset_utc` (default `00:00`).
- A scheduled job (or worker tick) promotes `paused_quota` runs whose `available_at <= now()`.
- Resume is idempotent: the graph continues from its checkpoint; no node reruns completed work.
- Log a `quota_resumed` event.

### 5.5 Observability

Metrics/logs:

- `quota_used_ratio{provider,model,window}` — warn at 0.8, page at 0.95 (log only; no pager).
- `quota_rejections_total{provider,reason}`
- `llm_fallback_total{from,to,reason}`
- `run_paused_quota_total`
- `tokens_per_run{architecture}` — detect budget drift.

---

## 6. Cost accounting when the bill is $0

Free-tier cost is **$0 billed**, but "cost" is still meaningful:

| Measure | Use |
|---|---|
| Tokens in/out per run | Primary efficiency metric; comparable across providers |
| Requests per run | Captures RPD pressure |
| Wall-clock latency | User experience and benchmark metric |
| Shadow cost | Tokens × a configured reference price, clearly labeled "not billed" |
| Local compute proxy | Embedding CPU seconds + Postgres storage; report separately |

Do **not** claim dollar savings or cost-per-run in dollars as if the APIs were paid. Report tokens and calls first; include shadow cost only for cross-architecture comparability.

---

## 7. Privacy and data handling

- Free tiers may train on prompts. **Public questions only.**
- No API keys, emails, phone numbers, or private URLs in prompts, logs, or cassettes.
- Redact secrets from error payloads before persisting.
- Cassettes are reviewed before commit; `scripts/scan_cassettes.py` (Phase 1) checks for key patterns.
- Memory writes are approval-gated and PII-scrubbed.
- Delete raw fetched content after the run unless it is part of a committed benchmark snapshot.

---

## 8. Contingency playbook

| Situation | Action |
|---|---|
| Provider returns 429 for >5 min | Cooldown, fallback, log; do not retry aggressively |
| All providers exhausted before noon | Pause benchmark; switch dev to Ollama/replay; resume next UTC day |
| Model retired / 404 | Update alias in config, re-run provider smoke test, replay evals unaffected |
| Judge cost exceeds plan | Sample 5 claims/report; judge only the test matrix |
| DSPy optimization exceeds 1M tokens | Stop, keep hand-written prompts, report the negative result |
| Benchmark results inconclusive | Report CIs and per-category breakdown; do not overclaim; extend collection if time allows |
| Laptop RAM pressure | Disable Ollama profile; use smaller embed model; reduce concurrent runs to 1 |

---

## 9. Pre-flight checklist (before any collection run)

- [ ] Provider limits verified and written to `config/providers.yaml`.
- [ ] `LLM_MODE=live` for collection; `replay` for CI.
- [ ] Quota tracker migration applied; current usage visible.
- [ ] Budget caps set for the run (`max_total_tokens`, `max_steps`, `max_wall_clock_s`).
- [ ] Dataset split and seeds recorded.
- [ ] Cassette directory writable and outside git until reviewed.
- [ ] No private data in prompts.
- [ ] Stop condition: 80% of any daily provider cap.
- [ ] Resume plan: `paused_quota` runs scheduled after UTC reset.
