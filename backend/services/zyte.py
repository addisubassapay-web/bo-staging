"""Zyte API client — thin async wrapper around POST https://api.zyte.com/v1/extract.

Docs: https://docs.zyte.com/zyte-api/usage/reference.html

Uses HTTP Basic Auth with the API key as the username and an empty password.
Returns Zyte's structured `product` (schema.org-like) plus screenshot on demand.
"""
from __future__ import annotations
import base64
import os
from typing import Any, Optional

import httpx

ZYTE_ENDPOINT = "https://api.zyte.com/v1/extract"
DEFAULT_TIMEOUT = 60.0


def _api_key() -> str:
    key = os.environ.get("ZYTE_API_KEY") or ""
    if not key:
        raise RuntimeError("ZYTE_API_KEY is not configured")
    return key


def _auth_header() -> str:
    token = base64.b64encode(f"{_api_key()}:".encode()).decode()
    return f"Basic {token}"


async def extract_product(url: str, *, geolocation: Optional[str] = None,
                          high_fidelity: bool = False,
                          timeout: float = DEFAULT_TIMEOUT) -> dict[str, Any]:
    """Ask Zyte to return a structured product object for the given URL.

    Tries fast `httpResponseBody` extraction first, then automatically falls
    back to `browserHtml` (JavaScript-rendered) when the fast path yields an
    empty product. Amazon, Best Buy, and similar JS-heavy sites need this.

    When `high_fidelity=True` we skip the fast path entirely and go straight
    to browser rendering with anti-bot mitigations enabled — used for Amazon
    and other heavily-defended sites.
    """
    if high_fidelity:
        try:
            result = await _extract_with_mode(url, "browserHtml", geolocation=geolocation,
                                              timeout=max(timeout, 90.0), full_browser=True)
            result["_extract_from"] = "browserHtml_hi"
            return result
        except ZyteError:
            # Plan may not cover browser rendering — fall through to fast path.
            pass

    result = await _extract_with_mode(url, "httpResponseBody", geolocation=geolocation, timeout=timeout)
    prod = result.get("product") or {}
    if prod.get("name") or prod.get("price") is not None:
        result["_extract_from"] = "httpResponseBody"
        return result
    # Fallback: JS-rendered extraction for SPA / bot-defended sites.
    try:
        result = await _extract_with_mode(url, "browserHtml", geolocation=geolocation,
                                          timeout=max(timeout, 90.0))
        result["_extract_from"] = "browserHtml"
    except ZyteError:
        result.setdefault("_extract_from", "httpResponseBody")
    return result


async def _extract_with_mode(url: str, mode: str, *, geolocation: Optional[str] = None,
                             timeout: float = DEFAULT_TIMEOUT,
                             full_browser: bool = False) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "url": url,
        "product": True,
        "productOptions": {"extractFrom": mode},
    }
    if full_browser:
        # Request the full browser pipeline (with Zyte's anti-bot proxy).
        payload["browserHtml"] = True
    if geolocation:
        payload["geolocation"] = geolocation

    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(
            ZYTE_ENDPOINT,
            json=payload,
            headers={"Authorization": _auth_header(), "Content-Type": "application/json"},
        )
        if r.status_code >= 400:
            try:
                data = r.json()
            except Exception:
                data = {"detail": r.text}
            raise ZyteError(status=r.status_code, detail=data)
        return r.json()


class ZyteError(Exception):
    def __init__(self, status: int, detail: Any):
        self.status = status
        self.detail = detail
        super().__init__(f"Zyte API error {status}: {detail}")


def normalize_product(zyte_payload: dict[str, Any]) -> dict[str, Any]:
    """Flatten a Zyte extraction into the marketplace's canonical listing shape.

    Zyte's response contains a `product` object; we map its fields onto the
    keys the marketplace already uses (title, description, price, images, etc.).
    """
    p = zyte_payload.get("product") or {}
    # Price
    price = None
    try:
        price = float(p.get("price")) if p.get("price") is not None else None
    except (TypeError, ValueError):
        price = None
    # Images
    images: list[str] = []
    for img in (p.get("images") or []):
        if isinstance(img, dict) and img.get("url"):
            images.append(img["url"])
        elif isinstance(img, str):
            images.append(img)
    if not images and p.get("mainImage") and isinstance(p["mainImage"], dict):
        images.append(p["mainImage"].get("url", ""))
    images = [u for u in images if u]

    return {
        "title": (p.get("name") or "").strip()[:200],
        "description": (p.get("description") or "").strip(),
        "price": price,
        "currency": p.get("currency") or "USD",
        "images": images[:12],
        "brand": (p.get("brand") or {}).get("name") if isinstance(p.get("brand"), dict) else p.get("brand"),
        "sku": p.get("sku"),
        "gtin": p.get("gtin") if isinstance(p.get("gtin"), str) else None,
        "availability": p.get("availability"),
        "aggregate_rating": p.get("aggregateRating"),
        "url": zyte_payload.get("url"),
        "extract_from": zyte_payload.get("_extract_from"),
        "raw": p,
    }
