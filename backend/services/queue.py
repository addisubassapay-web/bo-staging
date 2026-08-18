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

from services.zyte import extract_product, extract_product_list, normalize_product, normalize_product_list_item, ZyteError
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

        # Optional auto-publish (no-op unless job.auto_publish + category_id).
        try:
            await _publish_from_result(db, {**job, "id": job_id}, listing)
        except Exception:
            logger.exception("auto-publish crashed")

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
    """Turn a completed scrape into a live listing under the pre-chosen
    category. No-op if required fields are missing or category is invalid."""
    if not job.get("auto_publish") or not job.get("category_id") or not job.get("owner_id"):
        return
    title = (listing.get("title") or "").strip()
    price = listing.get("price")
    if not title or price is None:
        # Can't publish without a title + price — leave as extracted-only.
        await db.scraper_jobs.update_one(
            {"id": job["id"]},
            {"$set": {"publish_status": "skipped_missing_fields"}},
        )
        return

    cat = await db.categories.find_one({"id": job["category_id"]}, {"_id": 0})
    if not cat:
        await db.scraper_jobs.update_one(
            {"id": job["id"]},
            {"$set": {"publish_status": "skipped_bad_category"}},
        )
        return

    owner = await db.users.find_one({"id": job["owner_id"]}, {"_id": 0, "password_hash": 0})
    if not owner:
        return

    # Import the Listing model lazily to avoid circulars at module import time.
    from server import Listing, ensure_store_for_user

    store = None
    if not owner.get("store_id"):
        try:
            store = await ensure_store_for_user(owner["id"])
        except Exception:
            store = None
    store_id = owner.get("store_id") or (store or {}).get("id")

    doc = Listing(
        seller_id=owner["id"],
        seller_name=owner.get("username") or owner.get("email", "seller"),
        title=title[:200],
        description=(listing.get("description") or title)[:5000],
        price=float(price),
        category_id=cat["id"],
        category_name=cat["name"],
        condition="new",
        brand=(listing.get("brand") or "")[:80],
        images=(listing.get("images") or [])[:8],
        shipping_paid_by="seller",
        shipping_method="Standard",
        status="active",
        store_id=store_id,
    )
    try:
        await db.listings.insert_one(doc.model_dump())
        await db.scraper_jobs.update_one(
            {"id": job["id"]},
            {"$set": {"publish_status": "published", "published_listing_id": doc.id}},
        )
    except Exception as e:
        logger.exception("failed to publish scraped listing")
        await db.scraper_jobs.update_one(
            {"id": job["id"]},
            {"$set": {"publish_status": f"failed:{e}"}},
        )


# --- Enqueue helper ------------------------------------------------------
async def enqueue_scrape(job_id: str) -> None:
    pool = await create_pool(_redis_settings())
    try:
        await pool.enqueue_job("scrape_url_task", job_id, _job_id=f"scrape:{job_id}")
    finally:
        await pool.close()


async def scrape_category_task(ctx: dict, super_batch_id: str) -> dict:
    """Fetch a category / search URL via Zyte productList and fan out into
    a set of `scraper_jobs` rows (one per product) with pre-extracted data.

    Because productList already returns name/price/image, we mark each row
    as `status='done'` immediately and (optionally) auto-publish, avoiding
    a second Zyte round-trip per product.
    """
    db = _db()
    batch = await db.scraper_batches.find_one({"id": super_batch_id}, {"_id": 0})
    if not batch:
        return {"ok": False, "error": "batch vanished"}

    url = batch["source_url"]
    started = datetime.now(timezone.utc)
    await db.scraper_batches.update_one(
        {"id": super_batch_id},
        {"$set": {"status": "running", "started_at": started}},
    )
    try:
        payload = await extract_product_list(
            url,
            geolocation=batch.get("geolocation") or None,
            high_fidelity=bool(batch.get("high_fidelity")),
        )
        items = payload.get("productList", {}).get("products") or payload.get("products") or []
    except ZyteError as e:
        await db.scraper_batches.update_one(
            {"id": super_batch_id},
            {"$set": {"status": "failed", "error": {"status": e.status, "detail": e.detail},
                      "finished_at": datetime.now(timezone.utc)}},
        )
        return {"ok": False, "status": e.status}
    except Exception as e:
        logger.exception("scrape_category_task crashed")
        await db.scraper_batches.update_one(
            {"id": super_batch_id},
            {"$set": {"status": "failed", "error": {"message": str(e)},
                      "finished_at": datetime.now(timezone.utc)}},
        )
        return {"ok": False, "error": str(e)}

    now = datetime.now(timezone.utc)
    created = 0
    from uuid import uuid4
    for item in items:
        listing = normalize_product_list_item(item, source_url=url)
        if not listing.get("title") or listing.get("price") is None:
            continue
        # Rehost images
        listing["images"] = await rehost_many(listing.get("images") or [], prefix="scraper_list")
        job = {
            "id": str(uuid4()),
            "owner_id": batch["owner_id"],
            "owner_email": batch.get("owner_email"),
            "url": listing.get("url") or url,
            "batch_id": super_batch_id,
            "category_id": batch.get("category_id"),
            "auto_publish": bool(batch.get("auto_publish")),
            "high_fidelity": bool(batch.get("high_fidelity")),
            "status": "done",
            "provider": "zyte",
            "result": {"listing": listing, "extracted_at": now, "provider": "zyte"},
            "error": None,
            "created_at": now,
            "updated_at": now,
            "attempts": 1,
        }
        await db.scraper_jobs.insert_one(job)
        # Auto-publish inline (still respects auto_publish + category_id).
        try:
            await _publish_from_result(db, job, listing)
        except Exception:
            logger.exception("auto-publish crashed inside category task")
        created += 1

    await db.scraper_batches.update_one(
        {"id": super_batch_id},
        {"$set": {"status": "done", "finished_at": datetime.now(timezone.utc), "total": created}},
    )
    return {"ok": True, "created": created}


async def enqueue_category(super_batch_id: str) -> None:
    pool = await create_pool(_redis_settings())
    try:
        await pool.enqueue_job("scrape_category_task", super_batch_id, _job_id=f"catlist:{super_batch_id}")
    finally:
        await pool.close()


# --- Worker settings -----------------------------------------------------
class WorkerSettings:
    functions = [scrape_url_task, scrape_category_task]
    redis_settings = _redis_settings()
    max_jobs = 5
    job_timeout = 180
    keep_result = 300
