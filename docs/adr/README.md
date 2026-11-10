# Architecture Decision Records

| ADR | Title | Status |
|---|---|---|
| [0001](0001-langgraph-orchestration.md) | LangGraph for orchestration | Accepted |
| [0002](0002-free-tier-llm-router.md) | Provider-agnostic LLM router + Postgres quota tracker | Accepted |
| [0003](0003-record-replay-cache.md) | Record/replay cache for every external call | Accepted |
| [0004](0004-evidence-first-citations.md) | Evidence-first claims and claim-level citations | Accepted |
| [0005](0005-benchmark-single-vs-multi-agent.md) | Frozen, paired single- vs multi-agent benchmark | Accepted |
| [0006](0006-dspy-inside-langgraph-nodes.md) | DSPy inside LangGraph nodes | Accepted |
| [0007](0007-postgres-queue-and-sse.md) | Postgres job queue + SSE | Accepted |

## When to write an ADR

Write one when a decision:

- changes a public interface or data model;
- adds or removes an infrastructure dependency;
- trades off cost, latency, accuracy, or safety in a non-obvious way;
- would be expensive to reverse;
- is likely to be questioned in review.

Do not write ADRs for reversible implementation details. Use code comments and PR descriptions for those.

## ADR lifecycle

- **Proposed** — under discussion.
- **Accepted** — implemented or approved for implementation.
- **Superseded** — replaced by a newer ADR; link both ways.
- **Deprecated** — no longer relevant.
