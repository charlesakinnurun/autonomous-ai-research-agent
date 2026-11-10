"""Fetch service tests: redirects, byte caps, robots, and failures."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from research_agent.cache import CacheStore
from research_agent.core.errors import SecurityError, ToolRateLimited, ToolServerError
from research_agent.models.tools import FetchRequest
from research_agent.tools.fetch import FetchService, RobotsCache, RobotsPolicy
from research_agent.tools.url_safety import UrlPolicy


def _service(client: httpx.AsyncClient) -> FetchService:
    return FetchService(client=client, policy=UrlPolicy())


@pytest.mark.asyncio
@respx.mock
async def test_fetch_html(public_dns: None) -> None:
    respx.get("https://example.com/page").mock(
        return_value=httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            content=b"<html><body><p>Hello world</p></body></html>",
        )
    )
    async with httpx.AsyncClient() as client:
        service = _service(client)
        response = await service.fetch(
            FetchRequest(url="https://example.com/page", respect_robots_txt=False)
        )
        await service.aclose()
    assert response.ok
    assert response.content_type == "text/html"
    assert response.text is not None and "Hello world" in response.text
    assert response.content_hash.startswith("sha256:")


@pytest.mark.asyncio
@respx.mock
async def test_fetch_follows_and_validates_redirects(public_dns: None) -> None:
    respx.get("https://example.com/a").mock(
        return_value=httpx.Response(302, headers={"location": "/b"})
    )
    respx.get("https://example.com/b").mock(
        return_value=httpx.Response(200, headers={"content-type": "text/plain"}, content=b"done")
    )
    async with httpx.AsyncClient() as client:
        service = _service(client)
        response = await service.fetch(
            FetchRequest(url="https://example.com/a", respect_robots_txt=False)
        )
        await service.aclose()
    assert response.final_url == "https://example.com/b"
    assert response.redirect_chain == ["https://example.com/a"]


@pytest.mark.asyncio
@respx.mock
async def test_fetch_blocks_redirect_to_private_ip(public_dns: None) -> None:
    respx.get("https://example.com/a").mock(
        return_value=httpx.Response(302, headers={"location": "http://127.0.0.1/secret"})
    )
    async with httpx.AsyncClient() as client:
        service = _service(client)
        with pytest.raises(SecurityError):
            await service.fetch(FetchRequest(url="https://example.com/a", respect_robots_txt=False))
        await service.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_fetch_byte_cap(public_dns: None) -> None:
    respx.get("https://example.com/big").mock(
        return_value=httpx.Response(
            200, headers={"content-type": "text/plain"}, content=b"x" * 1000
        )
    )
    async with httpx.AsyncClient() as client:
        service = _service(client)
        response = await service.fetch(
            FetchRequest(url="https://example.com/big", max_bytes=100, respect_robots_txt=False)
        )
        await service.aclose()
    assert response.truncated is True
    assert len(response.body) == 100


@pytest.mark.asyncio
@respx.mock
async def test_fetch_429_and_500(public_dns: None) -> None:
    respx.get("https://example.com/rate").mock(
        return_value=httpx.Response(429, headers={"retry-after": "3"})
    )
    async with httpx.AsyncClient() as client:
        service = _service(client)
        with pytest.raises(ToolRateLimited) as exc_info:
            await service.fetch(
                FetchRequest(url="https://example.com/rate", respect_robots_txt=False)
            )
        assert exc_info.value.retry_after_seconds == 3.0
        await service.aclose()

    respx.get("https://example.com/error").mock(return_value=httpx.Response(503))
    async with httpx.AsyncClient() as client:
        service = _service(client)
        with pytest.raises(ToolServerError):
            await service.fetch(
                FetchRequest(url="https://example.com/error", respect_robots_txt=False)
            )
        await service.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_robots_disallow(public_dns: None) -> None:
    respx.get("https://example.com/robots.txt").mock(
        return_value=httpx.Response(200, text="User-agent: *\nDisallow: /private\n")
    )
    async with httpx.AsyncClient() as client:
        service = _service(client)
        with pytest.raises(SecurityError):
            await service.fetch(FetchRequest(url="https://example.com/private/page"))
        await service.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_robots_failure_policy(public_dns: None) -> None:
    respx.get("https://example.com/robots.txt").mock(return_value=httpx.Response(503))
    async with httpx.AsyncClient() as client:
        deny = RobotsCache(RobotsPolicy(user_agent="test", failure_policy="deny"), client=client)
        allow = RobotsCache(RobotsPolicy(user_agent="test", failure_policy="allow"), client=client)
        assert await deny.can_fetch("https://example.com/page") is False
        assert await allow.can_fetch("https://example.com/page") is True


@pytest.mark.asyncio
@respx.mock
async def test_fetch_record_replay(tmp_path: Path, public_dns: None) -> None:
    route = respx.get("https://example.com/cached").mock(
        return_value=httpx.Response(
            200, headers={"content-type": "text/plain"}, content=b"cached body"
        )
    )
    async with httpx.AsyncClient() as client:
        record = FetchService(
            client=client,
            policy=UrlPolicy(),
            cache=CacheStore(tmp_path / "cache", mode="record"),
        )
        first = await record.fetch(
            FetchRequest(url="https://example.com/cached", respect_robots_txt=False)
        )
        await record.aclose()
    assert route.called
    route.reset()
    async with httpx.AsyncClient() as client:
        replay = FetchService(
            client=client,
            policy=UrlPolicy(),
            cache=CacheStore(tmp_path / "cache", mode="replay"),
        )
        second = await replay.fetch(
            FetchRequest(url="https://example.com/cached", respect_robots_txt=False)
        )
        await replay.aclose()
    assert second.cached is True
    assert second.body == first.body
    assert second.text == "cached body"
    assert not route.called


@pytest.mark.asyncio
@respx.mock
async def test_fetch_pdf_is_binary(public_dns: None) -> None:
    respx.get("https://example.com/doc.pdf").mock(
        return_value=httpx.Response(
            200, headers={"content-type": "application/pdf"}, content=b"%PDF-1.4 fake"
        )
    )
    async with httpx.AsyncClient() as client:
        service = _service(client)
        response = await service.fetch(
            FetchRequest(url="https://example.com/doc.pdf", respect_robots_txt=False)
        )
        await service.aclose()
    assert response.text is None
    assert response.content_type == "application/pdf"
