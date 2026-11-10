"""SearXNG JSON search adapter.

SearXNG is self-hosted, so the request goes to a local service. Result URLs are
still untrusted and pass through SSRF/domain filtering before they reach the
researcher.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from research_agent.core.errors import ToolResponseError
from research_agent.models.common import SearchProvider, SourceKind
from research_agent.models.tools import SearchRequest, SearchResponse, SearchResult
from research_agent.tools.search.base import CachedSearchAdapter
from research_agent.tools.url_safety import domain_of, normalize_url


class SearXNGSearchAdapter(CachedSearchAdapter):
    provider = SearchProvider.SEARXNG
    version = "1"

    async def _search_remote(self, request: SearchRequest) -> SearchResponse:
        params: dict[str, Any] = {
            "q": request.query,
            "format": "json",
            "language": request.language,
            "safesearch": request.safe_search,
            "pageno": 1,
        }
        if request.engines:
            params["engines"] = ",".join(request.engines)
        if request.time_range:
            params["time_range"] = request.time_range
        if request.categories:
            params["categories"] = ",".join(request.categories)

        response = await self.client.get(
            f"{self.base_url}/search",
            params=params,
            headers={"Accept": "application/json"},
            timeout=self.timeout_seconds,
        )
        if response.status_code == 429:
            from research_agent.core.errors import ToolRateLimited

            raise ToolRateLimited("SearXNG rate limited")
        if response.status_code >= 500:
            from research_agent.core.errors import ToolServerError

            raise ToolServerError(f"SearXNG server error {response.status_code}")
        if response.status_code != 200:
            raise ToolResponseError(
                f"SearXNG returned {response.status_code}",
                details={"status": str(response.status_code)},
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise ToolResponseError("SearXNG returned invalid JSON") from exc
        raw_results = payload.get("results", [])
        if not isinstance(raw_results, list):
            raise ToolResponseError("SearXNG results field is not a list")

        results: list[SearchResult] = []
        for rank, item in enumerate(raw_results[: request.max_results]):
            if not isinstance(item, dict):
                continue
            url = item.get("url")
            if not isinstance(url, str) or not url:
                continue
            canonical = normalize_url(url)
            results.append(
                SearchResult(
                    title=str(item.get("title") or "")[:500],
                    url=url,
                    canonical_url=canonical,
                    domain=domain_of(canonical),
                    snippet=str(item.get("content") or "")[:4000],
                    provider=self.provider,
                    rank=rank,
                    score=_float_or_none(item.get("score")),
                    published_at=_parse_date(item.get("publishedDate")),
                    kind=SourceKind.WEB,
                )
            )
        return SearchResponse(
            query=request.query,
            provider=self.provider,
            results=results,
            latency_ms=0.0,
        )


def _float_or_none(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _parse_date(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
