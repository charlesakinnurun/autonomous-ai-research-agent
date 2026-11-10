"""Typed tool request/response contracts.

Every tool has a Pydantic request and response. Nodes never pass raw dicts to a
tool; they construct one of these models.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import Field, field_validator, model_validator

from research_agent.models.common import (
    SHA256_PATTERN,
    FinishReason,
    FrozenModel,
    Role,
    SearchProvider,
    SourceKind,
    TokenUsage,
)
from research_agent.models.sources import Chunk, DocumentMetadata, Source


def _validate_url(value: str) -> str:
    from urllib.parse import urlsplit

    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise ValueError("URL must be an absolute http(s) URL")
    if parts.username or parts.password:
        raise ValueError("URL must not contain credentials")
    return value


class SearchRequest(FrozenModel):
    query: str = Field(min_length=1, max_length=1000)
    max_results: int = Field(default=8, ge=1, le=50)
    language: str = Field(default="en", min_length=2, max_length=16)
    safe_search: int = Field(default=0, ge=0, le=2)
    engines: list[str] = Field(default_factory=list, max_length=20)
    time_range: str | None = Field(default=None, pattern=r"^(day|week|month|year)$")
    categories: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("query")
    @classmethod
    def _query_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must not be blank")
        return value.strip()


class SearchResult(FrozenModel):
    title: str = Field(default="", max_length=500)
    url: str
    canonical_url: str
    domain: str
    snippet: str = Field(default="", max_length=4000)
    provider: SearchProvider
    rank: int = Field(ge=0)
    score: float | None = Field(default=None, ge=0.0)
    published_at: datetime | None = None
    kind: SourceKind = SourceKind.WEB

    @field_validator("url", "canonical_url")
    @classmethod
    def _url_is_http(cls, value: str) -> str:
        return _validate_url(value)


class SearchResponse(FrozenModel):
    query: str
    provider: SearchProvider
    results: list[SearchResult] = Field(default_factory=list)
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    cached: bool = False
    latency_ms: float = Field(default=0.0, ge=0)
    warnings: list[str] = Field(default_factory=list)


class FetchRequest(FrozenModel):
    url: str
    headers: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: float = Field(default=15.0, gt=0, le=120)
    max_bytes: int = Field(default=3_000_000, gt=0, le=50_000_000)
    allowed_content_types: list[str] = Field(default_factory=list)
    respect_robots_txt: bool = True
    user_agent: str | None = None

    @field_validator("url")
    @classmethod
    def _url_is_http(cls, value: str) -> str:
        return _validate_url(value)

    @field_validator("headers")
    @classmethod
    def _no_authorization_header(cls, value: dict[str, str]) -> dict[str, str]:
        forbidden = {"authorization", "cookie", "set-cookie"}
        if forbidden & {key.lower() for key in value}:
            raise ValueError("fetch headers must not contain credentials")
        return value


class FetchResponse(FrozenModel):
    url: str
    final_url: str
    status_code: int = Field(ge=100, le=599)
    content_type: str = ""
    headers: dict[str, str] = Field(default_factory=dict)
    body: bytes = b""
    text: str | None = None
    content_hash: str = Field(pattern=SHA256_PATTERN)
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    truncated: bool = False
    redirect_chain: list[str] = Field(default_factory=list)
    cached: bool = False
    latency_ms: float = Field(default=0.0, ge=0)

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300

    @field_validator("url", "final_url")
    @classmethod
    def _url_is_http(cls, value: str) -> str:
        return _validate_url(value)


class ParseRequest(FrozenModel):
    url: str
    content_type: str
    body: bytes = Field(min_length=1)
    encoding: str | None = None

    @field_validator("url")
    @classmethod
    def _url_is_http(cls, value: str) -> str:
        return _validate_url(value)


class ParsedDocument(FrozenModel):
    url: str
    text: str = Field(min_length=1)
    title: str = ""
    author: str | None = None
    published_at: datetime | None = None
    language: str | None = None
    content_type: str
    page_count: int | None = Field(default=None, ge=0)
    word_count: int = Field(default=0, ge=0)
    content_hash: str = Field(pattern=SHA256_PATTERN)
    parser: str
    warnings: list[str] = Field(default_factory=list)

    @field_validator("url")
    @classmethod
    def _url_is_http(cls, value: str) -> str:
        return _validate_url(value)

    @property
    def metadata(self) -> DocumentMetadata:
        return DocumentMetadata(
            title=self.title,
            author=self.author,
            published_at=self.published_at,
            language=self.language,
            content_type=self.content_type,
            page_count=self.page_count,
            word_count=self.word_count,
        )


class RetrieveRequest(FrozenModel):
    run_id: UUID
    query: str = Field(min_length=1, max_length=1000)
    top_k: int = Field(default=8, ge=1, le=50)
    sub_question_id: str | None = None
    hybrid: bool = True
    min_score: float = Field(default=0.0, ge=0.0, le=1.0)


class RetrievedChunk(FrozenModel):
    chunk: Chunk
    source: Source
    score: float = Field(ge=0.0)
    vector_score: float | None = Field(default=None, ge=0.0)
    keyword_score: float | None = Field(default=None, ge=0.0)


class RetrieveResponse(FrozenModel):
    query: str
    results: list[RetrievedChunk] = Field(default_factory=list)
    cached: bool = False
    latency_ms: float = Field(default=0.0, ge=0)
    warnings: list[str] = Field(default_factory=list)


class LLMMessage(FrozenModel):
    role: Role
    content: str
    name: str | None = Field(default=None, max_length=100)


class LLMRequest(FrozenModel):
    model: str = Field(min_length=1, max_length=200)
    messages: list[LLMMessage] = Field(min_length=1)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1024, ge=1, le=100_000)
    response_format: str | None = Field(default=None, pattern=r"^(text|json_object)$")
    seed: int | None = None
    stop: list[str] = Field(default_factory=list, max_length=8)


class LLMResponse(FrozenModel):
    model: str
    provider: str
    content: str
    usage: TokenUsage = Field(default_factory=TokenUsage)
    finish_reason: FinishReason = FinishReason.STOP
    cached: bool = False
    latency_ms: float = Field(default=0.0, ge=0)
    request_id: UUID = Field(default_factory=uuid4)


class LLMRequestEnvelope(FrozenModel):
    """Cache envelope payload for an LLM call (provider-independent)."""

    request: LLMRequest
    role: str | None = None


class ToolCallRecord(FrozenModel):
    tool: str
    request_id: UUID = Field(default_factory=uuid4)
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None
    ok: bool = True
    cached: bool = False
    error: str | None = None

    @model_validator(mode="after")
    def _times_are_ordered(self) -> ToolCallRecord:
        if self.finished_at is not None and self.finished_at < self.started_at:
            raise ValueError("finished_at must be >= started_at")
        return self
