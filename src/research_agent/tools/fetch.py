"""HTTP fetch with SSRF/robots protection, redirect validation, byte caps, and cache."""

from __future__ import annotations

import asyncio
import base64
import time
import urllib.robotparser
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit

import httpx

from research_agent.cache.store import CacheStore, make_cache_key
from research_agent.core.errors import (
    SecurityError,
    ToolRateLimited,
    ToolResponseError,
    ToolServerError,
)
from research_agent.core.ids import content_hash_bytes
from research_agent.models.tools import FetchRequest, FetchResponse
from research_agent.tools.url_safety import UrlPolicy, validate_redirect, validate_url

TEXTUAL_TYPES = {
    "text/html",
    "application/xhtml+xml",
    "text/plain",
    "text/markdown",
    "application/json",
    "application/xml",
    "text/xml",
}
DEFAULT_CONTENT_TYPES = {
    "text/html",
    "application/xhtml+xml",
    "text/plain",
    "application/pdf",
}
FETCH_CACHE_VERSION = "1"


def build_client(
    *,
    user_agent: str,
    timeout_seconds: float = 30.0,
    max_connections: int = 10,
) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        headers={"User-Agent": user_agent, "Accept": "*/*"},
        timeout=httpx.Timeout(timeout_seconds, connect=min(10.0, timeout_seconds)),
        limits=httpx.Limits(
            max_connections=max_connections, max_keepalive_connections=max_connections
        ),
        follow_redirects=False,
        trust_env=True,
    )


@dataclass(frozen=True, slots=True)
class RobotsPolicy:
    user_agent: str
    timeout_seconds: float = 5.0
    max_bytes: int = 512_000
    cache_ttl_seconds: float = 3600.0
    failure_policy: Literal["allow", "deny"] = "deny"


class RobotsCache:
    """Per-process robots.txt cache with an explicit failure policy."""

    def __init__(self, policy: RobotsPolicy, client: httpx.AsyncClient | None = None) -> None:
        self.policy = policy
        self._client = client
        self._cache: dict[str, tuple[float, urllib.robotparser.RobotFileParser | bool]] = {}

    def _origin(self, url: str) -> str:
        parts = urlsplit(url)
        port = parts.port
        netloc = parts.hostname or ""
        if port is not None and port not in {80, 443}:
            netloc = f"{netloc}:{port}"
        return urlunsplit((parts.scheme, netloc, "", "", ""))

    async def _load(self, origin: str) -> urllib.robotparser.RobotFileParser | bool:
        robots_url = f"{origin}/robots.txt"
        owns_client = self._client is None
        client = self._client or build_client(
            user_agent=self.policy.user_agent,
            timeout_seconds=self.policy.timeout_seconds,
        )
        try:
            response = await client.get(
                robots_url,
                headers={"User-Agent": self.policy.user_agent, "Accept": "text/plain"},
                timeout=self.policy.timeout_seconds,
            )
        except httpx.HTTPError:
            return self.policy.failure_policy == "allow"
        finally:
            if owns_client:
                await client.aclose()

        if response.status_code in {401, 403}:
            return False
        if response.status_code == 404 or response.status_code == 410:
            return True
        if response.status_code >= 500:
            return self.policy.failure_policy == "allow"
        if response.status_code != 200:
            return self.policy.failure_policy == "allow"

        body = response.content[: self.policy.max_bytes]
        parser = urllib.robotparser.RobotFileParser()
        parser.set_url(robots_url)
        parser.parse(body.decode("utf-8", errors="replace").splitlines())
        return parser

    async def can_fetch(self, url: str) -> bool:
        origin = self._origin(url)
        now = time.monotonic()
        cached = self._cache.get(origin)
        if cached is not None and cached[0] > now:
            entry = cached[1]
        else:
            entry = await self._load(origin)
            self._cache[origin] = (now + self.policy.cache_ttl_seconds, entry)
        if isinstance(entry, bool):
            return entry
        return entry.can_fetch(self.policy.user_agent, url)


class FetchService:
    """Fetch a public URL with a hard byte cap, per-hop SSRF checks, and cache."""

    def __init__(
        self,
        *,
        policy: UrlPolicy | None = None,
        client: httpx.AsyncClient | None = None,
        robots: RobotsCache | None = None,
        cache: CacheStore | None = None,
        user_agent: str = "autonomous-research-agent/0.1 (local research; contact: local)",
        max_redirects: int = 5,
    ) -> None:
        self.policy = policy or UrlPolicy()
        self._owns_client = client is None
        self.client = client or build_client(user_agent=user_agent)
        self.robots = robots or RobotsCache(RobotsPolicy(user_agent=user_agent), client=client)
        self.cache = cache
        self.user_agent = user_agent
        self.max_redirects = max_redirects

    async def aclose(self) -> None:
        if self._owns_client:
            await self.client.aclose()

    async def __aenter__(self) -> FetchService:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def fetch(self, request: FetchRequest) -> FetchResponse:
        request_payload = request.model_dump(mode="json", exclude_none=True)
        # Never persist arbitrary headers in a cache envelope; only the headers
        # that legitimately vary representation are part of the key.
        request_payload["headers"] = {
            key: value
            for key, value in request.headers.items()
            if key.lower() in {"accept", "accept-language"}
        }
        cache_key = make_cache_key(
            tool="fetch",
            version=FETCH_CACHE_VERSION,
            request=request_payload,
            config={"user_agent": self.user_agent, "max_redirects": self.max_redirects},
        )
        if self.cache is not None and self.cache.mode == "replay":
            envelope = self.cache.get_response(tool="fetch", key=cache_key)
            return _from_cache_dict(envelope.response)

        started = time.perf_counter()
        response = await self._fetch_live(request)
        latency_ms = (time.perf_counter() - started) * 1000
        response = response.model_copy(update={"latency_ms": latency_ms})
        if self.cache is not None and self.cache.mode == "record":
            self.cache.put(
                tool="fetch",
                version=FETCH_CACHE_VERSION,
                request=request_payload,
                response=_to_cache_dict(response),
                provider="http",
                latency_ms=latency_ms,
                content_hash=response.content_hash,
                config={"user_agent": self.user_agent, "max_redirects": self.max_redirects},
            )
        return response

    async def _fetch_live(self, request: FetchRequest) -> FetchResponse:
        current = request.url
        redirect_chain: list[str] = []
        headers = {"User-Agent": request.user_agent or self.user_agent, **request.headers}
        allowed_types = set(request.allowed_content_types or DEFAULT_CONTENT_TYPES)
        max_redirects = self.max_redirects

        for _hop in range(max_redirects + 1):
            validated = await validate_url(current, self.policy)
            fetch_url = validated.original
            if request.respect_robots_txt and not await self.robots.can_fetch(fetch_url):
                raise SecurityError(
                    f"robots.txt disallows fetch: {fetch_url}",
                    details={"url": fetch_url},
                )

            try:
                async with self.client.stream(
                    "GET",
                    fetch_url,
                    headers=headers,
                    timeout=request.timeout_seconds,
                ) as response:
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            raise ToolResponseError("redirect without Location header")
                        redirect_chain.append(fetch_url)
                        current = await asyncio.to_thread(
                            validate_redirect, fetch_url, location, self.policy
                        )
                        continue

                    if response.status_code == 429:
                        retry_after = _retry_after_seconds(response.headers.get("retry-after"))
                        raise ToolRateLimited(
                            "fetch rate limited",
                            retry_after_seconds=retry_after,
                            details={"url": fetch_url},
                        )
                    if response.status_code >= 500:
                        raise ToolServerError(
                            f"fetch server error {response.status_code}",
                            details={"url": fetch_url},
                        )

                    content_type = (
                        response.headers.get("content-type", "").split(";")[0].strip().lower()
                    )
                    body, truncated = await _read_limited(response, request.max_bytes)
                    if allowed_types and content_type and content_type not in allowed_types:
                        body = b""
                        truncated = False
                    text = (
                        _decode_text(body, response.encoding)
                        if content_type in TEXTUAL_TYPES
                        else None
                    )
                    return FetchResponse(
                        url=request.url,
                        final_url=fetch_url,
                        status_code=response.status_code,
                        content_type=content_type,
                        headers={key.lower(): value for key, value in response.headers.items()},
                        body=body,
                        text=text,
                        content_hash=content_hash_bytes(body),
                        truncated=truncated,
                        redirect_chain=redirect_chain,
                    )
            except httpx.TimeoutException as exc:
                from research_agent.core.errors import ToolTimeout

                raise ToolTimeout(f"fetch timed out: {fetch_url}") from exc
            except httpx.HTTPError as exc:
                from research_agent.core.errors import ToolError

                raise ToolError(
                    f"fetch failed: {fetch_url}",
                    retryable=True,
                    details={"error": type(exc).__name__},
                ) from exc

        raise ToolResponseError(
            "too many redirects",
            details={"url": request.url, "max_redirects": str(max_redirects)},
        )


async def _read_limited(response: httpx.Response, max_bytes: int) -> tuple[bytes, bool]:
    chunks: list[bytes] = []
    total = 0
    truncated = False
    async for chunk in response.aiter_bytes():
        if total + len(chunk) > max_bytes:
            remaining = max_bytes - total
            if remaining > 0:
                chunks.append(chunk[:remaining])
            truncated = True
            break
        chunks.append(chunk)
        total += len(chunk)
    return b"".join(chunks), truncated


def _decode_text(body: bytes, encoding: str | None) -> str:
    for candidate in (encoding, "utf-8", "latin-1"):
        if not candidate:
            continue
        try:
            return body.decode(candidate)
        except (LookupError, UnicodeDecodeError):
            continue
    return body.decode("utf-8", errors="replace")


def _retry_after_seconds(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


def _to_cache_dict(response: FetchResponse) -> dict[str, Any]:
    payload = response.model_dump(mode="json")
    payload["body_b64"] = base64.b64encode(response.body).decode("ascii")
    payload.pop("body", None)
    return payload


def _from_cache_dict(payload: dict[str, Any]) -> FetchResponse:
    data = dict(payload)
    body = base64.b64decode(data.pop("body_b64", ""))
    data["body"] = body
    return FetchResponse.model_validate(data).model_copy(update={"cached": True})
