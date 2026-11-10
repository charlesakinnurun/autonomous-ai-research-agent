"""Search adapter tests with mocked HTTP."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from research_agent.cache import CacheStore
from research_agent.core.errors import ToolRateLimited, ToolResponseError, ToolServerError
from research_agent.core.retry import RetryPolicy
from research_agent.models.tools import SearchRequest
from research_agent.tools.search import (
    ArxivSearchAdapter,
    SearXNGSearchAdapter,
    WikipediaSearchAdapter,
)
from research_agent.tools.url_safety import UrlPolicy


def _policy() -> UrlPolicy:
    return UrlPolicy(resolve_dns=False)


def _searxng_payload() -> dict[str, object]:
    return {
        "results": [
            {
                "title": "Example result",
                "url": "https://example.com/article?utm_source=x",
                "content": "A useful snippet.",
                "engine": "duckduckgo",
                "score": 1.5,
            },
            {
                "title": "Unsafe result",
                "url": "http://127.0.0.1/admin",
                "content": "should be dropped",
            },
        ]
    }


@pytest.mark.asyncio
@respx.mock
async def test_searxng_search_and_filter() -> None:
    respx.get("http://searx.test/search").mock(
        return_value=httpx.Response(200, json=_searxng_payload())
    )
    async with httpx.AsyncClient() as client:
        adapter = SearXNGSearchAdapter(
            client=client,
            base_url="http://searx.test",
            policy=_policy(),
        )
        response = await adapter.search(SearchRequest(query="example", max_results=5))
        await adapter.aclose()
    assert response.provider.value == "searxng"
    assert len(response.results) == 1
    assert response.results[0].canonical_url == "https://example.com/article"


@pytest.mark.asyncio
@respx.mock
async def test_searxng_record_replay(tmp_path: Path) -> None:
    route = respx.get("http://searx.test/search").mock(
        return_value=httpx.Response(200, json=_searxng_payload())
    )
    async with httpx.AsyncClient() as client:
        record = SearXNGSearchAdapter(
            client=client,
            cache=CacheStore(tmp_path / "cache", mode="record"),
            base_url="http://searx.test",
            policy=_policy(),
        )
        first = await record.search(SearchRequest(query="example"))
        await record.aclose()
    assert route.called
    route.reset()
    async with httpx.AsyncClient() as client:
        replay = SearXNGSearchAdapter(
            client=client,
            cache=CacheStore(tmp_path / "cache", mode="replay"),
            base_url="http://searx.test",
            policy=_policy(),
        )
        second = await replay.search(SearchRequest(query="example"))
        await replay.aclose()
    assert second.cached is True
    assert second.results[0].url == first.results[0].url
    assert not route.called


@pytest.mark.asyncio
@respx.mock
async def test_searxng_errors_are_typed() -> None:
    respx.get("http://searx.test/search").mock(return_value=httpx.Response(429))
    async with httpx.AsyncClient() as client:
        adapter = SearXNGSearchAdapter(
            client=client,
            base_url="http://searx.test",
            policy=_policy(),
            retry_policy=RetryPolicy(max_attempts=1),
        )
        with pytest.raises(ToolRateLimited):
            await adapter.search(SearchRequest(query="example"))
        await adapter.aclose()

    respx.get("http://searx.test/search").mock(return_value=httpx.Response(500))
    async with httpx.AsyncClient() as client:
        adapter = SearXNGSearchAdapter(
            client=client,
            base_url="http://searx.test",
            policy=_policy(),
            retry_policy=RetryPolicy(max_attempts=1),
        )
        with pytest.raises(ToolServerError):
            await adapter.search(SearchRequest(query="example"))
        await adapter.aclose()

    respx.get("http://searx.test/search").mock(
        return_value=httpx.Response(200, content=b"not-json")
    )
    async with httpx.AsyncClient() as client:
        adapter = SearXNGSearchAdapter(
            client=client,
            base_url="http://searx.test",
            policy=_policy(),
            retry_policy=RetryPolicy(max_attempts=1),
        )
        with pytest.raises(ToolResponseError):
            await adapter.search(SearchRequest(query="example"))
        await adapter.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_wikipedia_search() -> None:
    payload = {
        "query": {
            "search": [{"title": "Example article", "snippet": "<span>Useful</span> snippet"}]
        }
    }
    respx.get("https://en.wikipedia.org/w/api.php").mock(
        return_value=httpx.Response(200, json=payload)
    )
    async with httpx.AsyncClient() as client:
        adapter = WikipediaSearchAdapter(
            client=client,
            base_url="https://en.wikipedia.org",
            policy=_policy(),
        )
        response = await adapter.search(SearchRequest(query="example"))
        await adapter.aclose()
    assert len(response.results) == 1
    assert response.results[0].title == "Example article"
    assert response.results[0].snippet == "Useful snippet"
    assert response.results[0].canonical_url.startswith("https://en.wikipedia.org/wiki/")


@pytest.mark.asyncio
@respx.mock
async def test_arxiv_search() -> None:
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <id>https://arxiv.org/abs/2401.00001</id>
        <title>A   Useful Paper</title>
        <summary>An abstract with
        useful content.</summary>
        <published>2024-01-02T03:04:05Z</published>
      </entry>
    </feed>"""
    respx.get("https://export.arxiv.org/api/query").mock(
        return_value=httpx.Response(200, content=xml.encode())
    )
    async with httpx.AsyncClient() as client:
        adapter = ArxivSearchAdapter(
            client=client,
            base_url="https://export.arxiv.org",
            policy=_policy(),
        )
        response = await adapter.search(SearchRequest(query="example"))
        await adapter.aclose()
    assert len(response.results) == 1
    assert response.results[0].title == "A Useful Paper"
    assert response.results[0].domain == "arxiv.org"
    assert response.results[0].published_at is not None
