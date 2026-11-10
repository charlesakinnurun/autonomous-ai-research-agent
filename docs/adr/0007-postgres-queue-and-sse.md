# ADR-0007: Postgres Job Queue + SSE for Progress

- **Status:** Accepted
- **Date:** 2026-11-07
- **Phase:** 0 (implemented in Phase 2)
- **Deciders:** Project owner

## Context

The API must start long-running research jobs, stream progress, and survive worker restarts. The laptop deployment should not require Redis, Celery, RabbitMQ, or a WebSocket gateway.

Options:

- FastAPI `BackgroundTasks` only.
- Celery + Redis.
- Postgres-backed job queue with `FOR UPDATE SKIP LOCKED`.
- External managed queue (not $0/laptop-friendly).

Progress streaming options: SSE, WebSocket, polling.

## Decision

Use a **Postgres-backed job queue**:

- `run_jobs` table with `status`, `priority`, `available_at`, `locked_at`, `locked_by`, `attempts`.
- Worker claims jobs with `SELECT ... FOR UPDATE SKIP LOCKED`.
- Heartbeat extends the lease; stale leases are reclaimed.
- `paused_quota` jobs get a future `available_at`.
- LangGraph checkpoints hold execution state; the job row holds scheduling state.

Use **SSE** for progress:

- Events are persisted in `run_events` with a monotonic `bigserial` ID.
- `GET /v1/runs/{id}/events` tails the table and supports `Last-Event-ID`.
- Reconnect is trivial; no in-memory pub/sub required.
- Polling remains available as a fallback.

## Consequences

**Positive**

- No extra infrastructure; one database.
- Durable scheduling and progress.
- SSE works through proxies and reconnects cleanly.
- Worker restart is safe: lease + checkpoint + idempotent events.

**Negative**

- Postgres queue is less featureful than Celery (no built-in retries/UI).
- Polling the events table has a small latency/DB cost.
- SSE is one-way; approvals use separate POSTs.
- Lease/heartbeat logic must be tested.

**Mitigations**

- Keep the queue small and well-tested; add a dead-letter view in Phase 7.
- Use `LISTEN/NOTIFY` only if polling latency becomes a problem.
- Contract-test reconnect and duplicate delivery.
- Document the operational limits (single worker, laptop scale).

## Alternatives considered

| Alternative | Why rejected |
|---|---|
| Celery + Redis | Extra service, config, and failure mode for laptop scale |
| FastAPI BackgroundTasks | No durability; lost on restart; no scheduling |
| WebSocket | More complex reconnect/proxy story; one-way progress is enough |
| Managed queue | Violates $0/laptop constraint |
| Polling only | Works, but SSE gives a better demo and is still simple |

## Verification

- Worker claim/lease/reclaim test.
- Restart/resume integration test.
- SSE reconnect with `Last-Event-ID`.
- Duplicate event handling test.
- Quota-paused job reschedule test.

## References

- `docs/DESIGN.md` §5.2, §5.11
- `docs/RISKS.md` R-12, R-13
