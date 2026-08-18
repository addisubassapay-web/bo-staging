"""Saved Seeds — sellers save favorite keyword/provider combos and we
auto-run each one nightly to grow the catalog hands-free.

Backed by the same paginated scrape pipeline (`_run_saved_seed_now`) and
runs via arq's built-in cron in `services.queue.WorkerSettings.cron_jobs`.
"""
from __future__ import annotations
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("saved_seeds")


async def run_saved_seed(db, seed: dict) -> dict | None:
    """Kick off a paginated scrape for a single saved seed. Returns the
    super_batch document or None if we skipped (over quota, disabled, etc.).
    Best-effort — never raises to callers."""
    from services.quotas import get_user_cap, get_usage
    from services.queue import enqueue_category

    owner = await db.users.find_one({"id": seed["owner_id"]}, {"_id": 0, "password_hash": 0})
    if not owner:
        return None
    if not seed.get("enabled", True):
        return None

    # Respect the user's monthly Zyte quota. If they can't afford the seed's
    # pages, silently skip this run — we'll try again tomorrow.
    used = await get_usage(db, owner["id"])
    cap = await get_user_cap(db, owner)
    pages = int(seed.get("pages") or 20)
    if used + pages > cap:
        logger.info(
            "saved_seed %s skipped — quota %s+%s>%s", seed["id"], used, pages, cap,
        )
        return None

    tmpl_map = {
        "amazon_search":      "https://www.amazon.com/s?k={q}&page={p}",
        "amazon_bestsellers": "https://www.amazon.com/gp/bestsellers/{q}?pg={p}",
        "mercari_search":     "https://www.mercari.com/search/?keyword={q}&page={p}",
    }
    tmpl = tmpl_map.get(seed.get("provider") or "amazon_search")
    if not tmpl:
        return None

    q = (seed.get("query") or "").replace(" ", "+")
    now = datetime.now(timezone.utc)
    super_id = str(uuid.uuid4())
    child_ids: list[str] = []

    for page in range(1, pages + 1):
        seed_url = tmpl.format(q=q, p=page)
        child_id = str(uuid.uuid4())
        await db.scraper_batches.insert_one({
            "id": child_id,
            "owner_id": owner["id"],
            "owner_email": owner.get("email"),
            "kind": "category",
            "super_batch_id": super_id,
            "source_url": seed_url,
            "seed_provider": seed.get("provider"),
            "seed_query": seed.get("query"),
            "page": page,
            "category_id": seed.get("category_id"),
            "high_fidelity": bool(seed.get("high_fidelity")),
            "auto_publish": True,  # saved seeds always publish live
            "status": "queued",
            "total": 0,
            "created_at": now,
        })
        try:
            await enqueue_category(child_id)
            child_ids.append(child_id)
        except Exception:
            await db.scraper_batches.update_one(
                {"id": child_id},
                {"$set": {"status": "failed", "error": {"message": "enqueue failed"}}},
            )

    await db.scraper_super_batches.insert_one({
        "id": super_id,
        "owner_id": owner["id"],
        "provider": seed.get("provider"),
        "query": seed.get("query"),
        "pages": pages,
        "category_id": seed.get("category_id"),
        "auto_publish": True,
        "saved_seed_id": seed["id"],
        "child_batch_ids": child_ids,
        "created_at": now,
    })
    await db.saved_seeds.update_one(
        {"id": seed["id"]},
        {"$set": {"last_run_at": now, "last_super_batch_id": super_id}},
    )
    return {"super_batch_id": super_id, "pages_queued": len(child_ids)}


async def run_all_enabled(db) -> dict[str, Any]:
    """Cron entry point — walk every enabled saved seed and kick it off."""
    started = datetime.now(timezone.utc)
    ran = skipped = 0
    async for seed in db.saved_seeds.find({"enabled": True}):
        try:
            r = await run_saved_seed(db, seed)
            if r:
                ran += 1
            else:
                skipped += 1
        except Exception:
            logger.exception("saved seed %s crashed", seed.get("id"))
            skipped += 1
    return {
        "ran": ran, "skipped": skipped,
        "started_at": started.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }
