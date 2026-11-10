"""Atomic claims, verifier verdicts, and citations."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import Field, field_validator, model_validator

from research_agent.models.common import (
    CITATION_MARKER_PATTERN,
    ClaimStatus,
    FrozenModel,
    Verdict,
)


class Claim(FrozenModel):
    id: UUID = Field(default_factory=uuid4)
    run_id: UUID
    section: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=4000)
    status: ClaimStatus = ClaimStatus.KEPT
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    citation_markers: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("citation_markers")
    @classmethod
    def _markers_are_valid(cls, value: list[str]) -> list[str]:
        import re

        for marker in value:
            if not re.fullmatch(CITATION_MARKER_PATTERN, marker):
                raise ValueError(f"invalid citation marker: {marker!r}")
        return list(dict.fromkeys(value))

    @model_validator(mode="after")
    def _kept_claims_are_cited(self) -> Claim:
        if self.status is ClaimStatus.KEPT and not self.citation_markers:
            raise ValueError("kept claims must have at least one citation marker")
        return self


class ClaimEvidence(FrozenModel):
    claim_id: UUID
    chunk_id: UUID
    source_id: UUID
    verdict: Verdict
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    quoted_span: str = Field(min_length=1, max_length=4000)
    rationale: str = Field(default="", max_length=2000)
    verifier_model: str = Field(min_length=1, max_length=200)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ClaimVerdict(FrozenModel):
    claim_id: UUID
    verdict: Verdict
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(default="", max_length=2000)
    evidence: list[ClaimEvidence] = Field(default_factory=list)
    verifier_model: str = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def _support_needs_evidence(self) -> ClaimVerdict:
        if self.verdict in {Verdict.SUPPORTED, Verdict.CONTRADICTED} and not self.evidence:
            raise ValueError("supported/contradicted verdicts require evidence")
        return self


class Citation(FrozenModel):
    id: UUID = Field(default_factory=uuid4)
    claim_id: UUID
    source_id: UUID
    chunk_id: UUID
    marker: str = Field(pattern=CITATION_MARKER_PATTERN)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ClaimBundle(FrozenModel):
    """A claim plus its verdict and resolved citations.

    This is the unit the report renderer consumes; it prevents the renderer from
    joining untyped dictionaries.
    """

    claim: Claim
    verdict: ClaimVerdict
    citations: list[Citation] = Field(default_factory=list)

    @model_validator(mode="after")
    def _ids_match(self) -> ClaimBundle:
        if self.verdict.claim_id != self.claim.id:
            raise ValueError("verdict claim_id does not match claim")
        if any(citation.claim_id != self.claim.id for citation in self.citations):
            raise ValueError("citation claim_id does not match claim")
        markers = {citation.marker for citation in self.citations}
        if not set(self.claim.citation_markers).issubset(markers):
            raise ValueError("claim markers are not all resolved by citations")
        return self
