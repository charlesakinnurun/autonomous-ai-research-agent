"""URL normalization and SSRF protection.

Retrieved content is untrusted. Before any HTTP request we validate:

- scheme is http/https,
- no credentials in the URL,
- host is not private/loopback/link-local/metadata,
- DNS resolution (when enabled) returns only public addresses,
- domain allow/deny lists,
- port is permitted.

Redirects are validated hop by hop by the fetcher; this module provides the
single-hop validator used there.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Iterable
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from pydantic import Field, field_validator

from research_agent.core.errors import SecurityError, ToolError
from research_agent.models.common import FrozenModel

DEFAULT_ALLOWED_PORTS = (80, 443)
TRACKING_PARAMS = {"fbclid", "gclid", "mc_cid", "mc_eid", "ref_src", "ref_url"}


class UrlPolicy(FrozenModel):
    allowed_schemes: list[str] = Field(default_factory=lambda: ["http", "https"])
    allowed_ports: list[int] = Field(default_factory=lambda: list(DEFAULT_ALLOWED_PORTS))
    allow_private_ips: bool = False
    domain_allowlist: list[str] = Field(default_factory=list)
    domain_denylist: list[str] = Field(default_factory=list)
    resolve_dns: bool = True
    max_url_length: int = Field(default=4096, gt=0, le=16384)

    @field_validator("allowed_schemes")
    @classmethod
    def _schemes_are_lowercase(cls, value: list[str]) -> list[str]:
        return [item.lower() for item in value]

    @field_validator("domain_allowlist", "domain_denylist")
    @classmethod
    def _domains_are_normalized(cls, value: list[str]) -> list[str]:
        normalized = []
        for item in value:
            domain = item.strip().lower().strip(".")
            if not domain:
                raise ValueError("domain entries must not be empty")
            normalized.append(domain)
        return normalized


class ValidatedUrl(FrozenModel):
    original: str
    normalized: str
    scheme: str
    host: str
    port: int
    path: str
    resolved_ips: list[str] = Field(default_factory=list)


def _is_tracking_param(key: str) -> bool:
    return key.lower().startswith("utm_") or key.lower() in TRACKING_PARAMS


def normalize_url(url: str) -> str:
    """Canonical form used for dedupe and cache keys.

    Removes fragments and tracking parameters, lowercases the scheme/host,
    drops default ports, and sorts query parameters. Path case is preserved.
    """
    parts = urlsplit(url.strip())
    if parts.username or parts.password:
        raise ValueError("URL must not contain credentials")
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower().rstrip(".")
    if not scheme or not host:
        raise ValueError("URL must be absolute")
    try:
        ipaddress.ip_address(host)
        is_ip = True
    except ValueError:
        is_ip = False
        try:
            host = host.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise ValueError("invalid internationalized hostname") from exc
    port = parts.port
    if port is None:
        port = 443 if scheme == "https" else 80
    host_for_netloc = f"[{host}]" if is_ip and ":" in host else host
    if (scheme == "http" and port == 80) or (scheme == "https" and port == 443):
        netloc = host_for_netloc
    else:
        netloc = f"{host_for_netloc}:{port}"
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not _is_tracking_param(key)
    ]
    query.sort(key=lambda item: (item[0], item[1]))
    path = parts.path or "/"
    return urlunsplit((scheme, netloc, path, urlencode(query, doseq=True), ""))


def domain_of(url: str) -> str:
    host = urlsplit(url).hostname
    if not host:
        raise ValueError("URL has no hostname")
    return host.lower().rstrip(".")


def domain_matches(host: str, domain: str) -> bool:
    host = host.lower().rstrip(".")
    domain = domain.lower().rstrip(".")
    return host == domain or host.endswith(f".{domain}")


def _is_blocked_ip(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return any(
        (
            ip.is_private,
            ip.is_loopback,
            ip.is_link_local,
            ip.is_multicast,
            ip.is_reserved,
            ip.is_unspecified,
        )
    )


def _resolve_host(host: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ToolError(
            f"DNS resolution failed for {host}", code="dns_error", retryable=True
        ) from exc
    addresses: set[str] = set()
    for info in infos:
        sockaddr = info[4]
        if sockaddr:
            addresses.add(str(sockaddr[0]))
    if not addresses:
        raise ToolError(f"DNS resolution returned no addresses for {host}", retryable=True)
    return sorted(addresses)


def _validate_domains(host: str, policy: UrlPolicy) -> None:
    if policy.domain_allowlist and not any(
        domain_matches(host, domain) for domain in policy.domain_allowlist
    ):
        raise SecurityError(
            f"domain not in allowlist: {host}",
            details={"host": host},
        )
    if any(domain_matches(host, domain) for domain in policy.domain_denylist):
        raise SecurityError(f"domain is denylisted: {host}", details={"host": host})


def validate_url_sync(url: str, policy: UrlPolicy | None = None) -> ValidatedUrl:
    """Validate a single URL. Performs DNS resolution unless disabled."""
    policy = policy or UrlPolicy()
    if len(url) > policy.max_url_length:
        raise SecurityError("URL is too long")
    raw_parts = urlsplit(url)
    if raw_parts.username or raw_parts.password:
        raise SecurityError("URL must not contain credentials")
    try:
        normalized = normalize_url(url)
    except ValueError as exc:
        raise SecurityError(str(exc)) from exc
    parts = urlsplit(normalized)
    scheme = parts.scheme
    host = parts.hostname or ""
    try:
        port = parts.port or (443 if scheme == "https" else 80)
    except ValueError as exc:
        raise SecurityError("URL has an invalid port") from exc
    path = parts.path
    if scheme not in policy.allowed_schemes:
        raise SecurityError(f"scheme not allowed: {scheme}")
    if port not in policy.allowed_ports:
        raise SecurityError(f"port not allowed: {port}")
    _validate_domains(host, policy)

    resolved: list[str] = []
    try:
        ipaddress.ip_address(host)
    except ValueError:
        if policy.resolve_dns:
            resolved = _resolve_host(host)
    else:
        # IP literals are checked even when DNS resolution is disabled.
        resolved = [host]
    if resolved and not policy.allow_private_ips:
        blocked = [address for address in resolved if _is_blocked_ip(address)]
        if blocked:
            raise SecurityError(
                f"URL resolves to a private address: {host}",
                details={"host": host, "addresses": ",".join(blocked)},
            )
    return ValidatedUrl(
        original=url,
        normalized=normalized,
        scheme=scheme,
        host=host,
        port=port,
        path=path,
        resolved_ips=resolved,
    )


async def validate_url(url: str, policy: UrlPolicy | None = None) -> ValidatedUrl:
    """Async wrapper that keeps DNS off the event loop."""
    return await asyncio.to_thread(validate_url_sync, url, policy)


def validate_redirect(current_url: str, location: str, policy: UrlPolicy | None = None) -> str:
    """Resolve a redirect target and validate it before following.

    The original target (not the canonical form) is returned so signed query
    strings are not reordered by canonicalization.
    """
    target = urljoin(current_url, location)
    validate_url_sync(target, policy)
    return target


def filter_public_urls(urls: Iterable[str], policy: UrlPolicy | None = None) -> list[str]:
    """Return only safe URLs; invalid entries are dropped rather than failing a batch."""
    safe: list[str] = []
    seen: set[str] = set()
    for url in urls:
        try:
            normalized = validate_url_sync(url, policy).normalized
        except (SecurityError, ToolError, ValueError):
            continue
        if normalized not in seen:
            seen.add(normalized)
            safe.append(normalized)
    return safe
