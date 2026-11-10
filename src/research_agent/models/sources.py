"""Source, document, chunk, and evidence-span contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from pydantic import Field, field_validator, model_validator

from research_agent.models.common import (
    SHA256_PATTERN,
    FrozenModel,
    JsonValue,
    SourceKind,
    SourceStatus,
)


def _validate_http_url(value: str) -> str:
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"}:
        raise ValueError("URL must use http or https")
    if not parts.netloc:
        raise ValueError("URL must include a host")
    if parts.username or parts.password:
        raise ValueError("URL must not contain credentials")
    if len(value) > 4096:
        raise ValueError("URL is too long")
    return value


class SourceProvenance(FrozenModel):
    """How a source entered the run. Kept for audit and ranking priors."""

    provider: str
    query: str | None = None
    engine: str | None = None
    rank: int | None = Field(default=None, ge=0)
    parent_url: str | None = None
    request_id: str | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class Source(FrozenModel):
    id: UUID = Field(default_factory=uuid4)
    run_id: UUID
    url: str
    canonical_url: str
    domain: str
    title: str = ""
    kind: SourceKind = SourceKind.WEB
    status: SourceStatus = SourceStatus.PENDING
    fetched_at: datetime | None = None
    content_hash: str | None = Field(default=None, pattern=SHA256_PATTERN)
    http_status: int | None = Field(default=None, ge=100, le=599)
    provenance: SourceProvenance

    @field_validator("url", "canonical_url")
    @classmethod
    def _url_is_http(cls, value: str) -> str:
        return _validate_http_url(value)

    @field_validator("domain")
    @classmethod
    def _domain_is_non_empty(cls, value: str) -> str:
        if not value or len(value) > 253:
            raise ValueError("domain must be 1..253 characters")
        return value.lower().strip(".")

    @model_validator(mode="before")
    @classmethod
    def _fill_derived_fields(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        url = data.get("url")
        if isinstance(url, str):
            parts = urlsplit(url)
            data.setdefault("canonical_url", url)
            if "domain" not in data and parts.hostname:
                data["domain"] = parts.hostname.lower()
        return data


class DocumentMetadata(FrozenModel):
    title: str = ""
    author: str | None = None
    published_at: datetime | None = None
    language: str | None = None
    content_type: str = "text/html"
    page_count: int | None = Field(default=None, ge=0)
    word_count: int | None = Field(default=None, ge=0)


class Document(FrozenModel):
    id: UUID = Field(default_factory=uuid4)
    source_id: UUID
    text: str = Field(min_length=1)
    metadata: DocumentMetadata = Field(default_factory=DocumentMetadata)
    content_hash: str = Field(pattern=SHA256_PATTERN)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Chunk(FrozenModel):
    id: UUID = Field(default_factory=uuid4)
    source_id: UUID
    document_id: UUID
    ordinal: int = Field(ge=0)
    text: str = Field(min_length=1)
    start_char: int = Field(ge=0)
    end_char: int = Field(gt=0)
    token_count: int = Field(ge=0)
    embedding: list[float] | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def _offsets_are_ordered(self) -> Chunk:
        if self.end_char <= self.start_char:
            raise ValueError("end_char must be greater than start_char")
        return self


class ChunkDraft(FrozenModel):
    """A chunk before persistence/embedding."""

    text: str = Field(min_length=1)
    start_char: int = Field(ge=0)
    end_char: int = Field(gt=0)
    token_count: int = Field(ge=0)

    @model_validator(mode="after")
    def _offsets_are_ordered(self) -> ChunkDraft:
        if self.end_char <= self.start_char:
            raise ValueError("end_char must be greater than start_char")
        return self


class EvidenceSpan(FrozenModel):
    id: UUID = Field(default_factory=uuid4)
    source_id: UUID
    chunk_id: UUID
    sub_question_id: str | None = None
    quote: str = Field(min_length=1)
    start_char: int = Field(ge=0)
    end_char: int = Field(gt=0)
    relevance_score: float = Field(default=0.0, ge=0.0, le=1.0)
    quality_score: float = Field(default=0.0, ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def _offsets_are_ordered(self) -> EvidenceSpan:
        if self.end_char <= self.start_char:
            raise ValueError("end_char must be greater than start_char")
        return self
