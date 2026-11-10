# Scripts

Operational scripts. Each must be idempotent and safe to re-run.

| Script | Purpose | Phase |
|---|---|---|
| `bootstrap.ps1` | Windows setup: env file, uv sync, start Postgres/SearXNG, health check | 0 |
| `bootstrap.sh` | Same for macOS/Linux | 0 |
| `validate_dataset.py` | Enforce dataset shape, splits, cassettes, frozen test hash | 5 |
| `run_benchmark.py` | Run the eval matrix in replay/live mode | 5 |
| `generate_report.py` | Build `EVALUATION.md` + plots from raw JSON | 5 |
| `scan_cassettes.py` | Reject secrets/PII in recorded cassettes | 1 |
| `provider_smoke.py` | Verify provider keys, model IDs, and JSON mode | 1 |
| `prune.py` | Retention for runs/events/memory/cache | 7 |
| `check_quota.py` | Print current provider quota usage | 1 |

Do not put business logic here. Scripts are thin entry points over `src/research_agent`.
