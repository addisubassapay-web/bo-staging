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

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

from routers.deps import get_db, require_admin

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


# ---------------------------------------------------------------------------
# Admin management endpoints (auth-gated by require_admin)
# ---------------------------------------------------------------------------
class ProductUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    currency: Optional[str] = None
    category: Optional[str] = None
    sku: Optional[str] = None
    source_url: Optional[str] = None
    images: Optional[List[str]] = None
    is_active: Optional[bool] = None


@router.get("/admin/products", response_model=ProductListResponse)
async def admin_list_products(
    _admin: dict = Depends(require_admin),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    q: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
    status: str = Query(default="all", regex="^(all|active|inactive)$"),
):
    """Admin listing — includes inactive products and full search."""
    db = get_db()
    filt: Dict[str, Any] = {}
    if status == "active":
        filt["is_active"] = True
    elif status == "inactive":
        filt["is_active"] = False
    if category:
        filt["category"] = category
    if q:
        # Search title or SKU
        filt["$or"] = [
            {"title": {"$regex": q, "$options": "i"}},
            {"sku": {"$regex": q, "$options": "i"}},
        ]

    total = await db.products.count_documents(filt)
    cursor = (
        db.products.find(filt, {"_id": 0})
        .sort("created_at", -1)
        .skip((page - 1) * page_size)
        .limit(page_size)
    )
    docs = await cursor.to_list(length=page_size)
    return {"items": docs, "total": total, "page": page, "page_size": page_size}


@router.patch("/admin/products/{product_id}", response_model=ProductOut)
async def admin_update_product(
    product_id: str,
    payload: ProductUpdate,
    _admin: dict = Depends(require_admin),
):
    """Update any editable field on a product. Only provided fields are changed."""
    db = get_db()
    updates = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None or k == "is_active"}
    if not updates:
        raise HTTPException(400, "No fields to update")

    # Guard: if changing sku or source_url, keep them non-empty strings if provided
    if "sku" in updates and updates["sku"] is not None:
        updates["sku"] = str(updates["sku"]).strip() or None
    if "source_url" in updates and updates["source_url"] is not None:
        updates["source_url"] = str(updates["source_url"]).strip() or None

    updates["updated_at"] = datetime.now(timezone.utc)
    result = await db.products.update_one({"id": product_id}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(404, "Product not found")

    doc = await db.products.find_one({"id": product_id}, {"_id": 0})
    return doc


@router.delete("/admin/products/{product_id}")
async def admin_delete_product(
    product_id: str,
    _admin: dict = Depends(require_admin),
):
    """Hard-delete a product (permanent). Use `is_active=false` for soft-hide instead."""
    db = get_db()
    result = await db.products.delete_one({"id": product_id})
    if result.deleted_count == 0:
        raise HTTPException(404, "Product not found")
    return {"ok": True, "deleted": product_id}


class BulkAction(BaseModel):
    ids: List[str]
    action: str  # "activate" | "deactivate" | "delete"


@router.post("/admin/products/bulk")
async def admin_bulk_products(
    payload: BulkAction,
    _admin: dict = Depends(require_admin),
):
    """Apply an action to multiple products in one shot."""
    if not payload.ids:
        raise HTTPException(400, "No product ids provided")
    if len(payload.ids) > 500:
        raise HTTPException(400, "Bulk action limited to 500 items")
    if payload.action not in ("activate", "deactivate", "delete"):
        raise HTTPException(400, "Unknown action")

    db = get_db()
    if payload.action == "delete":
        result = await db.products.delete_many({"id": {"$in": payload.ids}})
        return {"ok": True, "action": "delete", "affected": result.deleted_count}

    is_active = payload.action == "activate"
    result = await db.products.update_many(
        {"id": {"$in": payload.ids}},
        {"$set": {"is_active": is_active, "updated_at": datetime.now(timezone.utc)}},
    )
    return {
        "ok": True,
        "action": payload.action,
        "affected": result.modified_count,
        "matched": result.matched_count,
    }


@router.post("/admin/products/import-from-listings")
async def import_products_from_listings(
    payload: dict = Body(default={}),
    _admin: dict = Depends(require_admin),
):
    """One-shot: promote every Apify-sourced row in `listings` into the
    permanent `products` catalog via upsert on sku (=apify_asin).

    Idempotent — re-running only refreshes titles/prices/images/categories
    and never creates duplicates because upsert is keyed on `sku`.

    Body (all optional):
      {
        "only_apify": true,           // if false, also promote non-Apify listings that have a source_url
        "status_filter": "active"     // which listing status(es) to consider
      }
    """
    db = get_db()
    only_apify = bool(payload.get("only_apify", True))
    status_filter = payload.get("status_filter", "active")

    q: dict = {"status": status_filter} if status_filter else {}
    if only_apify:
        q["apify_asin"] = {"$ne": None, "$exists": True}
    else:
        # Non-Apify: only take rows that have SOME external identifier
        q["$or"] = [
            {"apify_asin": {"$ne": None, "$exists": True}},
            {"source_url": {"$ne": None, "$exists": True}},
        ]

    listings = await db.listings.find(q, {"_id": 0}).to_list(50000)
    created = 0
    updated = 0
    skipped = 0
    now = datetime.now(timezone.utc)

    for l in listings:
        sku = l.get("apify_asin") or None
        source_url = l.get("apify_url") or l.get("source_url") or None
        if not sku and not source_url:
            skipped += 1
            continue
        # Upsert key — prefer sku, fall back to source_url
        upsert_query = {"sku": sku} if sku else {"source_url": source_url}
        # Skip if we somehow have neither in an insertable form
        product_doc = {
            "title": (l.get("title") or "")[:180],
            "description": l.get("description") or "",
            "price": float(l.get("price") or 0.0),
            "currency": l.get("currency") or "USD",
            "images": list(l.get("images") or []),
            "category": l.get("category_name") or None,
            "sku": sku,
            "source_url": source_url,
            "is_active": True,
            "updated_at": now,
        }
        existing = await db.products.find_one(upsert_query, {"_id": 0, "id": 1})
        if existing:
            await db.products.update_one(upsert_query, {"$set": product_doc})
            updated += 1
        else:
            product_doc["id"] = str(uuid.uuid4())
            product_doc["created_at"] = now
            await db.products.insert_one(product_doc)
            created += 1

    total = await db.products.count_documents({})
    active = await db.products.count_documents({"is_active": True})
    return {
        "ok": True,
        "listings_scanned": len(listings),
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "total_products_in_catalog": total,
        "active_products": active,
    }
