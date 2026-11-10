# Evaluation Harness

Phase 5 builds the harness. This directory is scaffolded now so dataset and cassette conventions are fixed before code.

## Layout

```text
evals/
  datasets/
    v1/
      questions.jsonl        # 50 questions: 30 train / 10 dev / 10 test
      manifest.json          # dataset hash, split hashes, counts, created_at
      README.md              # sourcing notes, licenses, known ambiguity
  cassettes/
    v1/
      <question_id>/
        search/*.json
        pages/*.json
        pdf/*.json
        manifest.json
  configs/
    smoke.yaml               # 5 questions, replay, PR gate
    release.yaml             # full matrix, live, manual
  judge_calibration/
    labels.jsonl             # >=100 human-labeled claims
    rubric.md
  results/
    <run_id>/
      results.jsonl
      summary.json
  run_benchmark.py           # Phase 5
  generate_report.py         # Phase 5
```

## Rules

- **Frozen test split.** No prompt, threshold, or retrieval tuning on test.
- **Replay-only CI.** A cache miss is a failure; no live calls in PRs.
- **Content-addressed snapshots.** Every recorded request/response includes a hash and tool version.
- **Public data only.** No private questions, no secrets, no PII in cassettes.
- **Versioned datasets.** Changing a test question requires `v2` and a changelog entry.
- **Raw results are immutable.** `EVALUATION.md` is generated from `results/`, not hand-edited.

## Commands (Phase 5)

```bash
# PR smoke (replay, 5 questions)
make eval-smoke

# Full test matrix (manual; live quotas)
uv run python -m evals.run_benchmark --config evals/configs/release.yaml

# Regenerate EVALUATION.md and plots
uv run python -m evals.generate_report
```

Until Phase 5, CI runs `pytest -m smoke` only; see `.github/workflows/ci.yml`.
