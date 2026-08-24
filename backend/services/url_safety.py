"""SSRF-safe URL validation for user-submitted scraper targets.

We reject any URL whose:
  * scheme is not http / https
  * host is missing, obviously suspicious, or a raw IP in a private / loopback
    / link-local / reserved / multicast range
  * host resolves (via DNS) to any address in those ranges
  * URL includes embedded userinfo (`user:pass@host`) which some parsers
    treat differently than others (a classic SSRF bypass vector)

Blocks well-known cloud metadata endpoints too:
  * 169.254.169.254   — AWS / GCP / DigitalOcean IMDS
  * metadata.google.internal
  * metadata.aws
  * fd00:ec2::254     — IPv6 IMDS

The public helper is:

    is_safe_public_url(url) -> (ok: bool, reason: str)

Use it in every endpoint that accepts a URL from an authenticated user
before you queue anything, pass it to Zyte, or hand it to httpx.
"""
from __future__ import annotations

import ipaddress
import socket
from typing import Tuple
from urllib.parse import urlparse

_BLOCKED_HOSTNAMES = {
    "localhost",
    "ip6-localhost",
    "ip6-loopback",
    "metadata.google.internal",
    "metadata.aws",
    "metadata.aws.internal",
    "169.254.169.254",
    "instance-data",
    "instance-data.ec2.internal",
}

_MAX_URL_LEN = 2048


def _ip_is_disallowed(addr: str) -> bool:
    """Return True if `addr` (an IPv4 / IPv6 literal) falls in a range we
    must never let the scraper reach out to."""
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return False  # not an IP literal — hostname path handles it
    # AWS / GCP metadata IPv6 endpoint
    try:
        if ip == ipaddress.ip_address("fd00:ec2::254"):
            return True
    except ValueError:
        pass
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified  # 0.0.0.0 / ::
    )


def is_safe_public_url(url: str) -> Tuple[bool, str]:
    """Validate that `url` is a well-formed http(s) URL pointing at a
    publicly-routable host. Returns (ok, reason)."""
    if not url or not isinstance(url, str):
        return False, "URL is required"
    url = url.strip()
    if len(url) > _MAX_URL_LEN:
        return False, "URL is too long"

    try:
        parsed = urlparse(url)
    except Exception:
        return False, "URL could not be parsed"

    if parsed.scheme not in ("http", "https"):
        return False, "Only http and https URLs are allowed"
    if not parsed.netloc:
        return False, "URL is missing a host"
    if parsed.username or parsed.password:
        # Embedded credentials are a common SSRF bypass — reject outright.
        return False, "URLs with embedded credentials are not allowed"

    host = (parsed.hostname or "").strip().lower()
    if not host:
        return False, "URL is missing a host"
    if host in _BLOCKED_HOSTNAMES:
        return False, "Host is not allowed"
    if host.endswith(".localhost") or host.endswith(".internal") or host.endswith(".local"):
        return False, "Host is not allowed"

    # If the host is an IP literal, check it directly.
    stripped_host = host.strip("[]")
    if _looks_like_ip(stripped_host):
        if _ip_is_disallowed(stripped_host):
            return False, "Host resolves to a private / loopback address"
        return True, ""

    # Otherwise resolve the DNS name and reject if any A/AAAA record is
    # internal. `getaddrinfo` is synchronous, but scraper endpoints already
    # do database work in the same request; the added latency is minimal.
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False, "Host could not be resolved"
    for info in infos:
        addr = info[4][0]
        if _ip_is_disallowed(addr):
            return False, "Host resolves to a private / loopback address"
    return True, ""


def _looks_like_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False
