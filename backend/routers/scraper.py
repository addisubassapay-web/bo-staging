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
from services.queue import enqueue_scrape
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
        "auto_publish": bool(payload.auto_publish),
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
