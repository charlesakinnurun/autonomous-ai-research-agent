# ADR-0001: LangGraph for Orchestration

- **Status:** Accepted
- **Date:** 2026-11-07
- **Phase:** 0
- **Deciders:** Project owner

## Context

The system needs explicit multi-step control flow, typed state, bounded loops, durable checkpoints, and human-in-the-loop pauses. The two candidate approaches are a general agent framework (CrewAI, AutoGen) or a graph/state-machine library (LangGraph), versus a hand-rolled orchestrator.

Requirements that dominate:

- Resume after process restart.
- Pause for human approval and continue from the exact node.
- Enforce loop/budget limits centrally.
- Keep state typed and inspectable.
- Support both single-agent and multi-agent architectures behind one interface.

## Decision

Use **LangGraph** as the orchestration layer. The graph owns nodes, conditional edges, state, checkpointing, interrupts, and loop bounds. LLM behavior is delegated to DSPy modules or hand-written prompts behind stable interfaces.

State is a `TypedDict` whose fields are Pydantic models and typed collections. Domain objects remain Pydantic. This avoids reducer complexity while keeping validation at every boundary.

## Consequences

**Positive**

- Checkpointing and interrupts are first-class, not bolted on.
- Explicit graph is reviewable and testable; no hidden agent loop.
- Conditional edges make the critic/loop logic visible.
- Postgres checkpointer shares the operational surface with the rest of the app.
- Single-agent baseline can be another graph behind the same interface.

**Negative**

- LangGraph API churn is a real risk (see R-01).
- Checkpoint schema ownership must be handled carefully with Alembic.
- Graph state can become a god object if not disciplined.
- Debugging interrupts/resume has a learning curve.

**Mitigations**

- Verify APIs in a day-1 spike; pin versions; isolate behind `GraphRunner`.
- Keep node functions small and pure where possible.
- Enforce state invariants in tests.
- Document the checkpoint table lifecycle.

## Alternatives considered

| Alternative | Why rejected |
|---|---|
| CrewAI | Higher-level, less control over state, retries, and interrupts; harder to prove fairness |
| AutoGen | Conversation-centric; durable checkpoint/resume and typed state are weaker fits |
| Custom finite-state machine | Would reimplement checkpointing, interrupts, and streaming; high maintenance |
| Temporal | Excellent durability, but another service and a heavier operational story for a laptop |
| Prefect/Dagster | Data-pipeline oriented; human-in-the-loop and agent state are awkward |

## Verification

- Restart/resume integration test in Phase 3.
- Approval approve/reject test.
- Loop-cap and no-progress tests.
- State invariant tests.

## References

- `docs/DESIGN.md` §5.3–5.5
- `docs/RISKS.md` R-01, R-11
