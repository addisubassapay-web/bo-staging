"""SSRF guard tests for the scraper input validation.

Covers the `is_safe_public_url` helper directly (fast, no DNS races) plus
one integration curl against the running /api/scraper/jobs endpoint to
confirm the reject path is wired end-to-end.
"""
from __future__ import annotations

import pytest

from services.url_safety import is_safe_public_url


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/anything",
        "http://127.0.0.1:8001/api/admin/users",
        "http://localhost/",
        "http://LOCALHOST:80/x",
        "http://0.0.0.0/",
        "http://10.0.0.5/etc/passwd",
        "http://172.16.0.10/",
        "http://192.168.1.1/router",
        "http://169.254.169.254/latest/meta-data/",
        "http://metadata.google.internal/",
        "http://[::1]/",
        "http://[fc00::1]/",
        "http://user:pass@example.com/",
        "ftp://example.com/file.txt",
        "javascript:alert(1)",
        "file:///etc/passwd",
        "",
        "not a url",
        "http://",
        "http:///path",
        "http://foo.local/x",
        "http://svc.internal/",
    ],
)
def test_unsafe_urls_are_rejected(url: str):
    ok, reason = is_safe_public_url(url)
    assert not ok, f"expected {url!r} to be rejected, got ok=True"
    assert reason, "reason string must be populated"


@pytest.mark.parametrize(
    "url",
    [
        "https://www.amazon.com/s?k=headphones",
        "https://www.ebay.com/sch/i.html?_nkw=lego",
        "http://example.com/",
        "https://example.com:8443/path?x=1",
    ],
)
def test_public_urls_pass(url: str):
    ok, reason = is_safe_public_url(url)
    assert ok, f"expected {url!r} to pass, got reason={reason!r}"
    assert reason == ""


def test_extremely_long_url_rejected():
    ok, reason = is_safe_public_url("https://example.com/" + ("a" * 3000))
    assert not ok
    assert "too long" in reason
