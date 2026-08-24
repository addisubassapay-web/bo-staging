"""Runtime mirror: keep the `listings` collection in sync with `products`.

Called at the tail of every webhook ingest so newly-added or updated
Apify products show up on the marketplace `/search` page immediately
(they'd otherwise only be visible on the separate /products catalog).

The one-shot backfill lives in `scripts/sync_products_to_listings.py` —
this module is the small idempotent version that runs after every
ingest. Both reuse the same shaping logic to avoid drift.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Dict, List

from pymongo import UpdateOne

MERCHARI_SELLER_USERNAME = "merchari_store"
MERCHARI_SELLER_DISPLAY = "Merchari Store"


async def _ensure_merchari_seller(db) -> dict:
    seller = await db.users.find_one({"username": MERCHARI_SELLER_USERNAME})
    if seller:
        return seller
    now = datetime.now(timezone.utc)
    seller = {
        "id": str(uuid.uuid4()),
        "username": MERCHARI_SELLER_USERNAME,
        "display_name": MERCHARI_SELLER_DISPLAY,
        "email": "store@merchari.local",
        "role": "seller",
        "seller_status": "active",
        "email_verified": True,
        "wallet_balance": 0.0,
        "wallet_frozen_balance": 0.0,
        "created_at": now,
        "protected": True,
    }
    await db.users.insert_one(seller)
    return seller


async def _category_lookup(db) -> Dict[str, dict]:
    out: Dict[str, dict] = {}
    async for c in db.categories.find({}, {"_id": 0, "id": 1, "name": 1, "slug": 1}):
        if c.get("slug"):
            out[c["slug"].lower()] = c
        if c.get("name"):
            out[c["name"].lower()] = c
    return out


def _shape(product: dict, seller: dict, cats: Dict[str, dict], now: datetime) -> dict:
    cat_name = product.get("category") or "Home"
    slug = cat_name.lower()
    cat = cats.get(slug) or {}
    in_stock = product.get("in_stock", True)
    return {
        "seller_id": seller["id"],
        "seller_name": seller["display_name"],
        "title": product.get("title", ""),
        "description": product.get("description", ""),
        "price": float(product.get("price") or 0),
        "category_id": cat.get("id") or slug,
        "category_name": cat.get("name") or cat_name,
        "condition": "new",
        "brand": "",
        "size": "",
        "color": "",
        "images": product.get("images", []) or [],
        "shipping_paid_by": "seller",
        "shipping_method": "Standard",
        "status": "active" if in_stock else "reserved",
        "featured": False,
        "imported_from_id": product["id"],
        "updated_at": now,
    }


async def mirror_products_to_listings(db) -> dict:
    """Idempotent mirror. Returns {created, updated, removed}."""
    seller = await _ensure_merchari_seller(db)
    cats = await _category_lookup(db)

    products = await db.products.find({"is_active": True}, {"_id": 0}).to_list(50_000)

    existing: Dict[str, dict] = {}
    async for d in db.listings.find(
        {"seller_id": seller["id"]},
        {"_id": 0, "id": 1, "imported_from_id": 1, "price": 1, "title": 1,
         "status": 1, "images": 1},
    ):
        if d.get("imported_from_id"):
            existing[d["imported_from_id"]] = d

    now = datetime.now(timezone.utc)
    ops: List[UpdateOne] = []
    created = 0
    updated = 0

    for p in products:
        target = _shape(p, seller, cats, now)
        prev = existing.pop(p["id"], None)
        if prev:
            if (
                prev.get("price") != target["price"]
                or prev.get("title") != target["title"]
                or prev.get("status") != target["status"]
                or prev.get("images") != target["images"]
            ):
                ops.append(UpdateOne({"id": prev["id"]}, {"$set": target}))
                updated += 1
        else:
            new_doc = {
                **target,
                "id": str(uuid.uuid4()),
                "created_at": now,
                "likes_count": 0,
                "views_count": 0,
            }
            ops.append(UpdateOne(
                {"imported_from_id": p["id"], "seller_id": seller["id"]},
                {"$setOnInsert": new_doc},
                upsert=True,
            ))
            created += 1

    removed = 0
    for orphan in existing.values():
        if orphan.get("status") != "removed":
            ops.append(UpdateOne(
                {"id": orphan["id"]},
                {"$set": {"status": "removed", "updated_at": now}},
            ))
            removed += 1

    if ops:
        for i in range(0, len(ops), 500):
            await db.listings.bulk_write(ops[i:i + 500], ordered=False)

    return {"created": created, "updated": updated, "removed": removed}
