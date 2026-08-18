"""Media storage — local disk by default, Cloudflare R2 if configured.

Every scraped image is streamed to a persistent location we own and served
from `<REACT_APP_BACKEND_URL>/uploads/scraper/…` so listings never depend on
supplier CDNs. When R2 credentials are present we stream to the bucket
instead and return the public R2 URL. Otherwise images live on the local
FastAPI static mount at /uploads.
"""
from __future__ import annotations
import hashlib
import mimetypes
import os
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import httpx

try:
    import boto3
    from botocore.config import Config as BotoConfig
except ImportError:
    boto3 = None  # type: ignore
    BotoConfig = None  # type: ignore

# On-disk root for uploaded media. Backend must mount /uploads → this dir.
LOCAL_ROOT = Path(os.environ.get("MEDIA_LOCAL_ROOT") or "/app/backend/uploads")
LOCAL_ROOT.mkdir(parents=True, exist_ok=True)


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def r2_enabled() -> bool:
    return all(
        _env(k)
        for k in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET")
    ) and boto3 is not None


def _r2_client():
    return boto3.client(
        "s3",
        endpoint_url=f"https://{_env('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com",
        aws_access_key_id=_env("R2_ACCESS_KEY_ID"),
        aws_secret_access_key=_env("R2_SECRET_ACCESS_KEY"),
        region_name="auto",
        config=BotoConfig(signature_version="s3v4"),
    )


def _r2_public_url(key: str) -> str:
    base = _env("R2_PUBLIC_URL")
    if base:
        return f"{base.rstrip('/')}/{key}"
    return f"https://pub-{_env('R2_ACCOUNT_ID')}.r2.dev/{_env('R2_BUCKET')}/{key}"


def _local_public_url(key: str) -> str:
    """Return the fully-qualified URL a browser can fetch. Uploads are
    served under /api/uploads/ so they flow through the same ingress rule
    as the FastAPI routes."""
    base = (
        _env("BACKEND_PUBLIC_URL")
        or _env("REACT_APP_BACKEND_URL")
        or ""
    ).rstrip("/")
    return f"{base}/api/uploads/{key}" if base else f"/api/uploads/{key}"


async def rehost_image(source_url: str, *, prefix: str = "scraped") -> str:
    """Stream a remote image into media storage and return the public URL.

    Order of preference: Cloudflare R2 (if configured) → local disk.
    Falls back to the supplier URL only if BOTH storage backends error.
    """
    if not source_url or not source_url.startswith(("http://", "https://")):
        return source_url
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            r = await client.get(source_url)
            r.raise_for_status()
            data = r.content
            content_type = r.headers.get("content-type", "").split(";")[0].strip() or _guess_ct(source_url)

        digest = hashlib.sha256(data).hexdigest()[:24]
        ext = mimetypes.guess_extension(content_type) or ".jpg"
        key = f"{prefix}/{digest[:2]}/{digest}{ext}"

        if r2_enabled():
            try:
                _r2_client().put_object(
                    Bucket=_env("R2_BUCKET"),
                    Key=key,
                    Body=data,
                    ContentType=content_type or "application/octet-stream",
                    CacheControl="public, max-age=31536000, immutable",
                )
                return _r2_public_url(key)
            except Exception:
                pass  # fall through to local

        dest = LOCAL_ROOT / key
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            dest.write_bytes(data)
        return _local_public_url(key)
    except Exception:
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
    """Small helper for admin UI — reveals which backend is active."""
    if r2_enabled():
        return {
            "provider": "cloudflare_r2",
            "enabled": True,
            "bucket": _env("R2_BUCKET"),
            "public_base": _env("R2_PUBLIC_URL") or f"pub-{_env('R2_ACCOUNT_ID')}.r2.dev",
        }
    return {
        "provider": "local_disk",
        "enabled": True,
        "root": str(LOCAL_ROOT),
        "public_base": _local_public_url("").rstrip("/"),
    }
