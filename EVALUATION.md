# Evaluation

> **Status: not yet run (Phase 0).** No benchmark numbers are reported yet. Adding results before Phase 5 would be fabricated; this file is a placeholder with the reporting contract.

The evaluation design is in [`docs/EVAL_PLAN.md`](docs/EVAL_PLAN.md). The harness lands in Phase 5.

## What will be reported

| Section | Content |
|---|---|
| Setup | Git SHA, lock hash, dataset hash, model IDs, provider config, run date |
| Dataset | 50 public questions, 30/10/10, 10 per category, frozen snapshots |
| Main results | Mean ± 95% bootstrap CI for each metric and variant |
| Per-category | Factual, multi-hop, contested, time-sensitive, unanswerable |
| Ablations | Verifier on/off, critic on/off, DSPy per module |
| Cost/latency | Tokens, requests, p50/p95, Pareto plots |
| Judge calibration | Cohen's κ, accuracy, per-class agreement, known biases |
| Failure analysis | Taxonomy distribution and representative examples |
| DSPy cost | Optimizer tokens/calls, artifacts, train/dev/test scores |
| Threats to validity | Small n, frozen snapshots, judge bias, model drift |
| Limitations | Specific, not generic |

## Variants

| ID | Architecture | Prompts |
|---|---|---|
| E0 | Single-agent ReAct | Hand-written |
| E1 | Multi-agent | Hand-written |
| E2 | Multi-agent | DSPy verifier |
| E3 | Multi-agent | DSPy verifier + writer |

Optional ablations: A1 (multi-agent without verifier), A3 (single-agent + verifier).

## How to reproduce (Phase 5+)

```bash
# Replay-only smoke (CI)
uv run pytest -m eval
# or
make eval-smoke

# Full matrix (manual; consumes free-tier quota)
uv run python -m evals.run_benchmark --config evals/configs/release.yaml
uv run python -m evals.generate_report
```

## Honesty rules

- The test split is frozen; no tuning on it.
- Report CIs and sample size. With 10 test questions, effects are directional.
- The judge is a different model family where possible and is calibrated on human labels.
- Free-tier billed cost is $0; tokens/requests are the primary cost metrics.
- Negative results are reported, not hidden.
- `EVALUATION.md` is generated from raw JSON, never hand-edited.

Until Phase 5, the only CI evaluation is `pytest -m smoke`, which checks installability and config presence — not research quality.
