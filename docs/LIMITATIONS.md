# Limitations and Future Work

This file is deliberately blunt. A portfolio project that hides its limits is not production-grade.

## 1. Current-phase limitations (Phase 1)

- **No research graph or report generation yet.** Contracts, schema, tools, and cache exist; Phase 2 adds the single-agent loop and run API.
- The API currently exposes only `/healthz` and `/version`; run endpoints are Phase 2.
- Docker services are configured but not verified on the authoring host; Docker must be running.
- `alembic upgrade head` is verified as offline SQL; apply/downgrade is skipped locally because pgvector is not installed. CI uses `pgvector/pgvector:pg16`.
- SearXNG is configured and mocked in tests; live SearXNG was not started here.
- Provider limits in `config/providers.example.yaml` are placeholders. Verify them.
- Live Groq/Gemini/Ollama calls were not made (no keys). Use `scripts/provider_smoke.py --live`.
- The `EVALUATION.md` file has no results yet; the harness is Phase 5.

## 2. Architectural limitations (v0.1 target)

| Limitation | Why it exists | Impact | Future work |
|---|---|---|---|
| Single-tenant, bearer-token auth | Scope control | Not safe for public hosting | OAuth/OIDC + RBAC + per-user isolation |
| One worker, Postgres queue | Laptop scale | No horizontal scaling; queue lacks a dead-letter UI | Add worker pool + operational UI if needed |
| 10-question test split | Free-tier quota | Wide CIs; weak power | Expand to 30–50 test questions with more quota |
| Frozen snapshots age | Reproducibility | Time-sensitive answers become stale | Periodic `v2` snapshots with as-of dates |
| Free-tier model drift | $0 constraint | Live results may not reproduce | Replay cassettes + recorded model IDs |
| LLM-as-judge bias | Cost | Metric error | Cross-family judge + human calibration + audits |
| No OCR | Dependency weight | Scanned PDFs are unusable | Add OCR as an optional adapter |
| No web UI | Scope | API-only experience | Minimal React/HTMX UI after evals |
| No fine-tuning | $0 + scope | Prompt optimization only | Distillation/fine-tuning if budget appears |
| No real-time monitoring | Scope | Time-sensitive questions are as-of | Scheduled refresh + change detection |
| Contested topics are hard | Epistemics | "Accuracy" is ill-defined | Position coverage + source balance metrics |
| Prompt injection cannot be solved | LLM reality | Residual risk | Defense in depth, canaries, constrained tools |

## 3. Evaluation limitations

- **Power:** 10 test questions cannot support strong claims. CIs will be wide; report them.
- **Judge calibration:** ≥100 human-labeled claims is a start, not a guarantee. Report κ.
- **Snapshot bias:** questions with good frozen evidence may be easier than live research.
- **Cost:** free-tier cost is $0 billed; shadow cost is a modeling choice, not a bill.
- **Seeds:** 3 seeds reveal variance but do not make a small sample large.
- **Leakage:** DSPy tuning on train and selection on dev reduce but do not eliminate overfitting risk.
- **Contested questions:** no single gold answer; score positions and source balance instead.
- **Unanswerable questions:** refusal correctness is judged, which is itself noisy.

## 4. Security and safety limitations

- Prompt injection defenses are probabilistic. A page can still influence tone or content.
- SSRF protections cover HTTP fetches; they do not make arbitrary parsers safe.
- PDF parsing runs in-process; a malicious PDF could exploit a parser bug. Keep dependencies patched.
- No sandbox for code execution (the system does not execute code).
- No malware scanning for downloads.
- Secrets are environment-based; no vault/KMS.
- Free-tier providers may train on prompts. Public data only.

## 5. Free-tier and operational limitations

- Daily limits are the real budget; collection can pause for a day.
- Model IDs and limits change without notice.
- Rate limits can make a benchmark run non-stationary.
- Ollama quality is below API models; local replication is indicative, not equivalent.
- Laptop sleep/restart interrupts runs; checkpoints help, but the worker must be running.
- Disk usage grows with cassettes; pruning is manual until Phase 7.

## 6. Future work (priority order)

| Priority | Item | Why |
|---|---|---|
| P1 | Expand test set to 30+ questions | Statistical power |
| P1 | Human adjudication of the test set | Reduce judge dependence |
| P2 | Better retrieval: reranker + query expansion | Evidence recall |
| P2 | Contradiction search per high-impact claim | Verification depth |
| P2 | Report a calibrated confidence per claim | User trust |
| P3 | Web UI with claim inspection | Usability |
| P3 | OCR adapter | Source coverage |
| P3 | Multi-user auth + memory isolation | Hosted deployment |
| P4 | Fine-tuning/distillation | Cost/quality |
| P4 | Real-time refresh and change detection | Time-sensitive research |
| P4 | Kubernetes/HA | Scale |

## 7. What would make this fail a production review?

- Claiming statistical significance from 10 questions without CIs.
- Hiding unsupported claims instead of flagging them.
- A judge from the same model family with no calibration.
- No replay path for evals.
- Approval gates that can be bypassed by config without an audit trail.
- Treating retrieved web content as trusted instructions.
- Reporting dollar costs for free tiers as if they were billed.

We will keep this list updated as the project matures.
