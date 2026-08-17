"""Cloudflare R2 storage — env-gated, S3-compatible.

If any of the R2_* env vars is missing we operate in "passthrough" mode and
return the supplier URL unchanged. When credentials are supplied we stream
each remote image into the R2 bucket and return the public URL so the
marketplace never depends on supplier hotlinks.
"""
from __future__ import annotations
import hashlib
import mimetypes
import os
from typing import Optional
from urllib.parse import urlparse

import httpx

try:
    import boto3
    from botocore.config import Config as BotoConfig
except ImportError:  # boto3 is a hard dep, but keep this defensive
    boto3 = None  # type: ignore
    BotoConfig = None  # type: ignore


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def r2_enabled() -> bool:
    return all(
        _env(k)
        for k in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET")
    ) and boto3 is not None


def _client():
    return boto3.client(
        "s3",
        endpoint_url=f"https://{_env('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com",
        aws_access_key_id=_env("R2_ACCESS_KEY_ID"),
        aws_secret_access_key=_env("R2_SECRET_ACCESS_KEY"),
        region_name="auto",
        config=BotoConfig(signature_version="s3v4"),
    )


def _public_url(key: str) -> str:
    base = _env("R2_PUBLIC_URL")
    if base:
        return f"{base.rstrip('/')}/{key}"
    # Fall back to R2's public bucket URL pattern; requires bucket to have
    # "Public Access" enabled or a custom domain configured.
    return f"https://pub-{_env('R2_ACCOUNT_ID')}.r2.dev/{_env('R2_BUCKET')}/{key}"


async def rehost_image(source_url: str, *, prefix: str = "scraped") -> str:
    """Stream a remote image into R2 and return the public URL.

    Falls back to returning the original URL when R2 is not configured or on
    any transient failure — the pipeline should never crash because storage
    is unavailable.
    """
    if not source_url or not source_url.startswith(("http://", "https://")):
        return source_url
    if not r2_enabled():
        return source_url

    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            r = await client.get(source_url)
            r.raise_for_status()
            data = r.content
            content_type = r.headers.get("content-type", "").split(";")[0].strip() or _guess_ct(source_url)

        # Deterministic key so we don't upload the same image twice.
        digest = hashlib.sha256(data).hexdigest()[:24]
        ext = mimetypes.guess_extension(content_type) or ".jpg"
        key = f"{prefix}/{digest[:2]}/{digest}{ext}"

        client = _client()
        client.put_object(
            Bucket=_env("R2_BUCKET"),
            Key=key,
            Body=data,
            ContentType=content_type or "application/octet-stream",
            CacheControl="public, max-age=31536000, immutable",
        )
        return _public_url(key)
    except Exception:
        # Best-effort — keep the supplier URL if anything goes wrong.
        return source_url


def _guess_ct(url: str) -> str:
    ct, _ = mimetypes.guess_type(urlparse(url).path)
    return ct or "image/jpeg"


async def rehost_many(urls: list[str], *, prefix: str = "scraped") -> list[str]:
    out: list[str] = []
    for u in urls:
        out.append(await rehost_image(u, prefix=prefix))
    return out


def storage_status() -> dict:
    """Small helper for admin UI — reveals whether rehosting is live."""
    return {
        "provider": "cloudflare_r2",
        "enabled": r2_enabled(),
        "bucket": _env("R2_BUCKET") or None,
        "public_base": _env("R2_PUBLIC_URL") or None,
    }
