# ADR-0005: Benchmark Single- vs Multi-Agent with a Frozen, Paired Design

- **Status:** Accepted
- **Date:** 2026-11-07
- **Phase:** 0 (implemented in Phase 5)
- **Deciders:** Project owner

## Context

The project's central claim is comparative: does a multi-agent, evidence-verifying architecture outperform a single ReAct agent at similar cost? A demo cannot answer this. A benchmark can, but only if it is fair, reproducible, and statistically honest.

Common failure modes in agent benchmarks:

- Different tools, budgets, or models per architecture.
- Test-set prompt tuning.
- A single seed, cherry-picked example.
- An LLM judge from the same family as the generator.
- No cost/latency accounting.
- A tiny test set with overconfident conclusions.

## Decision

Run a **paired, frozen, replayable benchmark**:

- **Variants:** E0 single-agent, E1 multi-agent hand-written, E2 multi-agent + DSPy verifier, E3 multi-agent + DSPy verifier + writer. Optional ablations A1 (no verifier) and A3 (single-agent + verifier).
- **Dataset:** 50 public questions, 30/10/10, 10 per category (factual, multi-hop, contested, time-sensitive, unanswerable).
- **Snapshots:** every search/page result frozen per question; replay mode fails on miss.
- **Fairness:** same tools, model router, token budget, evidence budget, output schema, and judge.
- **Seeds:** 3 on the 10-question test split; 1 on the 50-question coverage run if quota allows.
- **Metrics:** factual accuracy, groundedness, citation precision/recall, URL validity, hallucination rate, completion, tokens, requests, latency, steps/tool calls.
- **Statistics:** per-question averages, 10k bootstrap 95% CIs, paired bootstrap and Wilcoxon signed-rank, Holm–Bonferroni correction, effect sizes, Pareto plots.
- **Judge:** different model family where possible, randomized order, structured verdicts with quotes, human calibration subset (≥100 claims), κ reported.
- **CI:** 5-question replay smoke eval per PR; full matrix on release with regression gates.
- **Output:** `EVALUATION.md` generated from raw JSON, including failures and threats to validity.

## Consequences

**Positive**

- The comparison is defensible and reproducible.
- Costs are visible; the Pareto frontier is meaningful.
- Negative results are publishable, not hidden.
- Replay keeps CI free and deterministic.

**Negative**

- 10-question test split has low statistical power.
- Free-tier quota constrains the matrix.
- Frozen snapshots age, especially for time-sensitive questions.
- LLM judging adds cost and bias.
- Prompt tuning for each architecture can confound the result.

**Mitigations**

- Report CIs and avoid strong claims; add coverage run.
- Prioritize the 90-run test matrix.
- Version snapshots; use as-of dates.
- Cross-family judge + calibration.
- Disclose prompt variants and use ablations A1/A3 to separate architecture from verification.

## Alternatives considered

| Alternative | Why rejected |
|---|---|
| Single demo / case study | Not evidence |
| Public leaderboard only | Not comparable; no cost/latency control |
| Human evaluation at scale | Too expensive for $0 |
| One seed | Hides variance |
| Same-family judge only | Self-preference bias |
| 200-question benchmark | Exceeds free-tier token budget; 50 is the honest compromise |

## Verification

- Dataset validator + frozen test hash.
- Replay CI with zero network.
- Fairness contract test (same tools/budget/schema).
- Judge calibration report with κ.
- Reproduce `EVALUATION.md` from raw JSON.

## References

- `docs/EVAL_PLAN.md`
- `docs/QUOTA_PLAN.md` §3
- `docs/RISKS.md` R-02, R-03, R-04, R-09
