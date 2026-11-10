"""Identifiers, timestamps, hashing, and canonical JSON helpers."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(UTC)


def new_uuid() -> uuid.UUID:
    """Return a random UUID (v4)."""
    return uuid.uuid4()


def trace_id_for(run_id: uuid.UUID) -> str:
    """Stable trace id derived from the run id."""
    return f"trace-{run_id.hex}"


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def content_hash(text: str) -> str:
    """Content hash used for dedupe and cache identity."""
    return f"sha256:{sha256_hex(text.encode('utf-8'))}"


def content_hash_bytes(data: bytes) -> str:
    """Content hash for binary payloads (fetched pages, PDFs)."""
    return f"sha256:{sha256_hex(data)}"


def canonical_json_text(value: Any) -> str:
    """Canonical JSON used for cache keys and request hashes.

    Sorted keys, compact separators, UTF-8, and ``default=str`` make the key
    independent of dict insertion order. UUIDs and datetimes become strings,
    which is exactly what the cache needs for a stable identity.
    """
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )


def canonical_json_bytes(value: Any) -> bytes:
    return canonical_json_text(value).encode("utf-8")


def stable_hash(value: Any) -> str:
    """Hash a JSON-serializable value with the canonical encoding."""
    return sha256_hex(canonical_json_bytes(value))


def json_dumps(value: Any, *, pretty: bool = False) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        indent=2 if pretty else None,
        separators=None if pretty else (",", ":"),
        ensure_ascii=False,
        default=str,
    )


def json_loads(value: str | bytes) -> Any:
    return json.loads(value)


def parse_datetime(value: str) -> datetime:
    """Parse an ISO-8601 string and require a timezone."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return parsed.astimezone(UTC)


def format_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
