"""Content-addressed record/replay cache for every external call.

Design goals:

- ``replay`` performs zero network calls and fails loudly on a miss.
- ``record`` calls live and writes an immutable envelope.
- ``live`` bypasses the cache entirely.
- Keys include the tool name/version and the normalized request, so a prompt or
  parser change produces a new key instead of a false hit.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from research_agent.config import LLMMode
from research_agent.core.errors import CacheError, CacheMissError
from research_agent.core.ids import canonical_json_text, stable_hash, utc_now
from research_agent.models.common import TokenUsage


def make_cache_key(
    *,
    tool: str,
    version: str,
    request: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> str:
    """Stable key for a tool call.

    The version is part of the key on purpose: changing a parser or prompt must
    invalidate old recordings.
    """
    payload = {"tool": tool, "version": version, "request": request, "config": config or {}}
    return stable_hash(payload)


class CacheEnvelope(BaseModel):
    key: str = Field(pattern=r"^[0-9a-f]{64}$")
    tool: str
    version: str
    request: dict[str, Any]
    response: dict[str, Any]
    provider: str | None = None
    model: str | None = None
    recorded_at: datetime = Field(default_factory=utc_now)
    latency_ms: float = Field(default=0.0, ge=0)
    usage: TokenUsage | None = None
    content_hash: str | None = None


class CacheStore:
    """Filesystem cache with three explicit modes."""

    def __init__(self, root: Path, mode: LLMMode = "replay") -> None:
        self.root = Path(root)
        self.mode = mode

    def _path(self, tool: str, key: str) -> Path:
        # Shard by key prefix to avoid huge directories on Windows.
        return self.root / tool / key[:2] / key[2:4] / f"{key}.json"

    def read(self, *, tool: str, key: str, required: bool = False) -> CacheEnvelope | None:
        path = self._path(tool, key)
        if not path.exists():
            if required:
                raise CacheMissError(
                    f"cache miss for {tool} key {key}",
                    details={"tool": tool, "key": key, "path": str(path), "mode": self.mode},
                )
            return None
        try:
            raw = path.read_text(encoding="utf-8")
            envelope = CacheEnvelope.model_validate_json(raw)
        except Exception as exc:
            raise CacheError(f"invalid cache entry: {path}") from exc
        if envelope.key != key or envelope.tool != tool:
            raise CacheError(f"cache identity mismatch: {path}")
        return envelope

    def write(self, envelope: CacheEnvelope) -> Path:
        path = self._path(envelope.tool, envelope.key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(envelope.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(path)
        return path

    def get_response(self, *, tool: str, key: str) -> CacheEnvelope:
        return self.read(tool=tool, key=key, required=True)  # type: ignore[return-value]

    def put(
        self,
        *,
        tool: str,
        version: str,
        request: dict[str, Any],
        response: dict[str, Any],
        provider: str | None = None,
        model: str | None = None,
        latency_ms: float = 0.0,
        usage: TokenUsage | None = None,
        content_hash: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> CacheEnvelope:
        key = make_cache_key(tool=tool, version=version, request=request, config=config)
        envelope = CacheEnvelope(
            key=key,
            tool=tool,
            version=version,
            request=request,
            response=response,
            provider=provider,
            model=model,
            recorded_at=datetime.now(UTC),
            latency_ms=latency_ms,
            usage=usage,
            content_hash=content_hash,
        )
        if self.mode == "record":
            self.write(envelope)
        return envelope

    def describe(self) -> dict[str, Any]:
        return {
            "root": str(self.root),
            "mode": self.mode,
            "exists": self.root.exists(),
            "key_algorithm": "sha256-canonical-json",
        }


def envelope_request_hash(envelope: CacheEnvelope) -> str:
    """Deterministic request hash for diagnostics/tests."""
    return stable_hash(envelope.request)


def canonical_request(request: BaseModel | dict[str, Any]) -> dict[str, Any]:
    """Convert a request model to a JSON-safe dict for cache keys."""
    if isinstance(request, BaseModel):
        return request.model_dump(mode="json", exclude_none=True)
    return {key: value for key, value in request.items() if value is not None}


def cache_key_for_model(
    *,
    tool: str,
    version: str,
    request: BaseModel,
    config: dict[str, Any] | None = None,
) -> str:
    return make_cache_key(
        tool=tool,
        version=version,
        request=canonical_request(request),
        config=config,
    )


__all__ = [
    "CacheEnvelope",
    "CacheStore",
    "cache_key_for_model",
    "canonical_json_text",
    "canonical_request",
    "envelope_request_hash",
    "make_cache_key",
]
