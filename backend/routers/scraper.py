"""Scraper API — POST a URL, arq extracts + rehosts, we return job status.

Endpoints:
  POST /api/scraper/jobs               — auth required; enqueue a URL
  GET  /api/scraper/jobs/{job_id}      — poll status for a specific job
  GET  /api/scraper/jobs               — list this user's recent jobs
  GET  /api/scraper/admin/jobs         — admin only; list all recent jobs
  GET  /api/scraper/status             — health probe (Zyte key set?, R2 on?, Redis reachable?)
"""
from __future__ import annotations
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .deps import get_db, get_current_user, require_admin
from services.queue import enqueue_scrape, enqueue_category
from services.r2_storage import storage_status
from services.quotas import get_status as quota_status, admin_all_usage, assert_can_spend, get_user_cap, get_usage
from services.url_safety import is_safe_public_url

router = APIRouter(prefix="/scraper", tags=["scraper"])


def _valid_url(url: str) -> bool:
    ok, _ = is_safe_public_url(url)
    return ok


def _reject_unsafe_url(url: str) -> None:
    """Raise 400 with a human-friendly reason when `url` fails SSRF checks."""
    ok, reason = is_safe_public_url(url)
    if not ok:
        raise HTTPException(400, reason or "Enter a valid http(s) URL")


class ScrapeJobCreate(BaseModel):
    url: str = Field(..., min_length=8, max_length=2048)
    auto_publish: bool = False
    geolocation: Optional[str] = None  # e.g. "US", "GB"
    high_fidelity: bool = False        # force browser rendering (paid tier)
    category_id: Optional[str] = None  # remembered for downstream publish
    batch_id: Optional[str] = None


class BulkScrapeCreate(BaseModel):
    urls: list[str] = Field(..., min_length=1, max_length=500)
    category_id: Optional[str] = None
    auto_publish: bool = False
    geolocation: Optional[str] = None
    high_fidelity: bool = False


class CategoryScrapeCreate(BaseModel):
    url: str = Field(..., min_length=8, max_length=2048)
    category_id: Optional[str] = None
    auto_publish: bool = False
    geolocation: Optional[str] = None
    high_fidelity: bool = False


@router.post("/jobs")
async def create_scrape_job(payload: ScrapeJobCreate, user: dict = Depends(get_current_user)):
    _reject_unsafe_url(payload.url)
    if not (os.environ.get("ZYTE_API_KEY") or "").strip():
        raise HTTPException(503, "Zyte API key is not configured")
    db = get_db()
    # Dedupe: don't burn a credit if this seller already imported this URL.
    dup = await db.listings.find_one(
        {"seller_id": user["id"], "source_url": payload.url},
        {"_id": 0, "id": 1},
    )
    if dup:
        raise HTTPException(409, {"detail": "already_imported", "listing_id": dup["id"]})
    await assert_can_spend(db, user, cost=1)
    job_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    doc = {
        "id": job_id,
        "owner_id": user["id"],
        "owner_email": user.get("email"),
        "url": payload.url,
        "geolocation": payload.geolocation,
        "high_fidelity": bool(payload.high_fidelity),
        "auto_publish": bool(payload.auto_publish),
        "category_id": payload.category_id,
        "batch_id": payload.batch_id,
        "status": "queued",
        "provider": "zyte",
        "result": None,
        "error": None,
        "created_at": now,
        "updated_at": now,
        "attempts": 0,
    }
    await db.scraper_jobs.insert_one(doc)
    try:
        await enqueue_scrape(job_id)
    except Exception as e:
        await db.scraper_jobs.update_one(
            {"id": job_id},
            {"$set": {"status": "failed", "error": {"provider": "queue", "message": str(e)}}},
        )
        raise HTTPException(503, f"Queue unavailable: {e}")
    return {"id": job_id, "status": "queued", "url": payload.url}


@router.post("/jobs/bulk")
async def create_bulk_scrape(payload: BulkScrapeCreate, user: dict = Depends(get_current_user)):
    """Enqueue up to 20 URLs at once with a shared category + batch id.
    Bad URLs are rejected upfront; the response reports which ones queued."""
    if not (os.environ.get("ZYTE_API_KEY") or "").strip():
        raise HTTPException(503, "Zyte API key is not configured")
    if payload.auto_publish and not payload.category_id:
        raise HTTPException(400, "Auto-publish requires a category_id")

    db = get_db()
    if payload.category_id:
        cat = await db.categories.find_one({"id": payload.category_id}, {"_id": 0})
        if not cat:
            raise HTTPException(400, "Invalid category_id")

    valid: list[str] = []
    rejected: list[dict] = []
    seen: set[str] = set()
    for u in payload.urls:
        u = (u or "").strip()
        if not u:
            continue
        if u in seen:
            rejected.append({"url": u, "reason": "duplicate"})
            continue
        seen.add(u)
        if not _valid_url(u):
            rejected.append({"url": u, "reason": "invalid_url"})
        else:
            valid.append(u)

    if not valid:
        raise HTTPException(400, "No valid URLs provided")

    # Dedupe against listings the same user has already published from these
    # supplier URLs — prevents wasted Zyte credits + duplicate storefronts.
    db_dedupe = get_db()
    already = await db_dedupe.listings.distinct(
        "source_url", {"seller_id": user["id"], "source_url": {"$in": valid}}
    )
    if already:
        already_set = set(already)
        for u in list(valid):
            if u in already_set:
                rejected.append({"url": u, "reason": "already_imported"})
        valid = [u for u in valid if u not in already_set]
    if not valid:
        raise HTTPException(400, "All URLs were already imported by you")

    # Pre-flight: refuse if the batch would blow the monthly cap.
    db_check = get_db()
    await assert_can_spend(db_check, user, cost=len(valid))

    db = get_db()
    batch_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    queued: list[dict] = []

    for url in valid:
        job_id = str(uuid.uuid4())
        doc = {
            "id": job_id,
            "owner_id": user["id"],
            "owner_email": user.get("email"),
            "url": url,
            "geolocation": payload.geolocation,
            "high_fidelity": bool(payload.high_fidelity),
            "auto_publish": bool(payload.auto_publish),
            "category_id": payload.category_id,
            "batch_id": batch_id,
            "status": "queued",
            "provider": "zyte",
            "result": None,
            "error": None,
            "created_at": now,
            "updated_at": now,
            "attempts": 0,
        }
        await db.scraper_jobs.insert_one(doc)
        try:
            await enqueue_scrape(job_id)
            queued.append({"id": job_id, "url": url})
        except Exception as e:
            await db.scraper_jobs.update_one(
                {"id": job_id},
                {"$set": {"status": "failed", "error": {"provider": "queue", "message": str(e)}}},
            )
            rejected.append({"url": url, "reason": f"queue_error: {e}"})

    await db.scraper_batches.insert_one({
        "id": batch_id,
        "owner_id": user["id"],
        "category_id": payload.category_id,
        "high_fidelity": bool(payload.high_fidelity),
        "total": len(queued),
        "created_at": now,
    })
    return {
        "batch_id": batch_id,
        "queued_count": len(queued),
        "queued": queued,
        "rejected": rejected,
    }


@router.post("/jobs/category")
async def create_category_scrape(payload: CategoryScrapeCreate, user: dict = Depends(get_current_user)):
    """Fan-out one Zyte productList call into many pre-extracted job rows.
    Point it at an Amazon search page, an eBay category, a Shopify collection,
    etc. and Zyte returns 30-100 products in a single call. When
    `auto_publish=true` + `category_id` is set, each product goes live
    immediately under that category."""
    _reject_unsafe_url(payload.url)
    if not (os.environ.get("ZYTE_API_KEY") or "").strip():
        raise HTTPException(503, "Zyte API key is not configured")
    if payload.auto_publish and not payload.category_id:
        raise HTTPException(400, "Auto-publish requires a category_id")

    db = get_db()
    await assert_can_spend(db, user, cost=1)
    if payload.category_id:
        cat = await db.categories.find_one({"id": payload.category_id}, {"_id": 0})
        if not cat:
            raise HTTPException(400, "Invalid category_id")

    now = datetime.now(timezone.utc)
    batch_id = str(uuid.uuid4())
    await db.scraper_batches.insert_one({
        "id": batch_id,
        "owner_id": user["id"],
        "owner_email": user.get("email"),
        "kind": "category",
        "source_url": payload.url,
        "category_id": payload.category_id,
        "high_fidelity": bool(payload.high_fidelity),
        "auto_publish": bool(payload.auto_publish),
        "geolocation": payload.geolocation,
        "status": "queued",
        "total": 0,
        "created_at": now,
    })
    try:
        await enqueue_category(batch_id)
    except Exception as e:
        await db.scraper_batches.update_one(
            {"id": batch_id}, {"$set": {"status": "failed", "error": {"message": str(e)}}},
        )
        raise HTTPException(503, f"Queue unavailable: {e}")
    return {"batch_id": batch_id, "status": "queued", "kind": "category"}


class CsvScrapeCreate(BaseModel):
    urls: list[str] = Field(..., min_length=1, max_length=1000)
    category_id: Optional[str] = None
    auto_publish: bool = False
    high_fidelity: bool = False


@router.post("/jobs/csv")
async def create_csv_scrape(payload: CsvScrapeCreate, user: dict = Depends(get_current_user)):
    """Ingest a CSV / spreadsheet paste — up to 1,000 URLs per request.
    Internally reuses the same enqueue path as /jobs/bulk so each URL gets
    a full /product extract via arq. Response mirrors /jobs/bulk."""
    if not (os.environ.get("ZYTE_API_KEY") or "").strip():
        raise HTTPException(503, "Zyte API key is not configured")
    if payload.auto_publish and not payload.category_id:
        raise HTTPException(400, "Auto-publish requires a category_id")

    db = get_db()
    if payload.category_id:
        cat = await db.categories.find_one({"id": payload.category_id}, {"_id": 0})
        if not cat:
            raise HTTPException(400, "Invalid category_id")

    valid: list[str] = []
    rejected: list[dict] = []
    seen: set[str] = set()
    for u in payload.urls:
        u = (u or "").strip()
        if not u or u in seen:
            if u in seen:
                rejected.append({"url": u, "reason": "duplicate"})
            continue
        seen.add(u)
        if not _valid_url(u):
            rejected.append({"url": u, "reason": "invalid_url"})
        else:
            valid.append(u)

    if not valid:
        raise HTTPException(400, "No valid URLs provided")

    batch_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    queued: list[dict] = []
    for url in valid:
        job_id = str(uuid.uuid4())
        doc = {
            "id": job_id,
            "owner_id": user["id"],
            "owner_email": user.get("email"),
            "url": url,
            "geolocation": None,
            "high_fidelity": bool(payload.high_fidelity),
            "auto_publish": bool(payload.auto_publish),
            "category_id": payload.category_id,
            "batch_id": batch_id,
            "status": "queued",
            "provider": "zyte",
            "result": None,
            "error": None,
            "created_at": now,
            "updated_at": now,
            "attempts": 0,
        }
        await db.scraper_jobs.insert_one(doc)
        try:
            await enqueue_scrape(job_id)
            queued.append({"id": job_id, "url": url})
        except Exception as e:
            await db.scraper_jobs.update_one(
                {"id": job_id},
                {"$set": {"status": "failed", "error": {"provider": "queue", "message": str(e)}}},
            )
            rejected.append({"url": url, "reason": f"queue_error: {e}"})

    await db.scraper_batches.insert_one({
        "id": batch_id,
        "owner_id": user["id"],
        "kind": "csv",
        "category_id": payload.category_id,
        "auto_publish": bool(payload.auto_publish),
        "high_fidelity": bool(payload.high_fidelity),
        "total": len(queued),
        "created_at": now,
    })
    return {
        "batch_id": batch_id,
        "queued_count": len(queued),
        "queued": queued,
        "rejected": rejected,
    }


@router.get("/batches/{batch_id}")
async def get_batch_status(batch_id: str, user: dict = Depends(get_current_user)):
    """Aggregate status for a bulk import batch."""
    db = get_db()
    batch = await db.scraper_batches.find_one({"id": batch_id}, {"_id": 0})
    if not batch:
        raise HTTPException(404, "Batch not found")
    if batch.get("owner_id") != user["id"] and user.get("role") != "admin":
        raise HTTPException(403, "Not your batch")
    jobs = await db.scraper_jobs.find(
        {"batch_id": batch_id}, {"_id": 0}
    ).sort("created_at", 1).to_list(200)
    counts = {"queued": 0, "running": 0, "done": 0, "failed": 0}
    for j in jobs:
        counts[j.get("status", "queued")] = counts.get(j.get("status", "queued"), 0) + 1
    return {"batch": batch, "jobs": jobs, "counts": counts, "total": len(jobs)}


@router.get("/jobs/{job_id}")
async def get_scrape_job(job_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    doc = await db.scraper_jobs.find_one({"id": job_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Job not found")
    if doc.get("owner_id") != user["id"] and user.get("role") != "admin":
        raise HTTPException(403, "Not your job")
    return doc


@router.get("/jobs")
async def list_my_scrape_jobs(user: dict = Depends(get_current_user), limit: int = 50):
    db = get_db()
    docs = await db.scraper_jobs.find(
        {"owner_id": user["id"]}, {"_id": 0}
    ).sort("created_at", -1).limit(max(1, min(limit, 200))).to_list(200)
    return {"items": docs, "count": len(docs)}


@router.get("/admin/jobs")
async def admin_list_scrape_jobs(_admin: dict = Depends(require_admin), status: Optional[str] = None, limit: int = 100):
    db = get_db()
    q: dict = {}
    if status:
        q["status"] = status
    docs = await db.scraper_jobs.find(q, {"_id": 0}).sort("created_at", -1).limit(max(1, min(limit, 500))).to_list(500)
    return {"items": docs, "count": len(docs)}


@router.get("/status")
async def scraper_status(_admin: dict = Depends(require_admin)):
    """Health probe surfaced in the admin dashboard."""
    zyte_ok = bool((os.environ.get("ZYTE_API_KEY") or "").strip())
    redis_url = os.environ.get("REDIS_URL") or "redis://localhost:6379/0"
    redis_ok = False
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(redis_url)
        pong = await r.ping()
        redis_ok = bool(pong)
        await r.close()
    except Exception:
        redis_ok = False
    return {
        "zyte": {"enabled": zyte_ok},
        "queue": {"provider": "arq", "redis_ok": redis_ok, "redis_url": redis_url.split("@")[-1]},
        "storage": storage_status(),
    }


# =========================================================================
# Paginated seed scraper — Amazon + Ocean at scale
# =========================================================================
_SEED_TEMPLATES = {
    "amazon_search":  "https://www.amazon.com/s?k={q}&page={p}",
    "mercari-global_search": "https://www.mercari-global.com/search/?keyword={q}&page={p}",
    "amazon_bestsellers": "https://www.amazon.com/gp/bestsellers/{q}?pg={p}",
}


class PaginatedSeedCreate(BaseModel):
    provider: str = Field(..., description="amazon_search | mercari-global_search | amazon_bestsellers")
    query: str = Field(..., min_length=1, max_length=200)
    pages: int = Field(5, ge=1, le=50, description="How many pages to walk")
    category_id: Optional[str] = None
    auto_publish: bool = False
    high_fidelity: bool = False


@router.post("/jobs/paginated")
async def create_paginated_scrape(payload: PaginatedSeedCreate, user: dict = Depends(get_current_user)):
    """Walk N pages of a supplier search / bestseller listing at once.

    Each page fires one Zyte `productList` call and typically returns
    30-60 products, so 10 pages ≈ 300-600 live listings for 10 credits.
    Ideal for burning the $100 Zyte plan into the maximum number of
    marketplace listings.
    """
    if payload.provider not in _SEED_TEMPLATES:
        raise HTTPException(400, f"Unknown provider — choose one of {list(_SEED_TEMPLATES)}")
    if payload.auto_publish and not payload.category_id:
        raise HTTPException(400, "Auto-publish requires a category_id")
    if not (os.environ.get("ZYTE_API_KEY") or "").strip():
        raise HTTPException(503, "Zyte API key is not configured")

    db = get_db()
    # 1 credit per page.
    await assert_can_spend(db, user, cost=payload.pages)
    if payload.category_id:
        cat = await db.categories.find_one({"id": payload.category_id}, {"_id": 0})
        if not cat:
            raise HTTPException(400, "Invalid category_id")

    tmpl = _SEED_TEMPLATES[payload.provider]
    q = payload.query.replace(" ", "+")
    now = datetime.now(timezone.utc)
    super_id = str(uuid.uuid4())
    child_batch_ids: list[str] = []

    for page in range(1, payload.pages + 1):
        seed_url = tmpl.format(q=q, p=page)
        child_id = str(uuid.uuid4())
        await db.scraper_batches.insert_one({
            "id": child_id,
            "owner_id": user["id"],
            "owner_email": user.get("email"),
            "kind": "category",
            "super_batch_id": super_id,
            "source_url": seed_url,
            "seed_provider": payload.provider,
            "seed_query": payload.query,
            "page": page,
            "category_id": payload.category_id,
            "high_fidelity": bool(payload.high_fidelity),
            "auto_publish": bool(payload.auto_publish),
            "status": "queued",
            "total": 0,
            "created_at": now,
        })
        try:
            await enqueue_category(child_id)
            child_batch_ids.append(child_id)
        except Exception as e:
            await db.scraper_batches.update_one(
                {"id": child_id}, {"$set": {"status": "failed", "error": {"message": str(e)}}},
            )

    await db.scraper_super_batches.insert_one({
        "id": super_id,
        "owner_id": user["id"],
        "provider": payload.provider,
        "query": payload.query,
        "pages": payload.pages,
        "category_id": payload.category_id,
        "auto_publish": bool(payload.auto_publish),
        "child_batch_ids": child_batch_ids,
        "created_at": now,
    })
    return {
        "super_batch_id": super_id,
        "provider": payload.provider,
        "pages_queued": len(child_batch_ids),
        "child_batch_ids": child_batch_ids,
    }


@router.get("/super-batches/{super_batch_id}")
async def get_super_batch_status(super_batch_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    sb = await db.scraper_super_batches.find_one({"id": super_batch_id}, {"_id": 0})
    if not sb:
        raise HTTPException(404, "Super-batch not found")
    if sb.get("owner_id") != user["id"] and user.get("role") != "admin":
        raise HTTPException(403, "Not your batch")
    children = await db.scraper_batches.find(
        {"super_batch_id": super_batch_id}, {"_id": 0}
    ).sort("page", 1).to_list(200)
    # Aggregate stats across all child jobs.
    child_ids = [c["id"] for c in children]
    products_total = 0
    products_published = 0
    if child_ids:
        products_total = await db.scraper_jobs.count_documents({"batch_id": {"$in": child_ids}})
        products_published = await db.scraper_jobs.count_documents(
            {"batch_id": {"$in": child_ids}, "publish_status": "published"}
        )
    done_pages = sum(1 for c in children if c.get("status") == "done")
    failed_pages = sum(1 for c in children if c.get("status") == "failed")
    return {
        "super_batch": sb,
        "children": children,
        "pages_done": done_pages,
        "pages_failed": failed_pages,
        "pages_total": len(children),
        "products_total": products_total,
        "products_published": products_published,
    }


# =========================================================================
# Best Sellers Rotation — weekly re-check + demotion of stale imports
# =========================================================================
@router.get("/best-sellers/status")
async def best_sellers_status(user: dict = Depends(get_current_user)):
    """Small dashboard payload: last cron run + this user's demoted count."""
    db = get_db()
    last = await db.best_sellers_runs.find_one({}, {"_id": 0}, sort=[("finished_at", -1)])
    demoted = await db.listings.count_documents({"seller_id": user["id"], "demoted": True})
    eligible = await db.listings.count_documents(
        {"seller_id": user["id"], "source_url": {"$ne": None}}
    )
    return {
        "last_run": last,
        "your_demoted": demoted,
        "your_eligible": eligible,
        "drift_threshold_pct": 15,
        "cron": "weekly Monday 08:00 UTC",
    }


@router.post("/best-sellers/refresh")
async def best_sellers_refresh_now(user: dict = Depends(get_current_user), limit: int = 20):
    """Manual re-check of the caller's top-N (default 20) auto-imports.
    Costs 1 Zyte credit per listing checked."""
    from services.best_sellers import refresh_user_top_listings
    limit = max(1, min(int(limit), 100))
    db = get_db()
    await assert_can_spend(db, user, cost=limit)
    return await refresh_user_top_listings(db, user, limit=limit)


@router.get("/demoted")
async def list_demoted(user: dict = Depends(get_current_user)):
    """Listings this user has that were demoted by the rotation."""
    db = get_db()
    rows = await db.listings.find(
        {"seller_id": user["id"], "demoted": True},
        {"_id": 0, "id": 1, "title": 1, "price": 1, "supplier_last_price": 1,
         "demoted_reason": 1, "source_url": 1, "images": 1,
         "last_supplier_check_at": 1, "category_name": 1},
    ).sort("last_supplier_check_at", -1).to_list(200)
    return {"items": rows, "count": len(rows)}


class RestoreListing(BaseModel):
    new_price: Optional[float] = Field(None, gt=0)


@router.post("/demoted/{listing_id}/restore")
async def restore_demoted(listing_id: str, payload: RestoreListing, user: dict = Depends(get_current_user)):
    """Un-demote a listing (optionally updating its price to the new supplier
    price). Sets status back to 'active' and clears the demoted flag."""
    db = get_db()
    row = await db.listings.find_one({"id": listing_id, "seller_id": user["id"]}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Listing not found")
    update = {
        "demoted": False,
        "demoted_reason": None,
        "status": "active",
    }
    if payload.new_price:
        update["previous_price"] = float(row.get("price") or 0)
        update["price"] = float(payload.new_price)
    await db.listings.update_one({"id": listing_id}, {"$set": update})
    return {"ok": True, "listing_id": listing_id, **update}


@router.post("/demoted/bulk-restore")
async def bulk_restore_demoted(user: dict = Depends(get_current_user)):
    """One-click restore-all for every demoted listing this user owns. Each
    listing's price is set to its `supplier_last_price` (when available);
    listings without a fresh supplier price are restored at their old price."""
    db = get_db()
    rows = await db.listings.find(
        {"seller_id": user["id"], "demoted": True},
        {"_id": 0, "id": 1, "price": 1, "supplier_last_price": 1, "demoted_reason": 1},
    ).to_list(500)
    restored = repriced = skipped = 0
    for row in rows:
        # Skip 'supplier_gone' rows — they'd 404 for buyers.
        if row.get("demoted_reason") == "supplier_gone":
            skipped += 1
            continue
        update = {"demoted": False, "demoted_reason": None, "status": "active"}
        if row.get("supplier_last_price"):
            update["previous_price"] = float(row.get("price") or 0)
            update["price"] = float(row["supplier_last_price"])
            repriced += 1
        await db.listings.update_one({"id": row["id"]}, {"$set": update})
        restored += 1
    return {"restored": restored, "repriced": repriced, "skipped_gone": skipped}


# =========================================================================
# Seed Analytics — per-seed history and conversion metrics
# =========================================================================
@router.get("/saved-seeds/{seed_id}/analytics")
async def seed_analytics(seed_id: str, user: dict = Depends(get_current_user)):
    """Aggregate stats across every super-batch this saved seed has produced.
    Returns totals, averages, and the last N run records for a mini-chart."""
    db = get_db()
    seed = await db.saved_seeds.find_one({"id": seed_id}, {"_id": 0})
    if not seed:
        raise HTTPException(404, "Saved seed not found")
    if seed["owner_id"] != user["id"] and user.get("role") != "admin":
        raise HTTPException(403, "Not your seed")

    supers = await db.scraper_super_batches.find(
        {"saved_seed_id": seed_id}, {"_id": 0}
    ).sort("created_at", -1).to_list(50)

    runs = []
    total_products = 0
    total_published = 0
    total_credits = 0
    for sb in supers:
        child_ids = sb.get("child_batch_ids") or []
        prods = await db.scraper_jobs.count_documents({"batch_id": {"$in": child_ids}}) if child_ids else 0
        pub = await db.scraper_jobs.count_documents(
            {"batch_id": {"$in": child_ids}, "publish_status": "published"}
        ) if child_ids else 0
        credits = int(sb.get("pages") or len(child_ids))
        total_products += prods
        total_published += pub
        total_credits += credits
        runs.append({
            "super_batch_id": sb["id"],
            "created_at": sb.get("created_at"),
            "pages": sb.get("pages"),
            "products_extracted": prods,
            "products_published": pub,
            "credits_spent": credits,
        })
    n = max(1, len(supers))
    return {
        "seed": seed,
        "runs": runs,
        "totals": {
            "runs": len(supers),
            "products_extracted": total_products,
            "products_published": total_published,
            "credits_spent": total_credits,
        },
        "averages": {
            "products_per_run": round(total_products / n, 1),
            "published_per_run": round(total_published / n, 1),
            "credits_per_run": round(total_credits / n, 1),
            "live_conversion_pct": round((total_published / total_products) * 100, 1) if total_products else 0.0,
        },
    }


# =========================================================================
# Suggest Keywords — AI-generated seed ideas for seller's top categories
# =========================================================================
@router.get("/suggest-keywords")
async def suggest_keywords(user: dict = Depends(get_current_user)):
    """Emergent-LLM-backed keyword suggestions grouped by the seller's top
    categories. Falls back to a curated preset when the LLM is unavailable so
    the button never returns empty."""
    db = get_db()
    # Find the user's top 3 categories by listing count.
    pipeline = [
        {"$match": {"seller_id": user["id"], "status": "active"}},
        {"$group": {"_id": {"id": "$category_id", "name": "$category_name"}, "n": {"$sum": 1}}},
        {"$sort": {"n": -1}},
        {"$limit": 3},
    ]
    top = await db.listings.aggregate(pipeline).to_list(3)
    if not top:
        # Cold-start fallback — use platform-wide top categories.
        cat_docs = await db.categories.find({}, {"_id": 0, "id": 1, "name": 1}).limit(3).to_list(3)
        top = [{"_id": {"id": c["id"], "name": c["name"]}, "n": 0} for c in cat_docs]

    groups: list[dict] = []
    llm_ok = False
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        import uuid as _uuid
        key = os.environ.get("EMERGENT_LLM_KEY") or ""
        if key:
            chat = LlmChat(
                api_key=key,
                session_id=f"kw-{_uuid.uuid4()}",
                system_message=(
                    "You are a marketplace SEO expert. Given a category name, "
                    "suggest exactly 5 short (1-4 word) high-signal buyer search "
                    "keywords for Amazon-style sourcing. Reply as a JSON array of strings only, no prose."
                ),
            ).with_model("openai", "gpt-4o-mini")
            import json as _json
            for c in top:
                cat_name = c["_id"]["name"]
                reply = await chat.send_message(UserMessage(text=f"Category: {cat_name}"))
                text = str(reply).strip()
                # Extract JSON array — model sometimes wraps in code fences.
                if "```" in text:
                    text = text.split("```")[1].lstrip("json").strip()
                try:
                    kws = _json.loads(text)
                    kws = [str(k).strip() for k in kws if str(k).strip()][:5]
                except Exception:
                    kws = []
                if kws:
                    groups.append({"category_id": c["_id"]["id"], "category_name": cat_name, "keywords": kws})
            llm_ok = bool(groups)
    except Exception:
        llm_ok = False

    if not llm_ok:
        # Curated fallback per top category (still useful, no LLM needed).
        fallback = {
            "Electronics": ["wireless earbuds", "smart watch", "portable charger", "led strip lights", "phone tripod"],
            "Fashion": ["vintage denim", "graphic tee", "sneakers", "gold chain", "leather bag"],
            "Home": ["desk lamp", "kitchen organizer", "throw blanket", "candle set", "wall art"],
            "Beauty": ["face serum", "makeup brushes", "hair curler", "nail kit", "skincare set"],
            "Toys": ["lego set", "board game", "stuffed animal", "rc car", "puzzle 1000"],
        }
        for c in top:
            name = c["_id"]["name"]
            kws = fallback.get(name) or fallback.get(name.split()[0]) or ["trending gift", "under $25", "best seller", "gift for her", "gift for him"]
            groups.append({"category_id": c["_id"]["id"], "category_name": name, "keywords": kws})

    return {"groups": groups, "llm_ok": llm_ok}


# =========================================================================
# Saved Seeds — persist favorite keywords + nightly auto-run
# =========================================================================
class SavedSeedCreate(BaseModel):
    provider: str = Field(..., description="amazon_search | mercari-global_search | amazon_bestsellers")
    query: str = Field(..., min_length=1, max_length=200)
    pages: int = Field(20, ge=1, le=50)
    category_id: str
    high_fidelity: bool = False
    enabled: bool = True


class SavedSeedUpdate(BaseModel):
    query: Optional[str] = Field(None, min_length=1, max_length=200)
    pages: Optional[int] = Field(None, ge=1, le=50)
    category_id: Optional[str] = None
    high_fidelity: Optional[bool] = None
    enabled: Optional[bool] = None


@router.post("/saved-seeds")
async def create_saved_seed(payload: SavedSeedCreate, user: dict = Depends(get_current_user)):
    if payload.provider not in _SEED_TEMPLATES:
        raise HTTPException(400, f"Unknown provider — choose one of {list(_SEED_TEMPLATES)}")
    db = get_db()
    cat = await db.categories.find_one({"id": payload.category_id}, {"_id": 0})
    if not cat:
        raise HTTPException(400, "Invalid category_id")
    now = datetime.now(timezone.utc)
    doc = {
        "id": str(uuid.uuid4()),
        "owner_id": user["id"],
        "provider": payload.provider,
        "query": payload.query,
        "pages": payload.pages,
        "category_id": payload.category_id,
        "high_fidelity": bool(payload.high_fidelity),
        "enabled": bool(payload.enabled),
        "created_at": now,
        "last_run_at": None,
        "last_super_batch_id": None,
    }
    await db.saved_seeds.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.get("/saved-seeds")
async def list_saved_seeds(user: dict = Depends(get_current_user)):
    db = get_db()
    rows = await db.saved_seeds.find(
        {"owner_id": user["id"]}, {"_id": 0}
    ).sort("created_at", -1).to_list(200)
    return {"items": rows, "count": len(rows)}


@router.patch("/saved-seeds/{seed_id}")
async def update_saved_seed(seed_id: str, payload: SavedSeedUpdate, user: dict = Depends(get_current_user)):
    db = get_db()
    seed = await db.saved_seeds.find_one({"id": seed_id}, {"_id": 0})
    if not seed:
        raise HTTPException(404, "Saved seed not found")
    if seed["owner_id"] != user["id"] and user.get("role") != "admin":
        raise HTTPException(403, "Not your seed")
    updates = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    if updates.get("category_id"):
        cat = await db.categories.find_one({"id": updates["category_id"]}, {"_id": 0})
        if not cat:
            raise HTTPException(400, "Invalid category_id")
    if updates:
        await db.saved_seeds.update_one({"id": seed_id}, {"$set": updates})
    return await db.saved_seeds.find_one({"id": seed_id}, {"_id": 0})


@router.delete("/saved-seeds/{seed_id}")
async def delete_saved_seed(seed_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    seed = await db.saved_seeds.find_one({"id": seed_id}, {"_id": 0, "owner_id": 1})
    if not seed:
        raise HTTPException(404, "Saved seed not found")
    if seed["owner_id"] != user["id"] and user.get("role") != "admin":
        raise HTTPException(403, "Not your seed")
    await db.saved_seeds.delete_one({"id": seed_id})
    return {"ok": True}


@router.post("/saved-seeds/{seed_id}/run")
async def run_saved_seed_now(seed_id: str, user: dict = Depends(get_current_user)):
    """Trigger a saved seed manually — same as the nightly cron for one row."""
    from services.saved_seeds import run_saved_seed as _run
    db = get_db()
    seed = await db.saved_seeds.find_one({"id": seed_id}, {"_id": 0})
    if not seed:
        raise HTTPException(404, "Saved seed not found")
    if seed["owner_id"] != user["id"] and user.get("role") != "admin":
        raise HTTPException(403, "Not your seed")
    # Enforce quota inline so callers see 429 instead of a silent skip.
    await assert_can_spend(db, user, cost=int(seed.get("pages") or 20))
    result = await _run(db, seed)
    if not result:
        raise HTTPException(400, "Seed could not run (disabled or invalid).")
    return result


# =========================================================================
# Per-user Zyte quotas
# =========================================================================
@router.get("/quota")
async def my_quota(user: dict = Depends(get_current_user)):
    """Current-month Zyte credit usage for the calling user."""
    db = get_db()
    return await quota_status(db, user)


@router.get("/admin/quota")
async def admin_quota_list(_admin: dict = Depends(require_admin), month: Optional[str] = None):
    """All users' Zyte usage this month + their effective cap."""
    db = get_db()
    rows = await admin_all_usage(db, month=month)
    global_cap = None
    s = await db.settings.find_one({"id": "global"}, {"_id": 0, "zyte_monthly_cap_per_user": 1})
    if s and isinstance(s.get("zyte_monthly_cap_per_user"), (int, float)):
        global_cap = int(s["zyte_monthly_cap_per_user"])
    return {"rows": rows, "global_cap": global_cap or 500}


class QuotaOverrideUpdate(BaseModel):
    user_id: str
    cap: Optional[int] = Field(None, ge=0, le=1_000_000, description="0/null = clear override")


@router.post("/admin/quota/override")
async def admin_set_override(payload: QuotaOverrideUpdate, _admin: dict = Depends(require_admin)):
    """Set a per-user override. Cap=None or 0 clears the override so the
    user falls back to the global default."""
    db = get_db()
    if payload.cap and payload.cap > 0:
        await db.users.update_one({"id": payload.user_id}, {"$set": {"zyte_monthly_cap": int(payload.cap)}})
    else:
        await db.users.update_one({"id": payload.user_id}, {"$unset": {"zyte_monthly_cap": ""}})
    return {"ok": True, "user_id": payload.user_id, "cap": payload.cap or None}


class GlobalCapUpdate(BaseModel):
    cap: int = Field(..., ge=1, le=1_000_000)


@router.post("/admin/quota/global-cap")
async def admin_set_global_cap(payload: GlobalCapUpdate, _admin: dict = Depends(require_admin)):
    db = get_db()
    await db.settings.update_one(
        {"id": "global"},
        {"$set": {"zyte_monthly_cap_per_user": int(payload.cap)}},
        upsert=True,
    )
    return {"ok": True, "cap": int(payload.cap)}
