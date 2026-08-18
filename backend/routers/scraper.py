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
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .deps import get_db, get_current_user, require_admin
from services.queue import enqueue_scrape, enqueue_category
from services.r2_storage import storage_status

router = APIRouter(prefix="/scraper", tags=["scraper"])


def _valid_url(url: str) -> bool:
    try:
        u = urlparse(url)
        return u.scheme in ("http", "https") and bool(u.netloc)
    except Exception:
        return False


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
    if not _valid_url(payload.url):
        raise HTTPException(400, "Enter a valid http(s) URL")
    if not (os.environ.get("ZYTE_API_KEY") or "").strip():
        raise HTTPException(503, "Zyte API key is not configured")

    db = get_db()
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
    if not _valid_url(payload.url):
        raise HTTPException(400, "Enter a valid http(s) URL")
    if not (os.environ.get("ZYTE_API_KEY") or "").strip():
        raise HTTPException(503, "Zyte API key is not configured")
    if payload.auto_publish and not payload.category_id:
        raise HTTPException(400, "Auto-publish requires a category_id")

    db = get_db()
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
