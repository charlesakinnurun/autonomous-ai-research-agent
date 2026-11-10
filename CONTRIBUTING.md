# Contributing

Thanks for helping build this. The project is opinionated about evidence, reproducibility, and scope. Read `docs/DESIGN.md` and `docs/REQUIREMENTS.md` before a non-trivial PR.

## Setup

```bash
cp .env.example .env
uv sync --group dev
docker compose up -d postgres searxng
uv run pre-commit install
make check
```

Windows: use `scripts/bootstrap.ps1` and `Copy-Item .env.example .env`.

## Development workflow

1. Open an issue or write a short proposal for anything beyond a bug fix.
2. Create a branch: `feat/<topic>`, `fix/<topic>`, `docs/<topic>`, `eval/<topic>`.
3. Keep changes small and typed. No untyped `dict` across module boundaries.
4. Add tests with the code. Unit tests mock HTTP; integration tests use Postgres.
5. Run `make check` before pushing.
6. Open a PR using the checklist below.

## Code standards

- Python 3.11+ syntax; `from __future__ import annotations` in new modules.
- Pydantic v2 models for all contracts: tool I/O, agent state, claims, evidence, API schemas.
- No bare `except Exception` without re-raising or converting to a typed error.
- No secrets in code, logs, cassettes, or test fixtures.
- Timezone-aware datetimes (`datetime.now(UTC)`), never naive.
- Structured logging via `structlog`; include `run_id`/`trace_id` where relevant.
- Network calls go through the tool layer with timeouts, retries, and caching.
- New dependencies need a short justification in the PR; prefer stdlib.
- Public functions have type annotations and a docstring explaining **why**, not restating the signature.

## Tests

| Layer | Location | Rules |
|---|---|---|
| Unit | `tests/unit` | No network, no DB; mock HTTP with `respx` |
| Integration | `tests/integration` | Postgres via `DATABASE_URL`; skip if unavailable |
| Contract | `tests/contract` | FastAPI via `httpx.AsyncClient` |
| Eval | `tests/evals`, `evals/` | Replay-only in CI; frozen splits |

- Coverage gate: 80% overall, 90% on `core/`, `tools/`, `memory/`.
- A bug fix needs a regression test.
- A flaky test is a bug; fix or quarantine with an issue.

## Evaluation rules (non-negotiable)

- The **test split is frozen**. Do not tune prompts, thresholds, or retrieval on it.
- DSPy optimization uses train; model selection uses dev; test is touched once per version.
- Report CIs and sample size. Do not claim significance from a single run.
- Judge must be a different model family where possible; calibrate against human labels.
- Every eval run records git SHA, dataset hash, prompt/artifact hash, model IDs, seeds, and cost.
- Replay mode must make zero network calls.

## Commits and PRs

Conventional commits are encouraged:

```text
feat(graph): add coverage critic
fix(tools): block redirects to private IPs
docs(eval): clarify judge calibration
test(citations): reject dangling markers
```

PR checklist:

- [ ] Linked issue / design note.
- [ ] Typed contracts; no untyped dicts across boundaries.
- [ ] Tests added; `make check` green.
- [ ] No secrets or PII.
- [ ] Docs/ADRs updated if behavior or a decision changed.
- [ ] Cost/token impact estimated.
- [ ] Scope is within v0.1 (see the parking lot in `docs/REQUIREMENTS.md`).

## Security

Do not open a public issue for a vulnerability. Email the maintainer or use GitHub's private vulnerability reporting. See `docs/RISKS.md` for known threats. Prompt-injection and SSRF tests are mandatory for changes to retrieval or tool execution.

## License

By contributing, you agree that your contributions are licensed under the MIT License.
