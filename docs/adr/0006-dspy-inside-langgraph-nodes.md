# ADR-0006: DSPy Inside LangGraph Nodes, Not as the Orchestrator

- **Status:** Accepted
- **Date:** 2026-11-07
- **Phase:** 0 (implemented in Phase 6)
- **Deciders:** Project owner

## Context

DSPy is excellent at optimizing prompts and few-shot demonstrations against a metric. LangGraph is excellent at explicit control flow, state, checkpointing, and human approval. Using either for both jobs creates a bad fit:

- DSPy as orchestrator: opaque control flow, weak checkpoint/resume, awkward interrupts.
- LangGraph as prompt optimizer: no built-in optimizer; hand-rolled prompt search is worse than DSPy.

The system also needs to run the same node with either hand-written prompts or compiled DSPy programs for ablations.

## Decision

Use **DSPy inside LangGraph nodes**:

- Each LLM-driven step is a DSPy `Signature` + `Module` (or a hand-written implementation of the same protocol).
- Nodes call a stable interface: `module(**inputs) -> PydanticOutput`.
- LangGraph owns state, edges, loops, budgets, checkpoints, and approvals.
- DSPy owns prompt/demo optimization for: query decomposition, search-query generation, evidence extraction, claim extraction, claim verification, section writing, and the stop/continue critic.
- Compiled artifacts are JSON files with a manifest: optimizer, seed, dataset hash, metric scores, token/call cost, git SHA, and dependency lock hash.
- Artifact loading validates the hash and falls back to the hand-written module if missing/invalid.
- Optimize the **verifier first** with BootstrapFewShot (cheap, high leverage). MIPROv2 only with a separate budget approval.
- GEPA is a candidate later optimizer, not a default: its cost and provider compatibility must be measured against the same dev metric before adopting it.
- Train on 30 questions (the verifier derives claim-level examples from train runs), select on 10 dev, evaluate once on 10 frozen test.

## Consequences

**Positive**

- Clear separation of concerns.
- Per-module ablations are possible (hand vs DSPy) without changing the graph.
- Compiled artifacts are versioned and auditable.
- Hand-written fallback keeps the system runnable without optimization.

**Negative**

- Two abstraction layers to debug.
- DSPy serialization/version compatibility risk.
- Optimizer cost competes with benchmark quota.
- Compiled demos can overfit or leak if splits are mishandled.

**Mitigations**

- Verify DSPy APIs in Phase 1; pin versions.
- Keep signatures small and outputs Pydantic-validated.
- Log optimization cost in the manifest.
- Freeze test split; no prompt edits after test run.
- Report dev/test gap and CIs.

## Alternatives considered

| Alternative | Why rejected |
|---|---|
| DSPy orchestrates the whole agent | Loses checkpointing/interrupts; hard to bound loops |
| Hand-written prompts only | No systematic optimization; weaker ablation story |
| LangChain prompt templates + manual tuning | Not reproducible; no optimizer |
| Fine-tuning | Costly, violates $0, changes the comparison |
| MIPROv2 first | Expensive; verifier BFS is higher leverage per token |

## Verification

- Module protocol contract tests.
- Artifact manifest validation.
- Fallback when artifact missing.
- Dev/test leakage test (dataset hash + split check).
- Optimization cost recorded.

## References

- `docs/DESIGN.md` §5.4, §5.6
- `docs/EVAL_PLAN.md` §5
- `docs/RISKS.md` R-09, R-10
