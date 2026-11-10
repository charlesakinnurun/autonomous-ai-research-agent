"""OpenAI-compatible chat client with cache, retries, and quota accounting.

We use raw httpx rather than a provider SDK so every provider (Groq, Gemini,
OpenRouter, Cerebras, Mistral, Ollama) shares one request shape and one cache.
"""

from __future__ import annotations

import time
from typing import Any
from uuid import UUID, uuid4

import httpx

from research_agent.cache.store import CacheStore, make_cache_key
from research_agent.config import Settings
from research_agent.core.errors import (
    ConfigurationError,
    ProviderError,
    ProviderRateLimited,
    ProviderServerError,
    ToolTimeout,
)
from research_agent.core.retry import RetryPolicy, retry_async
from research_agent.core.tokens import count_tokens
from research_agent.llm.provider_config import ProviderConfig
from research_agent.llm.quota import QuotaTracker
from research_agent.models.common import FinishReason, TokenUsage
from research_agent.models.tools import LLMRequest, LLMResponse

LLM_CLIENT_VERSION = "1"


class LLMClient:
    def __init__(
        self,
        *,
        provider_name: str,
        config: ProviderConfig,
        settings: Settings,
        cache: CacheStore | None = None,
        quota: QuotaTracker | None = None,
        client: httpx.AsyncClient | None = None,
        retry_policy: RetryPolicy | None = None,
        timeout_seconds: float = 90.0,
    ) -> None:
        self.provider_name = provider_name
        self.config = config
        self.settings = settings
        self.cache = cache
        self.quota = quota
        self.base_url = config.base_url_for(settings).rstrip("/")
        self.api_key = config.api_key(settings)
        self.retry_policy = retry_policy or RetryPolicy()
        self.timeout_seconds = timeout_seconds
        self._owns_client = client is None
        self.client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds),
            follow_redirects=False,
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self.client.aclose()

    async def chat(self, request: LLMRequest, *, run_id: UUID | None = None) -> LLMResponse:
        resolved_model = self._resolve_model(request.model)
        if request.response_format == "json_object" and not self.config.capabilities.json_mode:
            raise ConfigurationError(f"provider {self.provider_name} does not support JSON mode")
        payload = self._payload(request, resolved_model)
        cache_key = make_cache_key(
            tool="llm",
            version=LLM_CLIENT_VERSION,
            request=payload,
            config={"provider": self.provider_name, "base_url": self.base_url},
        )
        if self.cache is not None and self.cache.mode == "replay":
            envelope = self.cache.get_response(tool="llm", key=cache_key)
            cached = LLMResponse.model_validate(envelope.response)
            return cached.model_copy(update={"cached": True})

        reservation = None
        estimated_tokens = sum(count_tokens(message.content) for message in request.messages)
        estimated_tokens += request.max_tokens
        if self.quota is not None:
            reservation = await self.quota.reserve(
                provider=self.provider_name,
                model=resolved_model,
                estimated_tokens=estimated_tokens,
                run_id=run_id,
            )

        started = time.perf_counter()
        try:
            response = await retry_async(
                lambda: self._post(payload),
                policy=self.retry_policy,
            )
            parsed = self._parse_response(response, resolved_model)
            latency_ms = (time.perf_counter() - started) * 1000
            parsed = parsed.model_copy(update={"latency_ms": latency_ms})
        except BaseException:
            if reservation is not None and self.quota is not None:
                await self.quota.release(reservation.id)
            raise

        if reservation is not None and self.quota is not None:
            await self.quota.commit(reservation.id, parsed.usage)

        if self.cache is not None and self.cache.mode == "record":
            self.cache.put(
                tool="llm",
                version=LLM_CLIENT_VERSION,
                request=payload,
                response=parsed.model_dump(mode="json"),
                provider=self.provider_name,
                model=resolved_model,
                latency_ms=parsed.latency_ms,
                usage=parsed.usage,
                config={"provider": self.provider_name, "base_url": self.base_url},
            )
        return parsed

    def _resolve_model(self, requested: str) -> str:
        if requested == "default":
            return self.config.models.default
        if requested == "fast":
            return self.config.models.fast
        return requested

    def _payload(self, request: LLMRequest, model: str) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": message.role.value, "content": message.content}
                | ({"name": message.name} if message.name else {})
                for message in request.messages
            ],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if request.response_format == "json_object":
            payload["response_format"] = {"type": "json_object"}
        if request.seed is not None:
            payload["seed"] = request.seed
        if request.stop:
            payload["stop"] = request.stop
        return payload

    async def _post(self, payload: dict[str, Any]) -> httpx.Response:
        if not self.api_key and self.config.api_key_env != "OLLAMA_API_KEY":
            raise ProviderError(
                f"missing API key for provider {self.provider_name}",
                retryable=False,
                details={"env": self.config.api_key_env},
            )
        headers = {
            "Authorization": f"Bearer {self.api_key or 'ollama'}",
            "Content-Type": "application/json",
        }
        try:
            response = await self.client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers,
                timeout=self.timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise ToolTimeout(f"provider {self.provider_name} timed out") from exc
        except httpx.HTTPError as exc:
            raise ProviderError(
                f"provider {self.provider_name} connection failed",
                retryable=True,
                details={"error": type(exc).__name__},
            ) from exc

        if response.status_code == 429:
            raise ProviderRateLimited(
                f"provider {self.provider_name} rate limited",
                retry_after_seconds=_retry_after(response.headers.get("retry-after")),
            )
        if response.status_code >= 500:
            raise ProviderServerError(f"provider {self.provider_name} server error")
        if response.status_code in {401, 403}:
            raise ProviderError(
                f"provider {self.provider_name} rejected credentials",
                details={"status": str(response.status_code)},
            )
        if response.status_code >= 400:
            raise ProviderError(
                f"provider {self.provider_name} rejected request",
                details={"status": str(response.status_code)},
            )
        return response

    def _parse_response(self, response: httpx.Response, model: str) -> LLMResponse:
        try:
            payload = response.json()
            choice = payload["choices"][0]
            message = choice["message"]
            content = message.get("content")
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderError(f"provider {self.provider_name} returned malformed JSON") from exc
        if not isinstance(content, str):
            raise ProviderError(f"provider {self.provider_name} returned no text content")
        usage_payload = payload.get("usage") or {}
        usage = TokenUsage(
            input_tokens=int(usage_payload.get("prompt_tokens") or 0),
            output_tokens=int(usage_payload.get("completion_tokens") or 0),
            requests=1,
        )
        return LLMResponse(
            model=str(payload.get("model") or model),
            provider=self.provider_name,
            content=content,
            usage=usage,
            finish_reason=_finish_reason(choice.get("finish_reason")),
            request_id=uuid4(),
            latency_ms=0.0,
        )


def _finish_reason(value: object) -> FinishReason:
    mapping = {
        "stop": FinishReason.STOP,
        "length": FinishReason.LENGTH,
        "content_filter": FinishReason.CONTENT_FILTER,
        "tool_calls": FinishReason.TOOL_CALLS,
        "error": FinishReason.ERROR,
    }
    return mapping.get(str(value), FinishReason.UNKNOWN)


def _retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None
