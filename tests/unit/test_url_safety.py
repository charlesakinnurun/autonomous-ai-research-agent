"""URL normalization and SSRF protection tests."""

from __future__ import annotations

import pytest

from research_agent.core.errors import SecurityError
from research_agent.tools.url_safety import (
    UrlPolicy,
    domain_matches,
    filter_public_urls,
    normalize_url,
    validate_redirect,
    validate_url_sync,
)


def test_normalize_url_removes_tracking_and_fragment() -> None:
    normalized = normalize_url("HTTPS://Example.COM:443/a/b?utm_source=x&b=2&a=1#fragment")
    assert normalized == "https://example.com/a/b?a=1&b=2"


def test_domain_matches_subdomains_only() -> None:
    assert domain_matches("news.example.com", "example.com")
    assert domain_matches("example.com", "example.com")
    assert not domain_matches("badexample.com", "example.com")


def test_public_url_passes(public_dns: None) -> None:
    validated = validate_url_sync("https://example.com/article")
    assert validated.host == "example.com"
    assert validated.port == 443
    assert validated.resolved_ips == ["93.184.216.34"]


def test_private_and_link_local_urls_are_blocked(public_dns: None) -> None:
    for url in [
        "http://127.0.0.1/admin",
        "http://localhost/admin",
        "http://10.0.0.1/",
        "http://169.254.169.254/latest/meta-data",
        "http://[::1]/",
    ]:
        with pytest.raises(SecurityError):
            validate_url_sync(url)


def test_ip_literal_is_checked_even_without_dns() -> None:
    policy = UrlPolicy(resolve_dns=False)
    with pytest.raises(SecurityError):
        validate_url_sync("http://127.0.0.1/", policy)
    assert validate_url_sync("https://example.com/", policy).host == "example.com"


def test_scheme_port_and_credentials_are_rejected(public_dns: None) -> None:
    with pytest.raises(SecurityError):
        validate_url_sync("ftp://example.com/x")
    with pytest.raises(SecurityError):
        validate_url_sync("http://example.com:8080/x")
    with pytest.raises(SecurityError):
        validate_url_sync("https://user:pass@example.com/x")


def test_allowlist_and_denylist(public_dns: None) -> None:
    allow = UrlPolicy(domain_allowlist=["example.com"])
    assert validate_url_sync("https://news.example.com/x", allow)
    with pytest.raises(SecurityError):
        validate_url_sync("https://other.com/x", allow)
    deny = UrlPolicy(domain_denylist=["example.com"])
    with pytest.raises(SecurityError):
        validate_url_sync("https://news.example.com/x", deny)


def test_redirect_is_resolved_and_validated(public_dns: None) -> None:
    target = validate_redirect("https://example.com/a", "/b", UrlPolicy())
    assert target == "https://example.com/b"
    with pytest.raises(SecurityError):
        validate_redirect("https://example.com/a", "http://127.0.0.1/b", UrlPolicy())


def test_filter_public_urls_drops_unsafe_entries(public_dns: None) -> None:
    filtered = filter_public_urls(
        [
            "https://example.com/a",
            "http://127.0.0.1/b",
            "not-a-url",
            "https://example.com/a?utm_source=x",
        ]
    )
    assert filtered == ["https://example.com/a"]
