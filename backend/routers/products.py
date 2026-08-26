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
import re
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
    # ISO 3166-1 alpha-2 — origin country derived from `source_url`.
    # Rendered as a flag next to the "Ships from" line on every tile.
    seller_country: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    is_active: bool = True
    # True until Apify sees the source listing become unavailable. Products
    # with in_stock=False remain on the storefront but render an OOS badge.
    in_stock: bool = True


def _seller_country_from_url(url: Optional[str]) -> Optional[str]:
    """Best-effort country guess for a scraper source URL. Keeps the same
    mapping as `services.listing_mirror._country_from_source_url` so the
    listings and products storefronts render consistent flags."""
    if not url:
        return None
    u = url.lower()
    if "amazon.co.uk" in u: return "GB"
    if "amazon.de" in u:    return "DE"
    if "amazon.co.jp" in u: return "JP"
    if "amazon.fr" in u:    return "FR"
    if "amazon.ca" in u:    return "CA"
    if "amazon.com.au" in u:return "AU"
    if "jp.mercari" in u:   return "JP"
    if "amazon.com" in u:   return "US"
    return None


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
    # Alternate keys used by some Apify Amazon scrapers (product_price is
    # typically a formatted string like "$449.99").
    for k in ("current_price", "salePrice", "price_value", "product_price"):
        v = item.get(k)
        if v is None:
            continue
        if isinstance(v, (int, float)):
            try:
                return round(float(v), 2)
            except (TypeError, ValueError):
                continue
        if isinstance(v, str):
            try:
                return round(float(v.replace("$", "").replace(",", "").strip()), 2)
            except ValueError:
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
    # Single-image alternate keys — `product_photo` is used by Apify's Amazon
    # Rainforest-style actor.
    for k in ("thumbnailImage", "image", "main_image", "product_photo"):
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
    return _first(
        item.get("url"), item.get("source_url"), item.get("productUrl"),
        item.get("product_url"), item.get("link"),
    )


def _extract_sku(item: Dict[str, Any]) -> Optional[str]:
    return _first(item.get("sku"), item.get("asin"), item.get("productId"), item.get("id"))


def _extract_category(item: Dict[str, Any]) -> Optional[str]:
    """Best-effort category resolution.

    Uses the dedicated classifier which prefers Apify's breadCrumbs chain
    (Amazon's own taxonomy) over ad-hoc keyword matching. Falls back to
    any existing `category` field, then to a title-keyword scorer.
    """
    from services.product_category import classify_product
    return classify_product(item)


def _normalize_product(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Convert a raw Apify item to a `products` document. Returns None if unusable.

    Out-of-stock items (no current price) are still ingested — they're stored
    with `price=0.0`, `in_stock=False`, and are marked inactive on insert so
    they don't leak onto the storefront. When Apify re-scrapes them with a
    real price, the ingest loop will flip them back to active.
    """
    title = _first(item.get("title"), item.get("name"), item.get("productTitle"), item.get("product_title"))
    price = _extract_price(item)
    sku = _extract_sku(item)
    source_url = _extract_source_url(item)

    # Bare-minimum requirements: title + something to dedupe on.
    if not title:
        return None
    if not sku and not source_url:
        return None

    desc_raw = _first(item.get("description"), item.get("productDescription"))
    description = str(desc_raw).strip()[:5000] if desc_raw else ""

    in_stock = price is not None
    # Some Apify actors also expose an inStock boolean — honour it when the
    # price is missing (rare items with inStock=True but no listed price).
    raw_stock = item.get("inStock")
    if isinstance(raw_stock, bool):
        in_stock = in_stock and raw_stock

    return {
        "title": str(title).strip()[:500],
        "description": description,
        "price": price if price is not None else 0.0,
        "currency": _extract_currency(item),
        "images": _extract_images(item),
        "category": _extract_category(item),
        "breadcrumbs": (str(item.get("breadCrumbs")) if item.get("breadCrumbs") else None),
        "sku": str(sku) if sku else None,
        "source_url": str(source_url) if source_url else None,
        "in_stock": in_stock,
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


def _extract_dataset_id(payload: Any) -> Optional[str]:
    """Pull the Apify default dataset id from a webhook envelope when the
    body doesn't include inline items. Apify's real webhooks send:
        { "resource": { "defaultDatasetId": "abc123", ... }, ... }
    We also accept top-level `defaultDatasetId` / `dataset_id` for convenience.
    """
    if not isinstance(payload, dict):
        return None
    for key in ("defaultDatasetId", "dataset_id", "datasetId"):
        v = payload.get(key)
        if isinstance(v, str) and v:
            return v
    resource = payload.get("resource")
    if isinstance(resource, dict):
        for key in ("defaultDatasetId", "dataset_id", "datasetId"):
            v = resource.get(key)
            if isinstance(v, str) and v:
                return v
    return None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.post("/webhooks/apify-import")
async def webhook_apify_import(
    request: Request,
    x_webhook_secret: Optional[str] = Header(default=None, alias="X-Webhook-Secret"),
    authorization: Optional[str] = Header(default=None),
    secret: Optional[str] = Query(default=None),
    background: Optional[bool] = Query(
        default=None,
        description="Force queue path (true) or sync path (false). Default: auto by payload size.",
    ),
):
    """Ingest products from an Apify webhook payload.

    Small inline payloads (<= INLINE_LIMIT items and no dataset_id) are
    processed synchronously and return created/updated counters — this
    preserves the behaviour our regression tests rely on.

    Large inline payloads or Apify-native envelopes that reference a
    `defaultDatasetId` are handed off to the arq worker so the HTTP call
    returns 200 immediately, avoiding the 502 timeout Apify hits when
    posting 4,000+ items in one shot. Poll `GET /api/admin/webhooks/
    apify-import/status/{job_id}` (or the /status list endpoint) for
    progress.

    Records are stored **permanently** — no TTL, no scheduled cleanup.
    """
    INLINE_LIMIT = 200  # items processed synchronously; anything larger is queued

    _authorize_webhook(x_webhook_secret, authorization, secret)

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON body")

    raw_items = _iter_apify_items(payload)
    dataset_id = _extract_dataset_id(payload) if not raw_items else None

    # Decide sync vs async
    force_bg = background is True
    force_sync = background is False
    should_queue = (
        force_bg
        or (not force_sync and dataset_id is not None)
        or (not force_sync and len(raw_items) > INLINE_LIMIT)
    )

    if should_queue:
        from arq import create_pool
        from arq.connections import RedisSettings

        redis_url = os.environ.get("REDIS_URL") or "redis://localhost:6379/0"
        job_id = str(uuid.uuid4())
        kind = "dataset" if dataset_id else "items"
        job_payload: Any = dataset_id if dataset_id else raw_items

        try:
            pool = await create_pool(RedisSettings.from_dsn(redis_url))
            try:
                await pool.enqueue_job(
                    "webhook_ingest_task",
                    kind,
                    job_payload,
                    job_id,
                    _job_id=f"webhook-import:{job_id}",
                )
            finally:
                await pool.close()
        except Exception as e:  # noqa: BLE001
            logger.exception("[apify-webhook] failed to enqueue")
            raise HTTPException(503, f"Queue unavailable: {e}")

        db = get_db()
        await db.apify_ingest_state.update_one(
            {"id": job_id},
            {
                "$set": {
                    "id": job_id,
                    "kind": kind,
                    "status": "queued",
                    "dataset_id": dataset_id,
                    "queued_items": len(raw_items),
                    "created_at": datetime.now(timezone.utc),
                }
            },
            upsert=True,
        )
        logger.info(
            f"[apify-webhook] queued job={job_id} kind={kind} items={len(raw_items)} dataset_id={dataset_id}"
        )
        return {
            "ok": True,
            "queued": True,
            "job_id": job_id,
            "kind": kind,
            "received": len(raw_items) if raw_items else None,
            "dataset_id": dataset_id,
            "message": "Ingest queued — poll /api/admin/webhooks/apify-import/status/{job_id}",
        }

    # ---- Sync path (small payloads) -----------------------------------------
    if not raw_items:
        return {
            "ok": True,
            "received": 0,
            "created": 0,
            "updated": 0,
            "skipped": 0,
            "message": "No parseable items in payload",
        }

    from services.webhook_ingest import ingest_items
    db = get_db()
    result = await ingest_items(db, raw_items)
    logger.info(
        f"[apify-webhook] sync received={result['received']} created={result['created']} "
        f"updated={result['updated']} skipped={result['skipped']}"
    )
    return {"ok": True, **result}


@router.get("/products", response_model=ProductListResponse)
async def list_products(
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
    category: Optional[str] = Query(default=None),
    subcategory: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None, description="Case-insensitive title search"),
    active_only: bool = Query(default=True),
    in_stock_only: bool = Query(
        default=False,
        description="If true, exclude out-of-stock products from the response.",
    ),
    sort: str = Query(
        default="stock_then_newest",
        description=(
            "stock_then_newest (default) | newest | oldest | price_asc | "
            "price_desc | title. Default puts in-stock items first so the "
            "storefront isn't dominated by OOS tiles clustered at the top."
        ),
    ),
):
    """Public list of permanent products. Returns only active items by default.

    Products with `in_stock=false` are still returned (they render an OOS
    badge on the tile) unless `in_stock_only=true` is passed. To keep the
    catalog scannable, the default sort demotes OOS items to the end so a
    fresh visitor lands on real inventory, not restock candidates.

    Regression-test artefacts (SKUs matching the reserved test-prefix
    pattern) are excluded server-side so a leaked webhook payload never
    reaches the storefront.
    """
    from services.storefront_filter import product_test_filter
    db = get_db()
    filt: Dict[str, Any] = dict(product_test_filter())
    if active_only:
        filt["is_active"] = True
    if in_stock_only:
        # Treat missing `in_stock` as True for legacy docs that never had
        # the field populated.
        filt["$or"] = [{"in_stock": True}, {"in_stock": {"$exists": False}}]
    if category:
        # Case-insensitive exact match so `?category=electronics` and
        # `?category=Electronics` both hit the same bucket.
        filt["category"] = {"$regex": f"^{re.escape(category)}$", "$options": "i"}
    if subcategory:
        # Sub-category matches the SECOND segment of the stored breadcrumbs
        # (e.g. "Home & Kitchen > Kitchen & Dining > ..." → "Kitchen & Dining").
        # We use a case-insensitive regex on the whole chain so the query
        # `?subcategory=Kitchen%20%26%20Dining` matches.
        filt["breadcrumbs"] = {
            "$regex": f">\\s*{re.escape(subcategory)}\\s*(>|$)",
            "$options": "i",
        }
    if q:
        filt["title"] = {"$regex": q, "$options": "i"}

    sort_map: Dict[str, List] = {
        # in_stock=True > False, so DESC puts in-stock first. Then newest.
        "stock_then_newest": [("in_stock", -1), ("created_at", -1)],
        "newest": [("created_at", -1)],
        "oldest": [("created_at", 1)],
        "price_asc": [("in_stock", -1), ("price", 1)],
        "price_desc": [("in_stock", -1), ("price", -1)],
        "title": [("in_stock", -1), ("title", 1)],
    }
    sort_spec = sort_map.get(sort, sort_map["stock_then_newest"])

    total = await db.products.count_documents(filt)
    cursor = (
        db.products.find(filt, {"_id": 0})
        .sort(sort_spec)
        .skip((page - 1) * page_size)
        .limit(page_size)
    )
    docs = await cursor.to_list(length=page_size)
    # Attach seller_country derived from source_url so the storefront can
    # render a flag next to every tile without a schema migration.
    for d in docs:
        if not d.get("seller_country"):
            d["seller_country"] = _seller_country_from_url(d.get("source_url"))

    # Deployment-safe fallback: freshly-deployed pods start with an empty
    # `products` collection until the first Apify auto-sync completes
    # (~60s startup delay). Rather than showing an empty storefront during
    # that window — or forever if the deploy doesn't have Apify creds —
    # top-up the response with matching active seller `listings`. This is
    # a NO-OP on healthy environments (preview has 4.5k+ products, so the
    # threshold check short-circuits immediately).
    FALLBACK_THRESHOLD = 100
    global_product_count = await db.products.count_documents({"is_active": True})
    if global_product_count < FALLBACK_THRESHOLD:
        merged_docs, merged_total = await _augment_with_listings(
            db=db,
            existing_docs=docs,
            products_total=total,
            page=page,
            page_size=page_size,
            category=category,
            subcategory=subcategory,
            q=q,
            in_stock_only=in_stock_only,
            sort=sort,
        )
        return {"items": merged_docs, "total": merged_total, "page": page, "page_size": page_size}

    return {"items": docs, "total": total, "page": page, "page_size": page_size}


def _listing_to_product_shape(l: Dict[str, Any]) -> Dict[str, Any]:
    """Map a `listings` document into the ProductOut shape so a listing
    can be surfaced through the `/api/products` catalog endpoint without
    the frontend needing to know about the two-collection architecture."""
    return {
        "id": l.get("id"),
        "title": l.get("title", ""),
        "description": l.get("description", "") or "",
        "price": float(l.get("price") or 0.0),
        "currency": "USD",
        "images": l.get("images") or [],
        "category": l.get("category_name"),
        "sku": l.get("id"),  # listings don't have SKUs; reuse id
        "source_url": l.get("source_url"),
        "seller_country": l.get("seller_country") or _seller_country_from_url(l.get("source_url")),
        "created_at": l.get("created_at"),
        "updated_at": None,
        "is_active": (l.get("status") == "active"),
        "in_stock": (l.get("status") == "active"),
    }


async def _augment_with_listings(
    *,
    db,
    existing_docs: List[Dict[str, Any]],
    products_total: int,
    page: int,
    page_size: int,
    category: Optional[str],
    subcategory: Optional[str],
    q: Optional[str],
    in_stock_only: bool,
    sort: str,
) -> tuple[List[Dict[str, Any]], int]:
    """Deploy-time fallback: top-up the `/api/products` result with matching
    seller `listings` when the permanent products catalog is nearly-empty
    (fresh deployment, Apify sync still pending). Returns the merged page
    plus the merged total so pagination reflects both sources."""
    from services.storefront_filter import listing_test_filter, LISTING_TEST_TITLE_RE, SELLER_TEST_USERNAME_RE
    listing_filter: Dict[str, Any] = dict(listing_test_filter())
    listing_filter["status"] = "active"
    # Additional Zyte-scraper URL blocks (guardrails owned by server._build_listings_query).
    listing_filter["$nor"] = [
        {"source_url": {"$regex": r"toscrape\.com", "$options": "i"}},
        {"source_url": {"$regex": r"scrape\.me", "$options": "i"}},
        {"source_url": {"$regex": r"quotes\.toscrape", "$options": "i"}},
        # Belt-and-braces: re-apply the title/seller regex via `$nor` so a
        # future refactor of `listing_test_filter()` can never drop the
        # guard by accident.
        {"title": {"$regex": LISTING_TEST_TITLE_RE, "$options": "i"}},
        {"seller_name": {"$regex": SELLER_TEST_USERNAME_RE}},
    ]
    if category:
        listing_filter["category_name"] = {"$regex": f"^{re.escape(category)}$", "$options": "i"}
    if q:
        listing_filter["title"] = {"$regex": q, "$options": "i"}

    listing_sort = {
        "newest": [("created_at", -1)],
        "oldest": [("created_at", 1)],
        "price_asc": [("price", 1)],
        "price_desc": [("price", -1)],
    }.get(sort, [("created_at", -1)])

    listings_total = await db.listings.count_documents(listing_filter)
    merged_total = products_total + listings_total

    # Compute how many listings this page needs.
    # Page slice [ (page-1)*page_size : page*page_size ] is filled first by
    # products, then by listings.
    slice_start = (page - 1) * page_size
    slice_end = slice_start + page_size
    # How many products would land on this page (regardless of what we
    # already fetched): each page has `page_size` products until we run
    # out at `products_total`.
    products_on_this_page = max(0, min(page_size, products_total - slice_start))
    listings_needed = page_size - len(existing_docs)

    if listings_needed <= 0:
        return existing_docs, merged_total

    # Where in the listings stream to start: we skip listings that would
    # have appeared on previous pages after products ran out.
    listings_skip = max(0, slice_start - products_total + products_on_this_page)
    cursor = (
        db.listings.find(listing_filter, {"_id": 0})
        .sort(listing_sort)
        .skip(listings_skip)
        .limit(listings_needed)
    )
    listing_docs = await cursor.to_list(length=listings_needed)
    return existing_docs + [_listing_to_product_shape(l) for l in listing_docs], merged_total


@router.get("/products/categories")
async def product_category_counts(
    active_only: bool = Query(default=True),
    in_stock_only: bool = Query(default=False),
):
    """Counts of active products per canonical marketplace category.

    Powers the chip row at the top of `/products` so shoppers see at a
    glance how many tiles live in each bucket. Categories without any
    matching product are still included (with count=0) so the row layout
    stays stable across ingests.
    """
    from services.product_category import CANONICAL_CATEGORIES
    from services.storefront_filter import product_test_filter
    db = get_db()
    filt: Dict[str, Any] = dict(product_test_filter())
    if active_only:
        filt["is_active"] = True
    if in_stock_only:
        filt["$or"] = [{"in_stock": True}, {"in_stock": {"$exists": False}}]

    pipeline = [
        {"$match": filt},
        {"$group": {"_id": "$category", "n": {"$sum": 1}}},
    ]
    rows = {r["_id"] or "": int(r["n"]) async for r in db.products.aggregate(pipeline)}

    total = await db.products.count_documents(filt)
    uncategorized = rows.get("", 0)
    items = [
        {"name": name, "slug": name.lower(), "count": rows.get(name, 0)}
        for name in CANONICAL_CATEGORIES
    ]
    return {
        "items": items,
        "total": total,
        "uncategorized": uncategorized,
    }


@router.get("/products/subcategories")
async def product_subcategory_counts(
    category: str = Query(..., description="Canonical parent category (Home, Electronics, ...)"),
    active_only: bool = Query(default=True),
    limit: int = Query(default=24, ge=1, le=60),
):
    """Break a parent category into subcategory chips using the Amazon
    breadcrumbs we store on each product.

    Strategy: take the SECOND breadcrumb segment (segment 0 is the Amazon
    top-level like "Home & Kitchen", segment 1 is the useful bucket like
    "Kitchen & Dining"). Rolls up ties and returns the top-N by count.
    """
    db = get_db()
    filt: Dict[str, Any] = {
        "category": {"$regex": f"^{re.escape(category)}$", "$options": "i"},
        "breadcrumbs": {"$exists": True, "$nin": [None, ""]},
    }
    if active_only:
        filt["is_active"] = True

    pipeline = [
        {"$match": filt},
        # split breadcrumbs on ">" and take the second segment
        {"$project": {
            "seg": {"$trim": {"input": {"$arrayElemAt": [{"$split": ["$breadcrumbs", ">"]}, 1]}}}
        }},
        {"$match": {"seg": {"$nin": [None, ""]}}},
        {"$group": {"_id": "$seg", "n": {"$sum": 1}}},
        {"$sort": {"n": -1}},
        {"$limit": limit},
    ]
    rows = [r async for r in db.products.aggregate(pipeline)]
    items = [{"name": r["_id"], "count": int(r["n"])} for r in rows]
    total = await db.products.count_documents({
        "category": {"$regex": f"^{re.escape(category)}$", "$options": "i"},
        **({"is_active": True} if active_only else {}),
    })
    return {
        "category": category,
        "items": items,
        "total": total,
    }


@router.get("/products/suggest")
async def products_suggest(
    q: str = Query(..., min_length=1, max_length=100),
    limit: int = Query(default=8, ge=1, le=15),
):
    """Autocomplete + typo-tolerant suggest.

    Returns matching products (prefix first, then substring), spelling
    corrections (when no direct hit is found), matching category chips,
    and related terms. Powers the search dropdown on `/products`.
    """
    from services.product_search import build_suggest
    from services.search_analytics import fire_and_forget
    db = get_db()
    result = await build_suggest(db, q, product_limit=limit)
    # Fire-and-forget analytics — never blocks the response.
    if len(q.strip()) >= 2:
        fire_and_forget(
            db, q, len(result.get("products") or []),
            result.get("corrected"), result.get("took_ms", 0),
        )
    return result


@router.post("/admin/search/vocab-refresh")
async def admin_search_vocab_refresh(_admin: dict = Depends(require_admin)):
    """Invalidate the fuzzy-correction vocab cache so the next suggest
    call rebuilds it from the latest product titles + successful
    searches. This is the self-healing loop that grows the vocabulary
    from what real shoppers type. Meant to be called weekly by a cron —
    or manually from the admin dashboard after a big ingest."""
    from services.product_search import clear_vocab_cache, _harvest_vocab
    clear_vocab_cache()
    db = get_db()
    fresh = await _harvest_vocab(db)
    return {"ok": True, "vocab_size": len(fresh)}


@router.get("/admin/search/analytics")
async def admin_search_analytics(
    _admin: dict = Depends(require_admin),
    hours: int = Query(default=24, ge=1, le=720),
    limit: int = Query(default=25, ge=1, le=100),
):
    """Search-analytics dashboard payload.

    Returns:
      - top_queries: most-searched terms in the window
      - zero_result: most-searched terms that returned NO products AND
        had no spelling correction (the vocabulary/inventory gaps)
      - total_searches, unique_queries, correction_rate
    """
    from datetime import timedelta
    db = get_db()
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    total = await db.search_events.count_documents({"created_at": {"$gte": since}})
    unique = len(await db.search_events.distinct(
        "query", {"created_at": {"$gte": since}}
    ))
    corrections = await db.search_events.count_documents(
        {"created_at": {"$gte": since}, "corrected": {"$ne": None}}
    )

    top_pipeline = [
        {"$match": {"created_at": {"$gte": since}, "query": {"$ne": ""}}},
        {"$group": {"_id": "$query", "n": {"$sum": 1},
                    "avg_results": {"$avg": "$result_count"}}},
        {"$sort": {"n": -1}},
        {"$limit": limit},
    ]
    top_queries = [
        {"query": r["_id"], "count": int(r["n"]),
         "avg_results": round(float(r["avg_results"] or 0), 1)}
        async for r in db.search_events.aggregate(top_pipeline)
    ]

    zero_pipeline = [
        {"$match": {"created_at": {"$gte": since}, "zero_result": True, "query": {"$ne": ""}}},
        {"$group": {"_id": "$query", "n": {"$sum": 1},
                    "last_seen": {"$max": "$created_at"}}},
        {"$sort": {"n": -1}},
        {"$limit": limit},
    ]
    zero_result = [
        {"query": r["_id"], "count": int(r["n"]),
         "last_seen": r["last_seen"].isoformat() if r.get("last_seen") else None}
        async for r in db.search_events.aggregate(zero_pipeline)
    ]

    return {
        "window_hours": hours,
        "total_searches": total,
        "unique_queries": unique,
        "correction_rate": round(corrections / total, 3) if total else 0.0,
        "top_queries": top_queries,
        "zero_result": zero_result,
    }


@router.get("/products/{product_id}", response_model=ProductOut)
async def get_product(product_id: str):
    db = get_db()
    doc = await db.products.find_one({"id": product_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Product not found")
    return doc


# ---------------------------------------------------------------------------
# Webhook ingest status (public read; requires knowing the job_id from the
# webhook response, so effectively private without listing them)
# ---------------------------------------------------------------------------
@router.get("/admin/webhooks/apify-import/status/{job_id}")
async def webhook_ingest_status(
    job_id: str,
    _admin: dict = Depends(require_admin),
):
    """Progress of a queued webhook ingest job."""
    db = get_db()
    doc = await db.apify_ingest_state.find_one({"id": job_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Ingest job not found")
    return doc


@router.get("/admin/webhooks/apify-import/status")
async def webhook_ingest_status_list(
    _admin: dict = Depends(require_admin),
    limit: int = Query(20, ge=1, le=100),
):
    """Latest webhook ingest jobs (newest first)."""
    db = get_db()
    cursor = db.apify_ingest_state.find({}, {"_id": 0}).sort("created_at", -1).limit(limit)
    docs = await cursor.to_list(length=limit)
    return {"items": docs, "count": len(docs)}



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

@router.post("/admin/products/ai-polish")
async def admin_products_ai_polish(
    payload: dict = Body(default={}),
    _admin: dict = Depends(require_admin),
):
    """Batch-run AI polish (GPT via Emergent LLM Key).

    Body: {
      "limit": 50,        // products per call (default 50, max 200)
      "force": false,     // if true, re-polish rows even if ai_polished_at is set
      "only_active": true
    }

    Cost per product: ~1500 tokens ≈ $0.0006 with gpt-5.4. 20k products ≈ $12.
    """
    from services.product_ai import polish_batch
    db = get_db()
    limit = max(1, min(int(payload.get("limit", 50)), 200))
    force = bool(payload.get("force", False))
    only_active = bool(payload.get("only_active", True))
    result = await polish_batch(db, limit=limit, force=force, only_active=only_active)
    remaining = await db.products.count_documents({
        "is_active": True if only_active else {"$exists": True},
        "ai_polished_at": {"$exists": False},
    })
    return {"ok": True, **result, "remaining_unpolished": remaining}


@router.get("/admin/products/ai-polish/status")
async def admin_products_ai_polish_status(_admin: dict = Depends(require_admin)):
    """Progress meter for the polish job — surfaces on the admin dashboard."""
    db = get_db()
    total = await db.products.count_documents({"is_active": True})
    polished = await db.products.count_documents({"is_active": True, "ai_polished_at": {"$exists": True}})
    failed = await db.products.count_documents({"is_active": True, "ai_polish_failed": True})
    return {
        "total_active": total,
        "polished": polished,
        "failed": failed,
        "remaining": max(0, total - polished),
        "pct_complete": round(100.0 * polished / total, 1) if total else 100.0,
    }



@router.post("/admin/products/r2-rehost")
async def admin_products_r2_rehost(
    payload: dict = Body(default={}),
    _admin: dict = Depends(require_admin),
):
    """Batch-rehost external product images (Amazon, etc.) into Cloudflare R2.

    Body: {
      "limit": 25,        // products per call (default 25, max 100)
      "force": false,     // if true, re-rehost even if r2_rehosted_at set
      "only_active": true
    }

    Streams each image once → uploads to our R2 bucket → rewrites
    `products.images[]` with the public R2 URL. Idempotent: rows already
    on R2 are marked and skipped.
    """
    from services.product_r2_rehost import rehost_product_batch
    db = get_db()
    limit = max(1, min(int(payload.get("limit", 25)), 100))
    force = bool(payload.get("force", False))
    only_active = bool(payload.get("only_active", True))
    result = await rehost_product_batch(
        db, limit=limit, force=force, only_active=only_active,
    )
    remaining = await db.products.count_documents({
        **({"is_active": True} if only_active else {}),
        "r2_rehosted_at": {"$exists": False},
    })
    return {"ok": True, **result, "remaining": remaining}


@router.get("/admin/products/r2-rehost/status")
async def admin_products_r2_rehost_status(_admin: dict = Depends(require_admin)):
    """Progress meter for the rehost job — for the admin dashboard."""
    from services.r2_storage import storage_status
    db = get_db()
    total = await db.products.count_documents({"is_active": True})
    rehosted = await db.products.count_documents({
        "is_active": True, "r2_rehosted_at": {"$exists": True},
    })
    failed = await db.products.count_documents({
        "is_active": True, "r2_rehost_failed_at": {"$exists": True},
    })
    return {
        "storage": storage_status(),
        "total_active": total,
        "rehosted": rehosted,
        "failed": failed,
        "remaining": max(0, total - rehosted),
        "pct_complete": round(100.0 * rehosted / total, 1) if total else 100.0,
    }
