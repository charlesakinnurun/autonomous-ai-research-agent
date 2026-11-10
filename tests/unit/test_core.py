"""Tests for core utilities: IDs, errors, retry, tokens, runtime, logging."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from research_agent.config import Settings
from research_agent.core import errors
from research_agent.core.config import Settings as CoreSettings
from research_agent.core.config import load_yaml as core_load_yaml
from research_agent.core.ids import (
    canonical_json_text,
    content_hash,
    content_hash_bytes,
    format_datetime,
    parse_datetime,
    stable_hash,
    trace_id_for,
    utc_now,
)
from research_agent.core.logging import (
    bind_run_context,
    clear_context,
    configure_logging,
    get_logger,
)
from research_agent.core.retry import RetryPolicy, retry_async
from research_agent.core.runtime import configure_windows_event_loop, load_yaml
from research_agent.core.tokens import count_tokens, truncate_to_tokens


def test_content_hash_and_canonical_json_are_stable() -> None:
    assert content_hash("hello") == content_hash("hello")
    assert content_hash("hello") != content_hash("world")
    assert content_hash_bytes(b"hello") == content_hash("hello")
    assert canonical_json_text({"b": 1, "a": 2}) == '{"a":2,"b":1}'
    assert stable_hash({"a": 1, "b": 2}) == stable_hash({"b": 2, "a": 1})


def test_datetime_helpers_require_timezone() -> None:
    now = utc_now()
    assert now.tzinfo is not None
    assert parse_datetime("2024-01-02T03:04:05Z") == datetime(2024, 1, 2, 3, 4, 5, tzinfo=UTC)
    assert format_datetime(datetime(2024, 1, 2, 3, 4, 5, tzinfo=UTC)) == "2024-01-02T03:04:05Z"
    with pytest.raises(ValueError):
        format_datetime(datetime(2024, 1, 2))
    with pytest.raises(ValueError):
        parse_datetime("2024-01-02T03:04:05")


def test_trace_id_is_derived_from_run_id() -> None:
    from uuid import uuid4

    run_id = uuid4()
    assert trace_id_for(run_id) == f"trace-{run_id.hex}"


def test_error_hierarchy_serializes() -> None:
    error = errors.ProviderRateLimited("slow down", retry_after_seconds=2.5)
    payload = error.to_dict()
    assert payload["code"] == "provider_rate_limited"
    assert payload["retryable"] is True
    assert payload["message"] == "slow down"
    assert error.retry_after_seconds == 2.5
    assert errors.CacheMissError("missing").code == "cache_miss"


@pytest.mark.asyncio
async def test_retry_async_retries_only_retryable_errors() -> None:
    attempts = 0

    async def flaky() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise errors.ToolTimeout("timeout")
        return "ok"

    result = await retry_async(flaky, policy=RetryPolicy(max_attempts=3, base_delay_seconds=0.0))
    assert result == "ok"
    assert attempts == 3

    attempts = 0

    async def fatal() -> str:
        nonlocal attempts
        attempts += 1
        raise errors.ToolResponseError("bad response")

    with pytest.raises(errors.ToolResponseError):
        await retry_async(fatal, policy=RetryPolicy(max_attempts=5, base_delay_seconds=0.0))
    assert attempts == 1


def test_retry_policy_bounds_delay() -> None:
    policy = RetryPolicy(base_delay_seconds=1.0, max_delay_seconds=5.0, jitter=0.0)
    assert policy.delay_for(1) == 1.0
    assert policy.delay_for(10) == 5.0
    assert policy.delay_for(1, retry_after=99.0) == 5.0


def test_token_counting_and_truncation() -> None:
    text = "The quick brown fox jumps over the lazy dog. " * 20
    count = count_tokens(text)
    assert count > 10
    truncated = truncate_to_tokens(text, 10)
    assert count_tokens(truncated) <= 10
    assert truncate_to_tokens(text, 0) == ""
    assert count_tokens("") == 0


def test_load_yaml_and_missing_file(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("a: 1\nb: [2, 3]\n", encoding="utf-8")
    assert load_yaml(path) == {"a": 1, "b": [2, 3]}
    with pytest.raises(FileNotFoundError):
        load_yaml(tmp_path / "missing.yaml")
    path.write_text("- not\n- a\n- mapping\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_yaml(path)
    path.write_text("", encoding="utf-8")
    assert load_yaml(path) == {}


def test_core_config_reexports_the_canonical_settings() -> None:
    assert CoreSettings is Settings
    assert core_load_yaml is load_yaml


def test_logging_helpers_do_not_raise() -> None:
    configure_windows_event_loop()
    configure_logging("DEBUG", json_logs=False)
    bind_run_context(run_id="r1", trace_id="t1")
    logger = get_logger("test")
    logger.info("hello")
    clear_context()
