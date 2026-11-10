"""arXiv search adapter (Atom API)."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any

from research_agent.core.errors import ToolResponseError
from research_agent.models.common import SearchProvider, SourceKind
from research_agent.models.tools import SearchRequest, SearchResponse, SearchResult
from research_agent.tools.search.base import CachedSearchAdapter
from research_agent.tools.url_safety import normalize_url

ATOM = "{http://www.w3.org/2005/Atom}"
_WS_RE = re.compile(r"\s+")


class ArxivSearchAdapter(CachedSearchAdapter):
    provider = SearchProvider.ARXIV
    version = "1"

    async def _search_remote(self, request: SearchRequest) -> SearchResponse:
        params: dict[str, Any] = {
            "search_query": f"all:{request.query}",
            "start": 0,
            "max_results": request.max_results,
            "sortBy": "relevance",
            "sortOrder": "descending",
        }
        response = await self.client.get(
            f"{self.base_url}/api/query",
            params=params,
            headers={"Accept": "application/atom+xml"},
            timeout=self.timeout_seconds,
        )
        if response.status_code == 429:
            from research_agent.core.errors import ToolRateLimited

            raise ToolRateLimited("arXiv rate limited")
        if response.status_code >= 500:
            from research_agent.core.errors import ToolServerError

            raise ToolServerError(f"arXiv server error {response.status_code}")
        if response.status_code != 200:
            raise ToolResponseError(f"arXiv returned {response.status_code}")
        if b"<!DOCTYPE" in response.content or b"<!ENTITY" in response.content:
            raise ToolResponseError("arXiv response contains a forbidden DTD/entity")

        try:
            root = ET.fromstring(response.content)  # noqa: S314 - no DTD, trusted API
        except ET.ParseError as exc:
            raise ToolResponseError("arXiv returned invalid XML") from exc

        results: list[SearchResult] = []
        for rank, entry in enumerate(root.findall(f"{ATOM}entry")):
            if rank >= request.max_results:
                break
            url = (entry.findtext(f"{ATOM}id") or "").strip()
            if not url:
                continue
            title = _clean(entry.findtext(f"{ATOM}title") or "")
            summary = _clean(entry.findtext(f"{ATOM}summary") or "")
            canonical = normalize_url(url)
            results.append(
                SearchResult(
                    title=title[:500],
                    url=url,
                    canonical_url=canonical,
                    domain="arxiv.org",
                    snippet=summary[:4000],
                    provider=self.provider,
                    rank=rank,
                    published_at=_parse_date(entry.findtext(f"{ATOM}published")),
                    kind=SourceKind.ARXIV,
                )
            )
        return SearchResponse(
            query=request.query,
            provider=self.provider,
            results=results,
        )


def _clean(value: str) -> str:
    return _WS_RE.sub(" ", value).strip()


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
