"""LangGraph state and reducers.

The graph state is a ``TypedDict`` whose fields are Pydantic models. Reducers
dedupe by stable keys instead of simply appending, so retries and resumptions do
not duplicate sources or claims.

Every field is optional (``total=False``) so nodes can return partial updates.
"""

from __future__ import annotations

import operator
from collections.abc import Sequence
from typing import Annotated, Protocol, TypedDict, TypeVar
from uuid import UUID

from research_agent.models.claims import Claim, ClaimVerdict
from research_agent.models.common import (
    AgentError,
    BudgetState,
    LoopCounters,
    UsageLedger,
)
from research_agent.models.research import (
    ApprovalRequest,
    CoverageReport,
    CritiqueDecision,
    FinalReport,
    ReportDraft,
    ResearchPlan,
    RunContext,
)
from research_agent.models.sources import EvidenceSpan, Source


class HasId(Protocol):
    id: UUID


T = TypeVar("T", bound=HasId)


def append_unique_by_id(left: Sequence[T], right: Sequence[T]) -> list[T]:
    """Append items whose id is not already present (stable first-wins)."""
    seen = {item.id for item in left}
    merged = list(left)
    for item in right:
        if item.id not in seen:
            seen.add(item.id)
            merged.append(item)
    return merged


def append_unique_by_url(left: Sequence[Source], right: Sequence[Source]) -> list[Source]:
    """Dedupe sources by canonical URL, not by generated id."""
    seen = {item.canonical_url for item in left}
    merged = list(left)
    for item in right:
        if item.canonical_url not in seen:
            seen.add(item.canonical_url)
            merged.append(item)
    return merged


def append_unique_evidence(
    left: Sequence[EvidenceSpan], right: Sequence[EvidenceSpan]
) -> list[EvidenceSpan]:
    """Dedupe evidence by (source, chunk, quote) so a retry is idempotent."""
    seen = {(item.source_id, item.chunk_id, item.quote) for item in left}
    merged = list(left)
    for item in right:
        key = (item.source_id, item.chunk_id, item.quote)
        if key not in seen:
            seen.add(key)
            merged.append(item)
    return merged


def append_unique_verdicts(
    left: Sequence[ClaimVerdict], right: Sequence[ClaimVerdict]
) -> list[ClaimVerdict]:
    """Keep the latest verdict for each claim."""
    by_claim = {item.claim_id: item for item in left}
    for item in right:
        by_claim[item.claim_id] = item
    return list(by_claim.values())


class ResearchState(TypedDict, total=False):
    run: RunContext
    budget: BudgetState
    usage: UsageLedger
    loop_counters: LoopCounters

    plan: ResearchPlan | None
    research_cursor: int

    sources: Annotated[list[Source], append_unique_by_url]
    evidence: Annotated[list[EvidenceSpan], append_unique_evidence]
    coverage: CoverageReport | None

    draft: ReportDraft | None
    claims: Annotated[list[Claim], append_unique_by_id]
    verdicts: Annotated[list[ClaimVerdict], append_unique_verdicts]

    critique: CritiqueDecision | None
    approvals: Annotated[list[ApprovalRequest], append_unique_by_id]
    approval: ApprovalRequest | None

    errors: Annotated[list[AgentError], operator.add]
    warnings: Annotated[list[str], operator.add]

    final_report: FinalReport | None
