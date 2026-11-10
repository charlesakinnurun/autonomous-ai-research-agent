"""Search adapter interface and shared caching/retry behavior."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import httpx

from research_agent.cache.store import CacheStore, make_cache_key
from research_agent.core.retry import RetryPolicy, retry_async
from research_agent.models.common import SearchProvider
from research_agent.models.tools import SearchRequest, SearchResponse
from research_agent.tools.url_safety import UrlPolicy, normalize_url, validate_url_sync


class SearchAdapter(ABC):
    provider: SearchProvider
    version: str = "1"

    @abstractmethod
    async def search(self, request: SearchRequest) -> SearchResponse:
        """Search the provider and return normalized, safe results."""


class CachedSearchAdapter(SearchAdapter):
    """Template: cache -> retry -> normalize/filter results."""

    def __init__(
        self,
        *,
        cache: CacheStore | None = None,
        client: httpx.AsyncClient | None = None,
        policy: UrlPolicy | None = None,
        retry_policy: RetryPolicy | None = None,
        timeout_seconds: float = 10.0,
        base_url: str = "",
        user_agent: str = "autonomous-research-agent/0.1 (local research; contact: local)",
    ) -> None:
        self.cache = cache
        self._owns_client = client is None
        self.client = client or httpx.AsyncClient(
            headers={"User-Agent": user_agent},
            timeout=timeout_seconds,
            follow_redirects=True,
        )
        self.policy = policy or UrlPolicy()
        self.search_policy = self.policy.model_copy(update={"resolve_dns": False})
        self.retry_policy = retry_policy or RetryPolicy()
        self.timeout_seconds = timeout_seconds
        self.base_url = base_url.rstrip("/")
        self.user_agent = user_agent

    async def aclose(self) -> None:
        if self._owns_client:
            await self.client.aclose()

    async def search(self, request: SearchRequest) -> SearchResponse:
        payload = request.model_dump(mode="json", exclude_none=True)
        key = make_cache_key(
            tool=f"search.{self.provider.value}",
            version=self.version,
            request=payload,
            config={"base_url": self.base_url},
        )
        if self.cache is not None and self.cache.mode == "replay":
            envelope = self.cache.get_response(tool=f"search.{self.provider.value}", key=key)
            return SearchResponse.model_validate(envelope.response).model_copy(
                update={"cached": True}
            )

        response = await retry_async(
            lambda: self._search_remote(request),
            policy=self.retry_policy,
        )
        filtered = self._safe_results(response)
        if self.cache is not None and self.cache.mode == "record":
            self.cache.put(
                tool=f"search.{self.provider.value}",
                version=self.version,
                request=payload,
                response=filtered.model_dump(mode="json"),
                provider=self.provider.value,
                latency_ms=filtered.latency_ms,
                config={"base_url": self.base_url},
            )
        return filtered

    @abstractmethod
    async def _search_remote(self, request: SearchRequest) -> SearchResponse:
        """Perform the live HTTP call and parse the provider payload."""

    def _safe_results(self, response: SearchResponse) -> SearchResponse:
        """Drop unsafe URLs and normalize/canonicalize the rest."""
        safe = []
        for result in response.results:
            try:
                validated = validate_url_sync(result.url, self.search_policy)
            except Exception:  # noqa: S112 - one unsafe result must not fail the batch
                continue
            safe.append(
                result.model_copy(
                    update={
                        "url": validated.normalized,
                        "canonical_url": normalize_url(validated.normalized),
                        "domain": validated.host,
                    }
                )
            )
        # Dedupe by canonical URL while preserving rank.
        seen: set[str] = set()
        deduped = []
        for result in safe:
            if result.canonical_url in seen:
                continue
            seen.add(result.canonical_url)
            deduped.append(result)
        return response.model_copy(update={"results": deduped})


def safe_domain(url: str, policy: UrlPolicy | None = None) -> str:
    """Validate a result URL and return its host."""
    return validate_url_sync(url, policy).host


def payload_summary(payload: dict[str, Any]) -> str:
    """Small debug string used in warnings; never includes credentials."""
    return ", ".join(f"{key}={value!r}" for key, value in sorted(payload.items()))[:500]
