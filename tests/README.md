# Tests

The pyramid, from fast to slow:

| Layer | Marker | What it proves |
|---|---|---|
| Unit | `unit` | Pure logic: parsers, citation validation, budget math, cache keys |
| Integration | `integration` | Postgres, migrations, repositories, graph checkpoints |
| Contract | `contract` | FastAPI request/response/SSE/idempotency behavior |
| Eval | `eval` | Harness, metrics, replay determinism, regression gates |
| Smoke | `smoke` | Installability and critical config presence |

Rules:

- Unit tests never touch the network or a real database.
- Integration tests use `DATABASE_URL` and skip with a clear message if absent.
- Replay tests assert zero network calls and fail on cache miss.
- Live tests are marked `live` and never run in CI.
- Tests are deterministic: freeze time, seed randomness, no sleeps longer than needed.

Run:

```bash
uv run pytest -m unit
uv run pytest -m integration
uv run pytest -m "not live and not slow"
uv run pytest -m smoke
```
