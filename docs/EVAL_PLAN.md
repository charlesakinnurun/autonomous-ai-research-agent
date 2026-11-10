# Evaluation Plan

| Field | Value |
|---|---|
| Version | 0.1.0 |
| Status | Draft |
| Benchmark | 50 public questions: 30 train / 10 dev / 10 frozen test |
| Seeds | 3 on the test matrix; 1 on the 50-question coverage run |
| Judge | Different model family where possible; human-calibrated subset |
| CI | 5-question replay smoke eval per PR; full matrix on release |

The goal is not to prove multi-agent wins. The goal is to measure **when it wins, when it loses, and what it costs** — with enough rigor that a skeptical reviewer believes the numbers.

---

## 1. Research questions

| ID | Question | Primary metrics |
|---|---|---|
| RQ1 | Does decomposition + verification improve factual accuracy over a single ReAct agent? | Factual accuracy, groundedness, hallucination rate |
| RQ2 | Does multi-agent improve citation precision/recall? | Citation precision/recall, URL validity |
| RQ3 | What is the cost/latency penalty? | Tokens, requests, wall-clock, Pareto |
| RQ4 | Does DSPy optimization improve the verifier and writer? | Verdict accuracy, citation metrics, groundedness |
| RQ5 | Where does each architecture fail? | Per-category breakdown, failure taxonomy |

---

## 2. Dataset

### 2.1 Composition

| Category | Count | Split (train/dev/test) | What "good" looks like |
|---|---:|---|---|
| Factual lookup | 10 | 6/2/2 | Correct answer with a reliable source |
| Multi-hop | 10 | 6/2/2 | Correct synthesis across ≥2 sources |
| Contested | 10 | 6/2/2 | Multiple positions, sources preserved, no false consensus |
| Time-sensitive | 10 | 6/2/2 | Correct as-of the question's date; recency handled |
| Unanswerable | 10 | 6/2/2 | Refuses or states insufficient evidence; no fabrication |

**Total:** 50. Splits are stratified by category, so each split has 2 questions per category.

### 2.2 Item schema

```json
{
  "id": "q-mh-003",
  "version": "v1",
  "split": "test",
  "category": "multi_hop",
  "question": "Which institution employed the researcher who first demonstrated X, and what year did that institution adopt Y?",
  "as_of": "2025-06-01",
  "answerability": "answerable",
  "gold_answer": "Short gold answer or position set",
  "gold_claims": [
    {
      "id": "c1",
      "text": "Researcher R demonstrated X in year Y.",
      "importance": "required",
      "gold_evidence": [
        {"url": "https://...", "quote": "verbatim supporting span", "snapshot_id": "..."}
      ]
    }
  ],
  "gold_positions": [],
  "notes": "Why this question is in the set; known ambiguity",
  "source_license": "public domain / CC-BY / etc.",
  "dataset_hash": "sha256:..."
}
```

For contested items, `gold_answer` is null and `gold_positions` is a list of `{position, sources[]}`. For unanswerable items, `answerability = "unanswerable"` and `gold_claims` is empty; the correct behavior is a refusal with a reason.

### 2.3 Sourcing rules

- Public questions only; no private or user data.
- Prefer questions with verifiable public evidence.
- Do not use questions whose gold answer depends on a single paywalled source.
- Record the source license and retrieval date.
- For time-sensitive questions, freeze `as_of`; do not update the snapshot later.
- Deduplicate near-duplicates across splits; no train/test leakage.
- The test split is frozen at dataset `v1`; changes require `v2` and a changelog entry.

### 2.4 Frozen snapshots

Every question has a cassette bundle:

```text
evals/cassettes/v1/<question_id>/
  search/<query_hash>.json       # normalized results, timestamp, engine
  pages/<url_hash>.json          # status, headers, content hash, extracted text
  pdf/<url_hash>.json            # pages + extracted text
  manifest.json                  # hashes, retrieval timestamps, tool versions
```

- Replay mode reads only these files; a miss is a hard failure.
- Live mode records new cassettes into a staging directory; a human reviews and promotes them.
- Snapshots include the as-of date; results are never silently refreshed.
- Store extracted text, not raw HTML, unless needed for parser tests.

### 2.5 Dataset validation

A `scripts/validate_dataset.py` check (Phase 5) enforces:

- 50 items; 30/10/10 split; 10 per category.
- Unique IDs; unique normalized questions.
- Every answerable item has ≥1 gold claim and ≥1 gold evidence quote.
- Every contested item has ≥2 positions.
- Every unanswerable item has a refusal rationale.
- Every cassette referenced by an item exists and hashes match.
- No item is in more than one split.
- Test split hash is unchanged from the frozen manifest.

---

## 3. Metrics

Let:

- `C` = claims kept in the final report.
- `C_cited` = claims with ≥1 citation.
- `C_supported` = claims with a `supported` verdict.
- `C_contradicted` = claims with a `contradicted` verdict.
- `G` = gold claims.
- `U` = cited URLs.

### 3.1 Primary metrics

| Metric | Formula | Notes |
|---|---|---|
| **Factual accuracy** | `supported_and_correct / |C|` (importance-weighted option) | "Correct" vs gold; judged, not just self-verdict |
| **Groundedness** | `|C_supported| / |C|` | Support by the cited span; verifier + judge audit |
| **Citation precision** | `|claims whose cited span supports them| / |C_cited|` | Penalizes citations that don't support the claim |
| **Citation recall** | `|gold claims covered by a supported, cited claim| / |G|` | Penalizes missing key claims |
| **URL validity** | `|valid cited URLs| / |U|` | Replay: content hash matches; live: 2xx/3xx |
| **Hallucination rate** | `|C_unsupported ∪ C_contradicted| / |C|` | Claims kept without support |
| **Completion rate** | `valid_reports / runs` | Valid = schema-valid, citations resolve, status terminal |
| **Cost** | tokens in/out, requests, shadow cost | Free tier = $0 billed; shadow price labeled |
| **Latency** | wall-clock p50/p95 | Includes retrieval, excludes queue wait; p95 with ~30 samples is indicative, so report p50/mean too |
| **Efficiency** | steps, tool calls, sources fetched, tokens per supported claim | Detects verbose agents |

### 3.2 Secondary metrics

| Metric | Purpose |
|---|---|
| Answer accuracy (answerable) | Judge compares final answer to gold; useful for factual lookup |
| Refusal correctness (unanswerable) | Refuses or states insufficiency without fabricating |
| Contradiction detection rate | Fraction of planted/known contradictions flagged |
| Source diversity | Distinct domains cited; guards against one-source reports |
| Retrieval recall@k | Did the evidence store retrieve the gold evidence? |
| Verifier macro-F1 | Per-class performance on supported/contradicted/insufficient |
| Verifier calibration (ECE) | Confidence vs correctness |
| Judge agreement (κ) | Human vs judge on calibration set |
| Budget adherence | Runs that finish under caps; no silent overruns |
| Crash/resume rate | Runs that survive a worker restart |

### 3.3 Metric hygiene

- Compute metrics from structured report JSON, not from Markdown parsing alone.
- Claim matching to gold uses normalized text + judge; report both exact and semantic.
- Importance weighting: `required` claims count 2×, `supporting` 1×; report unweighted as well.
- Do not average per-claim metrics across runs without weighting by claim count; report both.
- A claim with multiple citations counts once for precision; all cited spans must support it.
- For contested questions, score position coverage and source balance, not a single "correct" answer.
- For unanswerable questions, a confident fabricated answer is a failure even if it sounds plausible.

---

## 4. Judge design

### 4.1 Judge protocol

For each sampled claim, the judge receives:

1. The claim text.
2. The cited quote(s) and source URL/title.
3. The question (for context).
4. A strict rubric and JSON schema.

It returns:

```json
{
  "verdict": "supported | contradicted | insufficient",
  "supports_claim": true,
  "quote": "verbatim span from the provided evidence",
  "rationale": "one or two sentences",
  "confidence": 0.0
}
```

Rules:

- The judge must quote the evidence; a verdict without a quote is invalid and retried once.
- The judge does not see the architecture, model, or full report.
- For pairwise comparisons, randomize A/B order and anonymize labels.
- Temperature 0 for judging; seed recorded.
- Max 10 claims per report, stratified by section and verdict, to control cost.
- The judge model family differs from the generator family where possible (e.g., Gemini judges Groq/Llama outputs; Groq/Llama judges Gemini outputs).
- If only one family is available, use a local Qwen judge for a 20% audit and report the limitation.

### 4.2 Calibration

- Human-label ≥100 claims stratified across categories and verdict classes.
- Calibration claims come from **train/dev runs, never the frozen test set**, so judge tuning cannot leak test labels.
- Compute judge accuracy, Cohen's κ, per-class F1, and calibration error.
- If κ <0.6: revise the rubric, add few-shot examples, and re-calibrate; if still low, human-adjudicate the test set and report judge results as secondary.
- Re-calibrate when the judge model, prompt, or rubric changes.
- Store the calibration set and labels in `evals/judge_calibration/`.

### 4.3 Known judge biases and mitigations

| Bias | Symptom | Mitigation |
|---|---|---|
| Verbosity | Longer answers score higher | Judge claims individually; length penalty in secondary analysis |
| Position | First option favored | Randomize order; swap and average |
| Self-preference | Same-family model favors its outputs | Cross-family judge; audit sample |
| Sycophancy | Agrees with confident wording | Blind architecture; require evidence quote |
| Citation-length | Longer quotes seem more supportive | Cap quote length; ask for minimal sufficient span |
| Category bias | Better on factual than contested | Per-category calibration and reporting |
| Temporal bias | Prefers recent sources | As-of date in rubric; source date shown |

Document these in `EVALUATION.md`, not just here.

---

## 5. Experimental design

### 5.1 Variants

| ID | Architecture | Prompt mode | Purpose |
|---|---|---|---|
| E0 | Single-agent ReAct | Hand-written | Baseline |
| E1 | Multi-agent | Hand-written | Decomposition + verification |
| E2 | Multi-agent | DSPy verifier | Verification quality (ablation) |
| E3 | Multi-agent | DSPy verifier + writer | End-to-end optimization |

**Main matrix:** E0, E1, E3 (3 variants × 10 test questions × 3 seeds = 90 runs). E2 is an ablation, not part of the 90-run matrix; run it only if quota remains. A1/A3 are exploratory and run on dev if the budget is tight.

Optional ablations:

| ID | Variant | Purpose |
|---|---|---|
| A1 | Multi-agent without verifier | Is verification doing the work? |
| A2 | Multi-agent without critic loops | Is iteration worth it? |
| A3 | Single-agent + verifier | Is the gain from architecture or verification? |
| A4 | DSPy writer only | Isolate writer gains |
| A5 | Single-agent, compute-matched to E1 | Separate architecture from extra steps/tokens |

A1/A3 are the most important: they separate "more agents" from "more verification."

### 5.2 Splits and seeds

| Split | Questions | Seeds | Use |
|---|---:|---:|---|
| Train | 30 | 1 | DSPy compilation |
| Dev | 10 | 1–2 | Prompt/optimizer selection |
| Test | 10 | 3 | Main comparison; touched once |
| Coverage | 50 | 1 | Optional appendix; not for tuning |

- Test split is frozen. No prompt changes after the first test run without a new version and disclosure.
- Seeds control sampling temperature and any randomized ordering. Record seed per run.
- Report seed variance separately; if it exceeds the architecture effect, say so.
- A literal 50 × 3 architectures × 3 seeds matrix would be ~53M tokens and 7–8 weeks; see `docs/QUOTA_PLAN.md` §3.3. The reduced design (3 seeds on test, 1 on coverage) must be disclosed in `EVALUATION.md`.

### 5.3 Fairness controls

- Same model router policy and max tokens per run.
- Same tools, retrieval cache, evidence budget, and output schema.
- Same judge and metric code.
- Same maximum sources/claims.
- Prompt variants are part of the treatment and disclosed.
- No architecture gets extra retries or a larger budget.
- Single-agent gets the same `write_report` tool and citation schema.

### 5.4 Statistics

- Unit of analysis: question. Average metrics across seeds per question.
- Bootstrap 10,000 resamples over questions; 95% percentile CI.
- Paired bootstrap for architecture differences (same questions).
- Wilcoxon signed-rank as a non-parametric robustness check.
- Holm–Bonferroni correction across the main comparisons.
- Report effect sizes (risk difference, Cohen's d) with CIs.
- Pareto frontier: quality (factual accuracy / groundedness) vs tokens and latency.
- With n=10 test questions, CIs will be wide. State the minimum detectable effect qualitatively and avoid "statistically significant" claims unless the paired test supports them.

### 5.5 Failure taxonomy

Every failed or degraded run is labeled:

| Code | Meaning |
|---|---|
| `search_empty` | No useful results after rewrites |
| `fetch_blocked` | Paywall/403/robots |
| `parse_failed` | HTML/PDF parse failure |
| `evidence_insufficient` | Not enough evidence for a sub-question |
| `claim_unsupported` | Verifier rejected a key claim |
| `contradiction` | Sources conflict |
| `budget_exhausted` | Token/step/time cap hit |
| `quota_paused` | Provider exhausted; run deferred |
| `invalid_output` | Schema/JSON repair failed |
| `citation_invalid` | Dangling marker or URL mismatch |
| `approval_rejected` | Human rejected an action |
| `tool_error` | Timeout/5xx after retries |

Report the distribution per architecture and category.

---

## 6. CI and release gates

### 6.1 PR smoke eval

- 5 questions from the dev split, replay mode.
- Zero network calls; cache miss is a failure.
- Assertions:
  - Run completes within budget.
  - Report schema valid.
  - 100% of citations resolve; no dangling markers.
  - Cost ledger equals recorded usage.
  - No unsupported claim in the main body.
- Runtime target: <3 minutes.

### 6.2 Release eval

- Full test matrix (10 × 3 architectures × 3 seeds) + judge.
- Manual workflow with provider secrets; not on every PR.
- Generates `EVALUATION.md`, CSVs, and plots as artifacts.
- Regression gates (initial thresholds; tune after baseline):

| Metric | Gate |
|---|---|
| Completion | ≥0.90 |
| Citation precision | ≥0.90 |
| URL validity | ≥0.98 (replay) |
| Dangling citations | 0 |
| Factual accuracy | ≥ baseline − 2pp |
| Groundedness | ≥ baseline − 2pp |
| Cost | ≤ baseline +20% |
| Latency p95 | ≤ baseline +20% |

- A gate failure blocks the release or requires a written exception in `EVALUATION.md`.

### 6.3 Determinism checks

- Replay the same 5 questions twice; structured output must be identical except timestamps/IDs.
- Run with two seeds in replay; outputs should differ only where sampling is recorded.
- Verify the dataset manifest hash and cassette hashes.

---

## 7. Generated `EVALUATION.md`

The report is generated from raw JSON, not hand-written. Sections:

1. **Setup** — git SHA, lock hash, dataset hash, model IDs, provider config, dates.
2. **Dataset** — composition, splits, known gaps.
3. **Main results** — table with mean ± 95% CI for every metric and variant.
4. **Per-category** — where each architecture wins/loses.
5. **Ablations** — verifier on/off, critic on/off, DSPy per module.
6. **Cost/latency** — tokens, requests, p50/p95, Pareto plots.
7. **Judge calibration** — κ, accuracy, per-class agreement, biases.
8. **Failure analysis** — taxonomy distribution and representative examples.
9. **DSPy optimization cost** — tokens, calls, artifacts, train/dev/test scores.
10. **Threats to validity** — small n, frozen snapshot, judge bias, model drift.
11. **Limitations and future work** — honest, specific.

Plots (matplotlib, committed as PNG or SVG):

- Quality vs tokens (Pareto).
- Quality vs latency (Pareto).
- Per-category accuracy heatmap.
- Citation precision/recall scatter.
- Seed variance box plot.

---

## 8. Threats to validity

| Threat | Impact | Mitigation |
|---|---|---|
| n=10 test questions | Wide CIs; low power | Report CIs; coverage run; no overclaiming |
| Frozen snapshots age | Time-sensitive questions become stale | As-of date; versioned snapshots; periodic v2 |
| Free model drift | Results not reproducible live | Replay cassettes; record model IDs; pin when possible |
| Judge bias | Metric error | Cross-family judge; human calibration; audit sample |
| Prompt tuning leakage | Inflated test scores | Frozen test; dev-only tuning; disclosure |
| Retrieval snapshot bias | Favors questions with good snapshots | Validate gold evidence; report retrieval recall |
| Contested topics lack ground truth | "Accuracy" is ill-defined | Score position coverage and source balance |
| Shadow cost is fictional | Misleading dollar claims | Label clearly; lead with tokens/requests |
| Single annotator | Label noise | Second-pass adjudication; report agreement |
| Architecture confound | Multi-agent gets more calls | Equal budget; A1/A3 ablations |
| Local vs API model mismatch | Different quality | Keep model fixed within a comparison; report fallback |

---

## 9. Open eval questions

1. How many claims per report should be judged? Proposal: up to 10, stratified, plus programmatic checks on all.
2. Should gold claims be exhaustive? No; mark `required` vs `supporting` and score recall on `required`.
3. How to handle a correct answer with a weaker citation? Citation precision and factual accuracy are separate; report both.
4. Is a refusal on an answerable question a completion failure? Yes, but distinguish "insufficient evidence" from "wrong answer."
5. How to score contested topics? Position coverage + source balance + no false consensus; no single accuracy number.
6. Do we include the optional A1/A3 ablations in the main matrix? Yes if budget allows; otherwise run on the dev split and label as exploratory.
