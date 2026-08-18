"""Best Sellers Rotation — weekly re-check of a seller's top-100
auto-imported listings.

Rules:
    - Only listings with a `source_url` (Zyte-imported) qualify.
    - We re-fetch each source via Zyte (`extract_product`) and compare price.
    - Price drift ≥ 15% (up or down) → demote with reason='supplier_price_shift'.
    - Zyte returns empty title/price → demote with reason='supplier_gone'.
    - Otherwise the listing keeps ticking; we record `last_supplier_check_at`
      and `supplier_last_price` for auditing / analytics.
    - Each re-check costs 1 Zyte credit; enforced through the same quota
      pipeline so it never surprises the seller with a bill.
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Any

from services.zyte import extract_product, normalize_product, ZyteError
from services.quotas import get_usage, get_user_cap, record_spend

logger = logging.getLogger("best_sellers")

DRIFT_THRESHOLD = 0.15   # 15%
TOP_N = 100


async def refresh_user_top_listings(db, user: dict, *, limit: int = TOP_N) -> dict:
    """Re-check up to `limit` of the user's live imports. Returns a summary.
    Best-effort — silently skips items when the user's quota can't cover them.
    """
    cursor = db.listings.find(
        {"seller_id": user["id"], "status": "active", "source_url": {"$ne": None}},
        {"_id": 0, "id": 1, "price": 1, "source_url": 1},
    ).sort([("views_count", -1), ("likes_count", -1)]).limit(limit)
    listings = await cursor.to_list(limit)

    demoted_price = demoted_gone = checked = skipped_quota = 0
    for row in listings:
        used = await get_usage(db, user["id"])
        cap = await get_user_cap(db, user)
        if used >= cap:
            skipped_quota += 1
            continue
        try:
            payload = await extract_product(row["source_url"])
            await record_spend(db, user["id"], cost=1)
        except ZyteError:
            continue
        except Exception:
            logger.exception("supplier recheck crashed for %s", row["id"])
            continue

        prod = normalize_product(payload)
        checked += 1
        new_price = prod.get("price")
        new_title = prod.get("title") or ""
        now = datetime.now(timezone.utc)

        # Supplier removed / bot-blocked → treat as gone.
        if not new_title and new_price is None:
            await db.listings.update_one(
                {"id": row["id"]},
                {"$set": {
                    "demoted": True,
                    "demoted_reason": "supplier_gone",
                    "status": "removed",
                    "last_supplier_check_at": now,
                }},
            )
            demoted_gone += 1
            continue

        # Price drift check.
        old = float(row["price"])
        if new_price is not None and old > 0:
            drift = abs(float(new_price) - old) / old
            if drift >= DRIFT_THRESHOLD:
                await db.listings.update_one(
                    {"id": row["id"]},
                    {"$set": {
                        "demoted": True,
                        "demoted_reason": "supplier_price_shift",
                        "status": "removed",
                        "supplier_last_price": float(new_price),
                        "last_supplier_check_at": now,
                    }},
                )
                demoted_price += 1
                continue

        # Everything fine — just bookmark the check.
        await db.listings.update_one(
            {"id": row["id"]},
            {"$set": {
                "last_supplier_check_at": now,
                "supplier_last_price": float(new_price) if new_price is not None else None,
            }},
        )

    return {
        "checked": checked,
        "demoted_price": demoted_price,
        "demoted_gone": demoted_gone,
        "skipped_quota": skipped_quota,
        "total_eligible": len(listings),
    }


async def refresh_all_users(db) -> dict:
    """Cron entry point — walk every seller who has imported listings."""
    started = datetime.now(timezone.utc)
    seller_ids = await db.listings.distinct(
        "seller_id",
        {"status": "active", "source_url": {"$ne": None}},
    )
    totals = {"users": 0, "checked": 0, "demoted_price": 0, "demoted_gone": 0}
    for sid in seller_ids:
        user = await db.users.find_one({"id": sid}, {"_id": 0, "password_hash": 0})
        if not user:
            continue
        try:
            r = await refresh_user_top_listings(db, user)
            totals["users"] += 1
            totals["checked"] += r["checked"]
            totals["demoted_price"] += r["demoted_price"]
            totals["demoted_gone"] += r["demoted_gone"]
        except Exception:
            logger.exception("best sellers refresh crashed for user %s", sid)
    totals["started_at"] = started.isoformat()
    totals["finished_at"] = datetime.now(timezone.utc).isoformat()
    # Persist a run summary so the widget can show "Last rotation ..." data.
    await db.best_sellers_runs.insert_one({**totals})
    return totals
