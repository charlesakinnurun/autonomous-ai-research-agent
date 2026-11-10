"""Research plan, report, run context, and approval contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID, uuid4

from pydantic import Field, field_validator, model_validator

from research_agent.models.claims import Citation, ClaimBundle
from research_agent.models.common import (
    ApprovalKind,
    ApprovalStatus,
    Architecture,
    FrozenModel,
    JsonValue,
    PromptMode,
    RunStatus,
)
from research_agent.models.sources import Source


class SubQuestionStatus(StrEnum):
    PENDING = "pending"
    RESEARCHING = "researching"
    COVERED = "covered"
    UNANSWERED = "unanswered"


class SubQuestion(FrozenModel):
    id: str = Field(pattern=r"^sq-[a-z0-9-]{1,40}$")
    question: str = Field(min_length=3, max_length=1000)
    rationale: str = Field(default="", max_length=1000)
    depends_on: list[str] = Field(default_factory=list)
    search_queries: list[str] = Field(default_factory=list, max_length=8)
    status: SubQuestionStatus = SubQuestionStatus.PENDING

    @field_validator("search_queries")
    @classmethod
    def _queries_are_non_empty(cls, value: list[str]) -> list[str]:
        if any(not query.strip() for query in value):
            raise ValueError("search queries must be non-empty")
        return value


class ResearchPlan(FrozenModel):
    id: UUID = Field(default_factory=uuid4)
    question: str = Field(min_length=3, max_length=4000)
    sub_questions: list[SubQuestion] = Field(min_length=1, max_length=12)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    version: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def _unique_ids(self) -> ResearchPlan:
        ids = [item.id for item in self.sub_questions]
        if len(ids) != len(set(ids)):
            raise ValueError("sub-question ids must be unique")
        known = set(ids)
        for item in self.sub_questions:
            missing = set(item.depends_on) - known
            if missing:
                raise ValueError(f"unknown dependencies: {sorted(missing)}")
        return self


class CoverageGap(FrozenModel):
    sub_question_id: str
    reason: str
    suggested_queries: list[str] = Field(default_factory=list, max_length=4)


class CoverageReport(FrozenModel):
    sub_question_coverage: dict[str, float] = Field(default_factory=dict)
    gaps: list[CoverageGap] = Field(default_factory=list)
    total_sources: int = Field(default=0, ge=0)
    total_evidence_spans: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def is_sufficient(self) -> bool:
        return not self.gaps and bool(self.sub_question_coverage)


class ReportSection(FrozenModel):
    title: str = Field(min_length=1, max_length=200)
    markdown: str = Field(min_length=1)
    claim_ids: list[UUID] = Field(default_factory=list)


class ReportDraft(FrozenModel):
    sections: list[ReportSection] = Field(min_length=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    revision: int = Field(default=0, ge=0)


class FinalReport(FrozenModel):
    run_id: UUID
    question: str
    markdown: str = Field(min_length=1)
    sections: list[ReportSection]
    claims: list[ClaimBundle]
    citations: list[Citation]
    sources: list[Source]
    warnings: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def _citation_markers_resolve(self) -> FinalReport:
        markers = {citation.marker for citation in self.citations}
        for bundle in self.claims:
            missing = set(bundle.claim.citation_markers) - markers
            if missing:
                raise ValueError(f"unresolved citation markers: {sorted(missing)}")
        return self


class CritiqueDecision(FrozenModel):
    route: Literal["research", "write", "revise", "finalize"]
    rationale: str = Field(default="", max_length=2000)
    gaps: list[CoverageGap] = Field(default_factory=list)
    revision_instructions: list[str] = Field(default_factory=list, max_length=10)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class RunContext(FrozenModel):
    run_id: UUID
    trace_id: str
    question: str = Field(min_length=3, max_length=4000)
    as_of: datetime = Field(default_factory=lambda: datetime.now(UTC))
    architecture: Architecture = Architecture.MULTI_AGENT
    prompt_mode: PromptMode = PromptMode.HANDWRITTEN
    user_id: str = "local"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ApprovalRequest(FrozenModel):
    id: UUID = Field(default_factory=uuid4)
    run_id: UUID
    kind: ApprovalKind
    payload: dict[str, JsonValue] = Field(default_factory=dict)
    status: ApprovalStatus = ApprovalStatus.PENDING
    requested_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    decided_at: datetime | None = None
    decided_by: str | None = None
    reason: str | None = None


class RunRecord(FrozenModel):
    """Persistence-facing view of a run (API/repository boundary)."""

    id: UUID
    question: str
    architecture: Architecture
    prompt_mode: PromptMode
    status: RunStatus
    trace_id: str
    created_at: datetime
    updated_at: datetime
    error: str | None = None
