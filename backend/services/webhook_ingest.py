"""Async Apify webhook ingest — handled by the arq worker so the HTTP endpoint
can return 200 immediately even when Apify hands us a 4,500-item dataset.

The public entry points are:
  - `ingest_items_sync(db, items)` — runs the upsert loop in-process (used
    by the small-payload synchronous path so the counters returned by the
    webhook stay meaningful for tests/one-off pushes).
  - `webhook_ingest_task(ctx, kind, payload)` — the arq task. `kind` is
    either "items" (payload is a list) or "dataset" (payload is an Apify
    default dataset id).

Progress is written to `apify_ingest_state` (id = job_id) so the admin
dashboard / operator curl can poll status.
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

# Ensure the worker process has env vars even if arq spawned before .env load.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import UpdateOne

from routers.products import _iter_apify_items, _normalize_product  # reuse parsers

logger = logging.getLogger("webhook_ingest")

CHUNK = 500  # products upserted per bulk_write


def _worker_db():
    """Motor DB handle for the arq worker process."""
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    return client[os.environ["DB_NAME"]]


async def _update_state(db, job_id: str, patch: Dict[str, Any]) -> None:
    patch = {**patch, "updated_at": datetime.now(timezone.utc)}
    await db.apify_ingest_state.update_one(
        {"id": job_id}, {"$set": patch, "$setOnInsert": {"id": job_id}}, upsert=True
    )


async def _upsert_chunk(db, chunk: List[Dict[str, Any]]) -> Dict[str, int]:
    """Upsert a batch of normalized products. Returns per-batch counters.

    Uses two passes so we can distinguish inserts from updates:
      1. Look up which upsert keys already exist.
      2. bulk_write UpdateOne(upsert=True) for the whole batch.

    Stock-state handling:
      • Insert: `is_active = in_stock` — OOS items land inactive so they
        don't leak onto the storefront.
      • Update: if an item flips from OOS -> in-stock, we auto-reactivate.
        If it flips the other way, we leave `is_active` untouched (an admin
        may want to keep the tile visible with a "sold out" badge).
    """
    if not chunk:
        return {"created": 0, "updated": 0, "reactivated": 0}

    now = datetime.now(timezone.utc)
    sku_keys = [c["sku"] for c in chunk if c.get("sku")]
    url_keys = [c["source_url"] for c in chunk if not c.get("sku") and c.get("source_url")]

    existing_by_sku: Dict[str, Dict[str, Any]] = {}
    existing_by_url: Dict[str, Dict[str, Any]] = {}
    if sku_keys:
        async for d in db.products.find(
            {"sku": {"$in": sku_keys}}, {"_id": 0, "sku": 1, "in_stock": 1, "is_active": 1}
        ):
            if d.get("sku"):
                existing_by_sku[d["sku"]] = d
    if url_keys:
        async for d in db.products.find(
            {"source_url": {"$in": url_keys}}, {"_id": 0, "source_url": 1, "in_stock": 1, "is_active": 1}
        ):
            if d.get("source_url"):
                existing_by_url[d["source_url"]] = d

    ops: List[UpdateOne] = []
    created = 0
    updated = 0
    reactivated = 0
    for norm in chunk:
        in_stock = bool(norm.get("in_stock"))
        if norm.get("sku"):
            key = {"sku": norm["sku"]}
            existing = existing_by_sku.get(norm["sku"])
        else:
            key = {"source_url": norm["source_url"]}
            existing = existing_by_url.get(norm["source_url"])

        set_doc = {**norm, "updated_at": now}

        # OOS-badge policy: OOS products stay visible on the storefront so
        # shoppers see restock candidates. We track availability via
        # `in_stock` on the product doc; the tile renders a
        # "Currently Unavailable" badge when it's false. `is_active` is
        # reserved for admin-controlled catalog hides.
        if existing and in_stock and not existing.get("is_active"):
            # Legacy items that were auto-deactivated by the earlier logic
            # come back online the moment we see them back in stock.
            set_doc["is_active"] = True
            reactivated += 1

        ops.append(
            UpdateOne(
                key,
                {
                    "$set": set_doc,
                    "$setOnInsert": {
                        "id": str(uuid.uuid4()),
                        "created_at": now,
                        # NEW inserts always land visible — the OOS badge on
                        # the tile is the source of truth for availability.
                        "is_active": True,
                    },
                },
                upsert=True,
            )
        )
        if existing:
            updated += 1
        else:
            created += 1

    await db.products.bulk_write(ops, ordered=False)
    return {"created": created, "updated": updated, "reactivated": reactivated}


async def ingest_items(
    db,
    items: List[Dict[str, Any]],
    job_id: Optional[str] = None,
) -> Dict[str, int]:
    """Normalize + chunk-upsert. Writes progress every chunk if job_id given."""
    total = len(items)
    created = 0
    updated = 0
    skipped = 0
    reactivated = 0
    oos_ingested = 0
    processed = 0

    if job_id:
        await _update_state(db, job_id, {
            "status": "running",
            "total": total,
            "created": 0,
            "updated": 0,
            "skipped": 0,
            "reactivated": 0,
            "oos_ingested": 0,
            "processed": 0,
            "started_at": datetime.now(timezone.utc),
        })

    buf: List[Dict[str, Any]] = []
    for raw in items:
        norm = _normalize_product(raw)
        if not norm:
            skipped += 1
            processed += 1
            continue
        if not norm.get("in_stock"):
            oos_ingested += 1
        buf.append(norm)
        processed += 1
        if len(buf) >= CHUNK:
            counts = await _upsert_chunk(db, buf)
            created += counts["created"]
            updated += counts["updated"]
            reactivated += counts.get("reactivated", 0)
            buf = []
            if job_id:
                await _update_state(db, job_id, {
                    "processed": processed,
                    "created": created,
                    "updated": updated,
                    "skipped": skipped,
                    "reactivated": reactivated,
                    "oos_ingested": oos_ingested,
                })

    if buf:
        counts = await _upsert_chunk(db, buf)
        created += counts["created"]
        updated += counts["updated"]
        reactivated += counts.get("reactivated", 0)

    result = {
        "received": total,
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "reactivated": reactivated,
        "oos_ingested": oos_ingested,
    }
    if job_id:
        await _update_state(db, job_id, {
            **result,
            "processed": total,
            "status": "done",
            "finished_at": datetime.now(timezone.utc),
        })
    logger.info(f"[webhook-ingest] job={job_id} {result}")

    # Mirror newly-ingested / updated products into the marketplace
    # `listings` collection so the /search page picks them up
    # automatically. This is a fire-and-forget — the ingest is already
    # done for the caller's contract, and the mirror is idempotent so a
    # missed run is self-healed on the next ingest.
    try:
        from services.listing_mirror import mirror_products_to_listings
        mirror_stats = await mirror_products_to_listings(db)
        logger.info(f"[webhook-ingest] mirror {mirror_stats}")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[webhook-ingest] mirror step failed (non-fatal): {e}")

    return result


def _fetch_dataset_items_sync(dataset_id: str) -> List[Dict[str, Any]]:
    """Blocking dataset fetch — called from run_in_executor inside the task."""
    from apify_client import ApifyClient
    tokens = [os.environ.get("APIFY_TOKEN"), os.environ.get("APIFY_TOKEN_FALLBACK")]
    tokens = [t for t in tokens if t]
    if not tokens:
        raise RuntimeError("No APIFY_TOKEN configured")
    last_err: Optional[Exception] = None
    for tok in tokens:
        try:
            client = ApifyClient(tok)
            return list(client.dataset(dataset_id).iterate_items())
        except Exception as e:  # noqa: BLE001
            last_err = e
            logger.warning(f"[webhook-ingest] dataset fetch failed with token: {e}")
            continue
    raise RuntimeError(f"All Apify tokens failed: {last_err}")


async def webhook_ingest_task(ctx: dict, kind: str, payload: Any, job_id: str) -> dict:
    """arq entry point. Never raises — persists errors to `apify_ingest_state`.

    kind = "items"    → `payload` is a list of raw items
    kind = "dataset"  → `payload` is a dataset_id string; fetch from Apify
    """
    import asyncio
    db = _worker_db()
    try:
        if kind == "dataset":
            await _update_state(db, job_id, {
                "status": "fetching",
                "kind": "dataset",
                "dataset_id": payload,
                "started_at": datetime.now(timezone.utc),
            })
            loop = asyncio.get_event_loop()
            items = await loop.run_in_executor(None, _fetch_dataset_items_sync, payload)
        else:
            items = list(payload or [])
            await _update_state(db, job_id, {
                "status": "queued",
                "kind": "items",
                "queued_items": len(items),
                "started_at": datetime.now(timezone.utc),
            })

        result = await ingest_items(db, items, job_id=job_id)
        return {"ok": True, **result}
    except Exception as e:  # noqa: BLE001
        logger.exception(f"[webhook-ingest] task {job_id} failed")
        await _update_state(db, job_id, {
            "status": "failed",
            "error": str(e),
            "finished_at": datetime.now(timezone.utc),
        })
        return {"ok": False, "error": str(e)}
