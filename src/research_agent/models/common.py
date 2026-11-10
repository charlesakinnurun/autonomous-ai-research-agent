"""Shared enums and small value objects used across contracts."""

from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

SLUG_PATTERN = r"^[a-z0-9][a-z0-9_-]{1,63}$"
SHA256_PATTERN = r"^sha256:[0-9a-f]{64}$"
CITATION_MARKER_PATTERN = r"^S[0-9]{1,4}$"


class FrozenModel(BaseModel):
    """Base for immutable value objects crossing module boundaries."""

    model_config = ConfigDict(extra="forbid", frozen=True, validate_assignment=True)


class SourceKind(StrEnum):
    WEB = "web"
    WIKIPEDIA = "wikipedia"
    ARXIV = "arxiv"
    PDF = "pdf"


class SourceStatus(StrEnum):
    PENDING = "pending"
    FETCHED = "fetched"
    FAILED = "failed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"


class SearchProvider(StrEnum):
    SEARXNG = "searxng"
    WIKIPEDIA = "wikipedia"
    ARXIV = "arxiv"


class Verdict(StrEnum):
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    INSUFFICIENT = "insufficient"


class ClaimStatus(StrEnum):
    KEPT = "kept"
    REMOVED = "removed"
    FLAGGED = "flagged"


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    PAUSED_QUOTA = "paused_quota"
    COMPLETED = "completed"
    COMPLETED_WITH_WARNINGS = "completed_with_warnings"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Architecture(StrEnum):
    SINGLE_AGENT = "single_agent"
    MULTI_AGENT = "multi_agent"


class PromptMode(StrEnum):
    HANDWRITTEN = "handwritten"
    DSPY = "dspy"


class ApprovalKind(StrEnum):
    EXPENSIVE_SEARCH = "expensive_search"
    MEMORY_WRITE = "memory_write"
    EXPORT = "export"
    LOW_CONFIDENCE_CLAIM = "low_confidence_claim"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class EventType(StrEnum):
    RUN_STARTED = "run_started"
    NODE_STARTED = "node_started"
    NODE_FINISHED = "node_finished"
    TOOL_CALLED = "tool_called"
    TOOL_FINISHED = "tool_finished"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_DECIDED = "approval_decided"
    QUOTA_PAUSED = "quota_paused"
    QUOTA_RESUMED = "quota_resumed"
    WARNING = "warning"
    ERROR = "error"
    RUN_FINISHED = "run_finished"


class ToolName(StrEnum):
    SEARXNG = "searxng"
    WIKIPEDIA = "wikipedia"
    ARXIV = "arxiv"
    FETCH = "fetch"
    HTML_PARSE = "html_parse"
    PDF_PARSE = "pdf_parse"
    RETRIEVE = "retrieve"
    LLM = "llm"


class Role(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class FinishReason(StrEnum):
    STOP = "stop"
    LENGTH = "length"
    CONTENT_FILTER = "content_filter"
    TOOL_CALLS = "tool_calls"
    ERROR = "error"
    UNKNOWN = "unknown"


class TokenUsage(FrozenModel):
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    requests: int = Field(default=0, ge=0)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def __add__(self, other: TokenUsage) -> TokenUsage:
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            requests=self.requests + other.requests,
        )


class UsageLedger(FrozenModel):
    """Token accounting for one run, optionally broken down by node."""

    total: TokenUsage = Field(default_factory=TokenUsage)
    by_node: dict[str, TokenUsage] = Field(default_factory=dict)
    tool_calls: int = Field(default=0, ge=0)
    llm_calls: int = Field(default=0, ge=0)
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    wall_clock_seconds: float = Field(default=0.0, ge=0)

    @field_validator("by_node")
    @classmethod
    def _validate_node_names(cls, value: dict[str, TokenUsage]) -> dict[str, TokenUsage]:
        for name in value:
            if not name or len(name) > 80:
                raise ValueError("node name must be 1..80 characters")
        return value


class BudgetLimits(FrozenModel):
    max_steps: int = Field(default=40, gt=0)
    max_tool_calls: int = Field(default=25, gt=0)
    max_total_tokens: int = Field(default=100_000, gt=0)
    max_cost_usd: float = Field(default=0.0, ge=0)
    max_wall_clock_seconds: int = Field(default=600, gt=0)
    max_research_loops: int = Field(default=2, ge=0)
    max_revision_loops: int = Field(default=2, ge=0)


class BudgetState(FrozenModel):
    limits: BudgetLimits = Field(default_factory=BudgetLimits)
    usage: UsageLedger = Field(default_factory=UsageLedger)
    deadline_epoch_seconds: float | None = None

    @property
    def total_tokens(self) -> int:
        return self.usage.total.total_tokens

    def with_usage(self, usage: UsageLedger) -> BudgetState:
        return self.model_copy(update={"usage": usage})


class LoopCounters(FrozenModel):
    research: int = Field(default=0, ge=0)
    revision: int = Field(default=0, ge=0)
    steps: int = Field(default=0, ge=0)
    tool_calls: int = Field(default=0, ge=0)
    critic: int = Field(default=0, ge=0)


class AgentError(FrozenModel):
    code: str
    message: str
    node: str | None = None
    retryable: bool = False
    details: dict[str, str] = Field(default_factory=dict)


class PageInfo(FrozenModel):
    limit: int = Field(ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class ApprovalDecision(FrozenModel):
    approved: bool
    decided_by: str
    reason: str | None = None


class QuotaLimits(FrozenModel):
    """Daily/minute limits loaded from provider config.

    ``0`` means unlimited and is only valid for local providers (Ollama).
    """

    rpm: int = Field(default=0, ge=0)
    rpd: int = Field(default=0, ge=0)
    tpm: int = Field(default=0, ge=0)
    tpd: int = Field(default=0, ge=0)


class QuotaSnapshot(FrozenModel):
    provider: str
    model: str
    day: date
    requests: int = Field(default=0, ge=0)
    tokens_in: int = Field(default=0, ge=0)
    tokens_out: int = Field(default=0, ge=0)
    reserved: int = Field(default=0, ge=0)

    @property
    def total_tokens(self) -> int:
        return self.tokens_in + self.tokens_out + self.reserved


class QuotaReservationRecord(FrozenModel):
    id: UUID
    provider: str
    model: str
    day: date
    tokens: int = Field(ge=0)
    expires_at: datetime


class CitationMarker(StrEnum):
    """Enum is not used for markers; this class documents the pattern."""

    PATTERN = CITATION_MARKER_PATTERN


JsonValue = Annotated[
    str | int | float | bool | list[Any] | dict[str, Any] | None,
    Field(description="JSON-compatible value"),
]
"""(Typed) JSON value for provenance payloads. Avoid using this for contracts
that deserve their own model."""

UUIDStr = Annotated[str, Field(pattern=r"^[0-9a-fA-F-]{36}$")]
"""(Typed) UUID string for JSON payloads where a parsed UUID is unnecessary."""

SortOrder = Literal["asc", "desc"]
"""Stable sort direction for list endpoints."""
