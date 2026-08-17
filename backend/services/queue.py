"""arq worker + enqueue helpers for the Zyte scraper pipeline.

Start the worker with:
    arq services.queue.WorkerSettings

The worker uses the same MongoDB the API talks to, so job state is fully
observable from `/api/scraper/jobs`.
"""
from __future__ import annotations
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv

# Load backend/.env so the worker picks up MONGO_URL, DB_NAME, REDIS_URL, ZYTE_API_KEY, R2_*
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from arq.connections import RedisSettings
from arq import create_pool
from motor.motor_asyncio import AsyncIOMotorClient

from services.zyte import extract_product, normalize_product, ZyteError
from services.r2_storage import rehost_many

logger = logging.getLogger("scraper_queue")


# --- Redis / DB ----------------------------------------------------------
def _redis_settings() -> RedisSettings:
    url = os.environ.get("REDIS_URL") or "redis://localhost:6379/0"
    return RedisSettings.from_dsn(url)


def _db():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    return client[os.environ["DB_NAME"]]


# --- Job task ------------------------------------------------------------
async def scrape_url_task(ctx: dict, job_id: str) -> dict:
    """Fetch a URL via Zyte, rehost images to R2, and store a listing draft.

    The `scraper_jobs` document is the single source of truth for status.
    Never raise — instead persist the error and let arq mark the job done.
    """
    db = _db()
    started = datetime.now(timezone.utc)
    await db.scraper_jobs.update_one(
        {"id": job_id},
        {"$set": {"status": "running", "started_at": started, "attempts": ctx.get("job_try", 1)}},
    )
    job = await db.scraper_jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        return {"ok": False, "error": "job vanished"}

    url = job["url"]
    try:
        payload = await extract_product(
            url,
            geolocation=job.get("geolocation") or None,
            high_fidelity=bool(job.get("high_fidelity")),
        )
        listing = normalize_product(payload)

        # Rehost images to R2 (falls back to supplier URL when R2 disabled)
        listing["images"] = await rehost_many(listing.get("images") or [], prefix="scraper")

        result = {
            "listing": listing,
            "extracted_at": datetime.now(timezone.utc),
            "provider": "zyte",
        }
        await db.scraper_jobs.update_one(
            {"id": job_id},
            {"$set": {
                "status": "done",
                "finished_at": datetime.now(timezone.utc),
                "result": result,
                "error": None,
            }},
        )
        # NOTE: Auto-publish is a next step — sellers currently review the
        # `result` object and create the Listing via the existing form
        # (which requires category selection + seller display name). Storing
        # the scraped payload is enough for the queue milestone.

        return {"ok": True, "listing_title": listing.get("title")}

    except ZyteError as e:
        await db.scraper_jobs.update_one(
            {"id": job_id},
            {"$set": {
                "status": "failed",
                "finished_at": datetime.now(timezone.utc),
                "error": {"provider": "zyte", "status": e.status, "detail": e.detail},
            }},
        )
        return {"ok": False, "status": e.status}
    except Exception as e:
        logger.exception(f"scrape_url_task crashed for job {job_id}")
        await db.scraper_jobs.update_one(
            {"id": job_id},
            {"$set": {
                "status": "failed",
                "finished_at": datetime.now(timezone.utc),
                "error": {"provider": "internal", "message": str(e)},
            }},
        )
        return {"ok": False, "error": str(e)}


async def _publish_from_result(db, job: dict, listing: dict) -> None:
    """Reserved for a follow-up — currently no-op."""
    return None


# --- Enqueue helper ------------------------------------------------------
async def enqueue_scrape(job_id: str) -> None:
    pool = await create_pool(_redis_settings())
    try:
        await pool.enqueue_job("scrape_url_task", job_id, _job_id=f"scrape:{job_id}")
    finally:
        await pool.close()


# --- Worker settings -----------------------------------------------------
class WorkerSettings:
    functions = [scrape_url_task]
    redis_settings = _redis_settings()
    max_jobs = 5
    job_timeout = 120
    keep_result = 300
