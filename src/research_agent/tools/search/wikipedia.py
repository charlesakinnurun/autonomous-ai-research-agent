"""Wikipedia search adapter (MediaWiki API)."""

from __future__ import annotations

import html
import re
from typing import Any
from urllib.parse import quote

from research_agent.core.errors import ToolResponseError
from research_agent.models.common import SearchProvider, SourceKind
from research_agent.models.tools import SearchRequest, SearchResponse, SearchResult
from research_agent.tools.search.base import CachedSearchAdapter
from research_agent.tools.url_safety import domain_of, normalize_url

_TAG_RE = re.compile(r"<[^>]+>")


class WikipediaSearchAdapter(CachedSearchAdapter):
    provider = SearchProvider.WIKIPEDIA
    version = "1"

    async def _search_remote(self, request: SearchRequest) -> SearchResponse:
        params: dict[str, Any] = {
            "action": "query",
            "list": "search",
            "srsearch": request.query,
            "format": "json",
            "utf8": 1,
            "srlimit": request.max_results,
            "srprop": "snippet",
        }
        response = await self.client.get(
            f"{self.base_url}/w/api.php",
            params=params,
            headers={"Accept": "application/json"},
            timeout=self.timeout_seconds,
        )
        if response.status_code == 429:
            from research_agent.core.errors import ToolRateLimited

            raise ToolRateLimited("Wikipedia rate limited")
        if response.status_code >= 500:
            from research_agent.core.errors import ToolServerError

            raise ToolServerError(f"Wikipedia server error {response.status_code}")
        if response.status_code != 200:
            raise ToolResponseError(f"Wikipedia returned {response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise ToolResponseError("Wikipedia returned invalid JSON") from exc
        rows = payload.get("query", {}).get("search", [])
        if not isinstance(rows, list):
            raise ToolResponseError("Wikipedia search payload is malformed")

        results: list[SearchResult] = []
        for rank, item in enumerate(rows[: request.max_results]):
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            if not title:
                continue
            url = f"https://en.wikipedia.org/wiki/{quote(title.replace(' ', '_'), safe='()_,-')}"
            canonical = normalize_url(url)
            snippet = html.unescape(_TAG_RE.sub("", str(item.get("snippet") or ""))).strip()
            results.append(
                SearchResult(
                    title=title,
                    url=url,
                    canonical_url=canonical,
                    domain=domain_of(canonical),
                    snippet=snippet,
                    provider=self.provider,
                    rank=rank,
                    kind=SourceKind.WIKIPEDIA,
                )
            )
        return SearchResponse(
            query=request.query,
            provider=self.provider,
            results=results,
        )
