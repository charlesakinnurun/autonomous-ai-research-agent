"""Provider configuration tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from research_agent.config import Settings
from research_agent.llm.provider_config import (
    ProvidersConfig,
    default_providers_config,
    load_providers_config,
)

EXAMPLE = Path(__file__).resolve().parents[2] / "config" / "providers.example.yaml"


def test_load_example_config() -> None:
    config = load_providers_config(EXAMPLE)
    assert "groq" in config.providers
    assert "gemini" in config.providers
    assert config.routing.fallback_order == ["groq", "gemini", "ollama"]
    assert config.providers["groq"].limits.rpd > 0
    assert config.providers["groq"].api_key(Settings(_env_file=None, groq_api_key="k")) == "k"


def test_ollama_uses_settings_base_url() -> None:
    config = load_providers_config(EXAMPLE)
    settings = Settings(_env_file=None, ollama_base_url="http://ollama:11434/v1")
    assert config.providers["ollama"].base_url_for(settings) == "http://ollama:11434/v1"


def test_unknown_routing_reference_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ProvidersConfig.model_validate(
            {
                "routing": {"fallback_order": ["missing"]},
                "providers": {},
            }
        )


def test_unknown_role_is_rejected() -> None:
    config = load_providers_config(EXAMPLE)
    with pytest.raises(KeyError):
        config.routing.roles.for_role("nope")


def test_default_config_missing_is_clear(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        providers_config_path=tmp_path / "providers.yaml",
    )
    with pytest.raises(FileNotFoundError, match="copy"):
        default_providers_config(settings)
