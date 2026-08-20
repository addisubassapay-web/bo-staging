"""
Permanent Product Catalog — webhook-ingested products stored forever.

This router is intentionally isolated from the existing `listings` marketplace
collection. It powers a permanent, read-only public catalog that is populated
via the Apify webhook. No TTLs, no scheduled cleanup, no automated archiving —
records live in `products` forever unless explicitly deleted via admin action.

Endpoints
---------
- POST /api/webhooks/apify-import  (secret-protected)
- GET  /api/products               (paginated list, is_active=true only)
- GET  /api/products/{product_id}  (single product; 404 if not found)
"""
from __future__ import annotations

import hmac
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

from routers.deps import get_db

logger = logging.getLogger(__name__)
router = APIRouter(tags=["products"])

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------
class ProductOut(BaseModel):
    id: str
    title: str
    description: str = ""
    price: float
    currency: str = "USD"
    images: List[str] = Field(default_factory=list)
    category: Optional[str] = None
    sku: Optional[str] = None
    source_url: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    is_active: bool = True


class ProductListResponse(BaseModel):
    items: List[ProductOut]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# Webhook auth
# ---------------------------------------------------------------------------
def _authorize_webhook(
    x_webhook_secret: Optional[str],
    authorization: Optional[str],
    query_secret: Optional[str],
) -> None:
    """Constant-time comparison against APIFY_WEBHOOK_SECRET.

    Accepts the secret via any of:
      • `X-Webhook-Secret: <secret>`
      • `Authorization: Bearer <secret>`
      • `?secret=<secret>` query param (useful for Apify's webhook UI)
    """
    expected = os.environ.get("APIFY_WEBHOOK_SECRET")
    if not expected:
        # Fail closed — refuse to accept webhooks until an operator sets the secret.
        raise HTTPException(503, "Webhook secret not configured on server")

    provided: Optional[str] = None
    if x_webhook_secret:
        provided = x_webhook_secret
    elif authorization and authorization.lower().startswith("bearer "):
        provided = authorization.split(" ", 1)[1].strip()
    elif query_secret:
        provided = query_secret

    if not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(401, "Invalid or missing webhook secret")


# ---------------------------------------------------------------------------
# Apify payload parsing
# ---------------------------------------------------------------------------
def _first(*vals: Any) -> Any:
    for v in vals:
        if v not in (None, "", [], {}):
            return v
    return None


def _extract_price(item: Dict[str, Any]) -> Optional[float]:
    p = item.get("price")
    if isinstance(p, dict):
        for k in ("value", "amount", "current"):
            if p.get(k) is not None:
                try:
                    return round(float(p[k]), 2)
                except (TypeError, ValueError):
                    continue
    if isinstance(p, (int, float)):
        return round(float(p), 2)
    if isinstance(p, str):
        try:
            return round(float(p.replace("$", "").replace(",", "").strip()), 2)
        except ValueError:
            return None
    for k in ("current_price", "salePrice", "price_value"):
        if item.get(k) is not None:
            try:
                return round(float(item[k]), 2)
            except (TypeError, ValueError):
                continue
    return None


def _extract_currency(item: Dict[str, Any]) -> str:
    p = item.get("price")
    if isinstance(p, dict):
        cur = p.get("currency") or p.get("currencyCode")
        if isinstance(cur, str) and cur:
            return cur.upper()
    for k in ("currency", "currencyCode"):
        cur = item.get(k)
        if isinstance(cur, str) and cur:
            return cur.upper()
    return "USD"


def _extract_images(item: Dict[str, Any]) -> List[str]:
    imgs: List[str] = []
    for k in ("highResolutionImages", "galleryThumbnails", "images", "image_urls"):
        v = item.get(k)
        if isinstance(v, list):
            imgs.extend([u for u in v if isinstance(u, str) and u.startswith("http")])
    for k in ("thumbnailImage", "image", "main_image"):
        v = item.get(k)
        if isinstance(v, str) and v.startswith("http"):
            imgs.append(v)
    # dedup preserving order
    seen: set = set()
    out: List[str] = []
    for u in imgs:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out[:10]


def _extract_source_url(item: Dict[str, Any]) -> Optional[str]:
    return _first(item.get("url"), item.get("source_url"), item.get("productUrl"), item.get("link"))


def _extract_sku(item: Dict[str, Any]) -> Optional[str]:
    return _first(item.get("sku"), item.get("asin"), item.get("productId"), item.get("id"))


def _extract_category(item: Dict[str, Any]) -> Optional[str]:
    cat = _first(item.get("category"), item.get("categorySlug"), item.get("productCategory"))
    if isinstance(cat, list) and cat:
        return str(cat[0])
    return cat if isinstance(cat, str) else None


def _normalize_product(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Convert a raw Apify item to a `products` document. Returns None if unusable."""
    title = _first(item.get("title"), item.get("name"), item.get("productTitle"))
    price = _extract_price(item)
    sku = _extract_sku(item)
    source_url = _extract_source_url(item)

    # Must have a title, a price and at least one of sku/source_url to dedupe on.
    if not title or price is None:
        return None
    if not sku and not source_url:
        return None

    desc_raw = _first(item.get("description"), item.get("productDescription"))
    description = str(desc_raw).strip()[:5000] if desc_raw else ""

    return {
        "title": str(title).strip()[:500],
        "description": description,
        "price": price,
        "currency": _extract_currency(item),
        "images": _extract_images(item),
        "category": _extract_category(item),
        "sku": str(sku) if sku else None,
        "source_url": str(source_url) if source_url else None,
    }


def _iter_apify_items(payload: Any) -> List[Dict[str, Any]]:
    """
    Accept several Apify webhook shapes:
      • a list of items                                    -> use as-is
      • { "items": [...] }                                 -> unwrap
      • { "resource": { "items": [...] } }                 -> unwrap Apify format
      • { "data": [...] } / { "products": [...] }          -> unwrap
      • { "resource": { "defaultDatasetId": "..." } }      -> ignored (no items inline)
      • a single item dict                                 -> wrap into list
    """
    if payload is None:
        return []
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in ("items", "data", "products"):
            v = payload.get(key)
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
        resource = payload.get("resource")
        if isinstance(resource, dict):
            v = resource.get("items")
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
        # single-item shape (has a title/price)
        if any(k in payload for k in ("title", "name", "productTitle")):
            return [payload]
    return []


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.post("/webhooks/apify-import")
async def webhook_apify_import(
    request: Request,
    x_webhook_secret: Optional[str] = Header(default=None, alias="X-Webhook-Secret"),
    authorization: Optional[str] = Header(default=None),
    secret: Optional[str] = Query(default=None),
):
    """Ingest products from an Apify webhook payload.

    Upserts on (sku or source_url). Existing records are updated with the
    latest data; new records are inserted. Records are stored **permanently**
    — no TTL, no scheduled cleanup.
    """
    _authorize_webhook(x_webhook_secret, authorization, secret)

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON body")

    raw_items = _iter_apify_items(payload)
    if not raw_items:
        return {
            "ok": True,
            "received": 0,
            "created": 0,
            "updated": 0,
            "skipped": 0,
            "message": "No parseable items in payload",
        }

    db = get_db()
    now = datetime.now(timezone.utc)

    created = 0
    updated = 0
    skipped = 0

    for raw in raw_items:
        norm = _normalize_product(raw)
        if not norm:
            skipped += 1
            continue

        # Build the upsert filter — prefer SKU, fall back to source_url.
        if norm.get("sku"):
            key = {"sku": norm["sku"]}
        else:
            key = {"source_url": norm["source_url"]}

        existing = await db.products.find_one(key, {"_id": 0, "id": 1})

        update_doc = {
            "$set": {
                **norm,
                "updated_at": now,
                # is_active is preserved on update (default True on insert only)
            },
            "$setOnInsert": {
                "id": str(uuid.uuid4()),
                "created_at": now,
                "is_active": True,
            },
        }
        await db.products.update_one(key, update_doc, upsert=True)

        if existing:
            updated += 1
        else:
            created += 1

    logger.info(
        f"[apify-webhook] received={len(raw_items)} created={created} updated={updated} skipped={skipped}"
    )
    return {
        "ok": True,
        "received": len(raw_items),
        "created": created,
        "updated": updated,
        "skipped": skipped,
    }


@router.get("/products", response_model=ProductListResponse)
async def list_products(
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
    category: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None, description="Case-insensitive title search"),
    active_only: bool = Query(default=True),
):
    """Public list of permanent products. Returns only active items by default."""
    db = get_db()
    filt: Dict[str, Any] = {}
    if active_only:
        filt["is_active"] = True
    if category:
        filt["category"] = category
    if q:
        filt["title"] = {"$regex": q, "$options": "i"}

    total = await db.products.count_documents(filt)
    cursor = (
        db.products.find(filt, {"_id": 0})
        .sort("created_at", -1)
        .skip((page - 1) * page_size)
        .limit(page_size)
    )
    docs = await cursor.to_list(length=page_size)
    return {"items": docs, "total": total, "page": page, "page_size": page_size}


@router.get("/products/{product_id}", response_model=ProductOut)
async def get_product(product_id: str):
    db = get_db()
    doc = await db.products.find_one({"id": product_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Product not found")
    return doc
