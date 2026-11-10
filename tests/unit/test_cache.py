"""Record/replay cache tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from research_agent.cache import CacheStore, cache_key_for_model, make_cache_key
from research_agent.core.errors import CacheError, CacheMissError
from research_agent.models.tools import SearchRequest


def test_cache_key_is_stable_and_versioned() -> None:
    request = {"query": "hello", "limit": 5}
    first = make_cache_key(tool="search", version="1", request=request)
    second = make_cache_key(tool="search", version="1", request={"limit": 5, "query": "hello"})
    other = make_cache_key(tool="search", version="2", request=request)
    assert first == second
    assert first != other


def test_model_cache_key_ignores_none_fields() -> None:
    request = SearchRequest(query="hello")
    first = cache_key_for_model(tool="search", version="1", request=request)
    second = cache_key_for_model(
        tool="search",
        version="1",
        request=request.model_copy(update={"time_range": None}),
    )
    assert first == second


def test_record_then_replay_round_trip(tmp_path: Path) -> None:
    record = CacheStore(tmp_path / "cache", mode="record")
    envelope = record.put(
        tool="search.searxng",
        version="1",
        request={"query": "hello"},
        response={"results": [1, 2, 3]},
        provider="searxng",
        latency_ms=12.5,
    )
    assert envelope.key
    replay = CacheStore(tmp_path / "cache", mode="replay")
    loaded = replay.get_response(tool="search.searxng", key=envelope.key)
    assert loaded.response == {"results": [1, 2, 3]}
    assert loaded.provider == "searxng"


def test_replay_miss_fails_loudly(tmp_path: Path) -> None:
    replay = CacheStore(tmp_path / "cache", mode="replay")
    with pytest.raises(CacheMissError):
        replay.get_response(tool="search.searxng", key="0" * 64)


def test_live_mode_does_not_write(tmp_path: Path) -> None:
    live = CacheStore(tmp_path / "cache", mode="live")
    live.put(
        tool="search.searxng",
        version="1",
        request={"query": "hello"},
        response={"ok": True},
    )
    assert not any((tmp_path / "cache").rglob("*.json"))


def test_corrupt_cache_entry_is_rejected(tmp_path: Path) -> None:
    store = CacheStore(tmp_path / "cache", mode="replay")
    key = make_cache_key(tool="search", version="1", request={"q": "x"})
    path = store._path("search", key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(CacheError):
        store.get_response(tool="search", key=key)


def test_cache_identity_mismatch_is_rejected(tmp_path: Path) -> None:
    store = CacheStore(tmp_path / "cache", mode="record")
    envelope = store.put(
        tool="search",
        version="1",
        request={"q": "x"},
        response={"ok": True},
    )
    path = store._path("search", envelope.key)
    payload = envelope.model_dump(mode="json")
    payload["key"] = "1" * 64
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(CacheError):
        store.get_response(tool="search", key=envelope.key)
