"""Unit tests for configuration loading and validation."""

import pytest

from research_agent.config import Settings, get_settings


def test_defaults_when_env_is_clean(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("LLM_MODE", raising=False)
    monkeypatch.delenv("MAX_TOTAL_TOKENS", raising=False)
    settings = Settings(_env_file=None)

    assert settings.app_env == "local"
    assert settings.llm_mode == "replay"
    assert settings.max_total_tokens == 100_000
    assert settings.max_cost_usd == 0.0
    assert settings.searxng_url == "http://localhost:8080"


def test_env_overrides_are_typed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("MAX_TOTAL_TOKENS", "250000")
    monkeypatch.setenv("SEARXNG_URL", "http://searxng:8080")

    settings = Settings(_env_file=None)

    assert settings.app_env == "test"
    assert settings.llm_mode == "live"
    assert settings.max_total_tokens == 250_000
    assert settings.searxng_url == "http://searxng:8080"


def test_zero_token_budget_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAX_TOTAL_TOKENS", "0")

    with pytest.raises(ValueError, match="greater than 0"):
        Settings(_env_file=None)


def test_auth_token_is_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_AUTH_TOKEN", "local-test-token")

    settings = Settings(_env_file=None)

    assert settings.api_auth_token.get_secret_value() == "local-test-token"
    assert "local-test-token" not in repr(settings)


def test_get_settings_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "staging")
    get_settings.cache_clear()

    first = get_settings()
    second = get_settings()

    assert first is second
    assert first.app_env == "staging"
    get_settings.cache_clear()
