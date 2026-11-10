"""LLM client and router tests with mocked provider responses."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import respx

from research_agent.cache import CacheStore
from research_agent.config import Settings
from research_agent.core.errors import (
    ConfigurationError,
    ProviderError,
    ProviderRateLimited,
    ProviderServerError,
)
from research_agent.core.retry import RetryPolicy
from research_agent.llm.client import LLMClient
from research_agent.llm.provider_config import ProvidersConfig
from research_agent.llm.quota import InMemoryQuotaStore, QuotaTracker
from research_agent.llm.router import LLMRouter
from research_agent.models.common import QuotaLimits, Role
from research_agent.models.tools import LLMMessage, LLMRequest

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"


def _providers() -> ProvidersConfig:
    return ProvidersConfig.model_validate(
        {
            "routing": {
                "fallback_order": ["groq", "gemini"],
                "roles": {"planner": ["groq", "gemini"]},
            },
            "providers": {
                "groq": {
                    "enabled": True,
                    "base_url": "https://api.groq.com/openai/v1",
                    "api_key_env": "GROQ_API_KEY",
                    "models": {"default": "llama-default", "fast": "llama-fast"},
                    "capabilities": {"json_mode": True, "tools": False, "streaming": True},
                    "limits": {"rpm": 0, "rpd": 0, "tpm": 0, "tpd": 0},
                },
                "gemini": {
                    "enabled": True,
                    "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
                    "api_key_env": "GEMINI_API_KEY",
                    "models": {"default": "gemini-default", "fast": "gemini-fast"},
                    "capabilities": {"json_mode": True, "tools": False, "streaming": True},
                    "limits": {"rpm": 0, "rpd": 0, "tpm": 0, "tpd": 0},
                },
            },
        }
    )


def _request() -> LLMRequest:
    return LLMRequest(
        model="fast",
        messages=[
            LLMMessage(role=Role.SYSTEM, content="Be brief."),
            LLMMessage(role=Role.USER, content="Hello"),
        ],
        max_tokens=16,
    )


def _response(model: str = "llama-fast", content: str = "hi") -> dict[str, object]:
    return {
        "model": model,
        "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 2},
    }


@pytest.mark.asyncio
@respx.mock
async def test_llm_client_alias_and_usage() -> None:
    respx.post(GROQ_URL).mock(return_value=httpx.Response(200, json=_response()))
    settings = Settings(_env_file=None, groq_api_key="test-key")
    client = LLMClient(
        provider_name="groq",
        config=_providers().providers["groq"],
        settings=settings,
    )
    response = await client.chat(_request())
    await client.aclose()
    assert response.content == "hi"
    assert response.model == "llama-fast"
    assert response.usage.input_tokens == 10
    assert response.usage.output_tokens == 2
    assert response.cached is False


@pytest.mark.asyncio
@respx.mock
async def test_llm_client_json_mode_and_cache(tmp_path: Path) -> None:
    route = respx.post(GROQ_URL).mock(return_value=httpx.Response(200, json=_response()))
    settings = Settings(_env_file=None, groq_api_key="test-key")
    request = _request().model_copy(update={"response_format": "json_object"})
    client = LLMClient(
        provider_name="groq",
        config=_providers().providers["groq"],
        settings=settings,
        cache=CacheStore(tmp_path / "cache", mode="record"),
    )
    first = await client.chat(request)
    await client.aclose()
    assert route.called
    route.reset()
    replay = LLMClient(
        provider_name="groq",
        config=_providers().providers["groq"],
        settings=settings,
        cache=CacheStore(tmp_path / "cache", mode="replay"),
    )
    second = await replay.chat(request)
    await replay.aclose()
    assert second.cached is True
    assert second.content == first.content
    assert not route.called


@pytest.mark.asyncio
@respx.mock
async def test_llm_client_errors() -> None:
    respx.post(GROQ_URL).mock(return_value=httpx.Response(429, headers={"retry-after": "2"}))
    settings = Settings(_env_file=None, groq_api_key="test-key")
    retry = RetryPolicy(max_attempts=1)
    client = LLMClient(
        provider_name="groq",
        config=_providers().providers["groq"],
        settings=settings,
        retry_policy=retry,
    )
    with pytest.raises(ProviderRateLimited):
        await client.chat(_request())
    await client.aclose()

    respx.post(GROQ_URL).mock(return_value=httpx.Response(500))
    client = LLMClient(
        provider_name="groq",
        config=_providers().providers["groq"],
        settings=settings,
        retry_policy=retry,
    )
    with pytest.raises(ProviderServerError):
        await client.chat(_request())
    await client.aclose()

    respx.post(GROQ_URL).mock(return_value=httpx.Response(401))
    client = LLMClient(
        provider_name="groq",
        config=_providers().providers["groq"],
        settings=settings,
        retry_policy=retry,
    )
    with pytest.raises(ProviderError):
        await client.chat(_request())
    await client.aclose()


@pytest.mark.asyncio
async def test_missing_key_and_unsupported_json_mode() -> None:
    settings = Settings(_env_file=None, groq_api_key=None)
    client = LLMClient(
        provider_name="groq",
        config=_providers().providers["groq"],
        settings=settings,
    )
    with pytest.raises(ProviderError):
        await client.chat(_request())
    await client.aclose()

    config = (
        _providers()
        .providers["groq"]
        .model_copy(
            update={
                "capabilities": _providers()
                .providers["groq"]
                .capabilities.model_copy(update={"json_mode": False})
            }
        )
    )
    client = LLMClient(
        provider_name="groq", config=config, settings=Settings(_env_file=None, groq_api_key="k")
    )
    with pytest.raises(ConfigurationError):
        await client.chat(_request().model_copy(update={"response_format": "json_object"}))
    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_quota_is_committed() -> None:
    respx.post(GROQ_URL).mock(return_value=httpx.Response(200, json=_response()))
    settings = Settings(_env_file=None, groq_api_key="test-key")
    tracker = QuotaTracker(InMemoryQuotaStore(), {"groq": QuotaLimits(rpd=10)})
    client = LLMClient(
        provider_name="groq",
        config=_providers().providers["groq"],
        settings=settings,
        quota=tracker,
    )
    await client.chat(_request())
    await client.aclose()
    usage = await tracker.store.get_usage("groq", "llama-fast", datetime.now(UTC).date())
    assert usage.requests == 1


@pytest.mark.asyncio
@respx.mock
async def test_router_falls_back() -> None:
    respx.post(GROQ_URL).mock(return_value=httpx.Response(500))
    respx.post(GEMINI_URL).mock(
        return_value=httpx.Response(200, json=_response("gemini-fast", "fallback"))
    )
    config = _providers()
    settings = Settings(_env_file=None, groq_api_key="g", gemini_api_key="m")
    retry = RetryPolicy(max_attempts=1)
    groq = LLMClient(
        provider_name="groq",
        config=config.providers["groq"],
        settings=settings,
        retry_policy=retry,
    )
    gemini = LLMClient(
        provider_name="gemini",
        config=config.providers["gemini"],
        settings=settings,
        retry_policy=retry,
    )
    router = LLMRouter(config=config, settings=settings, clients={"groq": groq, "gemini": gemini})
    response = await router.chat(_request(), role="planner")
    await router.aclose()
    assert response.provider == "gemini"
    assert response.content == "fallback"
