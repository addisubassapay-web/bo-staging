"""Denormalize the permanent product catalog into marketplace listings.

Why: the storefront's `/search` and homepage read from `listings`, but our
Apify-scraped catalog lived in `products`. Shoppers were only seeing the
1,179 peer-to-peer listings — the 4,500+ catalog products were tucked
away on `/products` where most visitors never went.

Strategy:
  1. Ensure a synthetic seller `mercari_store` exists (admin-owned so
     wallet/escrow logic still resolves).
  2. Upsert one `listings` doc per active product, keyed by
     `imported_from_id = product.id`. Idempotent — re-running only
     touches products we haven't mirrored yet or whose price/stock
     changed.
  3. Update on price/stock/title change; DELETE (soft-set status=removed)
     for products that no longer exist so the marketplace stays in sync.

Usage:
    python scripts/sync_products_to_listings.py             # dry-run
    python scripts/sync_products_to_listings.py --execute
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import UpdateOne

MERCHARI_SELLER_USERNAME = "mercari_store"
MERCHARI_SELLER_DISPLAY = "Mercarie Store"

# Canonical product category -> (category_id, category_name) tuples used
# on listings. Category IDs are looked up dynamically so we tolerate any
# admin re-slugging.
CATEGORY_MAP: Dict[str, str] = {
    "Women": "women",
    "Men": "men",
    "Kids": "kids",
    "Electronics": "electronics",
    "Home": "home",
    "Beauty": "beauty",
    "Sports": "sports",
    "Toys": "toys",
    "Books": "books",
    "Handmade": "handmade",
}


async def ensure_merchari_seller(db) -> dict:
    """Idempotently create the platform-owned seller account used to own
    every mirrored listing. Marked so it can never be deleted by cleanups."""
    seller = await db.users.find_one({"username": MERCHARI_SELLER_USERNAME})
    if seller:
        return seller
    now = datetime.now(timezone.utc)
    seller = {
        "id": str(uuid.uuid4()),
        "username": MERCHARI_SELLER_USERNAME,
        "display_name": MERCHARI_SELLER_DISPLAY,
        "email": "store@mercari.local",
        "role": "seller",
        "seller_status": "active",
        "email_verified": True,
        "avatar": None,
        "bio": "The official Mercarie-Global catalog.",
        "wallet_balance": 0.0,
        "wallet_frozen_balance": 0.0,
        "created_at": now,
        "protected": True,  # tell cleanup scripts to skip this account
    }
    await db.users.insert_one(seller)
    return seller


async def get_category_lookup(db) -> Dict[str, dict]:
    cats: Dict[str, dict] = {}
    async for c in db.categories.find({}, {"_id": 0, "id": 1, "name": 1, "slug": 1}):
        if c.get("slug"):
            cats[c["slug"].lower()] = c
        if c.get("name"):
            cats[c["name"].lower()] = c
    return cats


def _to_listing_doc(product: dict, seller: dict, category_lookup: Dict[str, dict], now: datetime) -> dict:
    """Shape a product dict into a listings-collection doc."""
    cat_name = product.get("category") or "Home"
    slug = CATEGORY_MAP.get(cat_name, cat_name.lower())
    cat = category_lookup.get(slug) or category_lookup.get(cat_name.lower()) or {}

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
        # Products flip in/out of stock over time; when OOS we mark the
        # mirror listing "reserved" so the marketplace hides it from the
        # default "active" filter — cleaner than deleting + re-inserting.
        "status": "active" if in_stock else "reserved",
        "featured": False,
        "imported_from_id": product["id"],
        "updated_at": now,
    }


async def sync(db, execute: bool):
    seller = await ensure_merchari_seller(db)
    print(f"[seller] {seller['display_name']} (id={seller['id']})")

    category_lookup = await get_category_lookup(db)
    print(f"[cats] {len(category_lookup)} category slugs available")

    products = await db.products.find(
        {"is_active": True}, {"_id": 0}
    ).to_list(50_000)
    print(f"[products] {len(products)} active products to mirror")

    # Pre-fetch existing mirror listings keyed by imported_from_id
    existing_ids = {
        d["imported_from_id"]: d
        async for d in db.listings.find(
            {"seller_id": seller["id"]},
            {"_id": 0, "id": 1, "imported_from_id": 1, "price": 1, "title": 1,
             "status": 1, "images": 1},
        )
        if d.get("imported_from_id")
    }
    print(f"[mirror] {len(existing_ids)} existing mirror listings")

    now = datetime.now(timezone.utc)
    ops: List[UpdateOne] = []
    created = 0
    updated = 0

    for p in products:
        target = _to_listing_doc(p, seller, category_lookup, now)
        existing = existing_ids.pop(p["id"], None)
        if existing:
            # Only rewrite if something material changed
            if (
                existing.get("price") != target["price"]
                or existing.get("title") != target["title"]
                or existing.get("status") != target["status"]
                or existing.get("images") != target["images"]
            ):
                ops.append(UpdateOne(
                    {"id": existing["id"]},
                    {"$set": target},
                ))
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

    # Anything left in existing_ids is a listing whose source product was
    # deleted — soft-remove it so the storefront quits showing a dead tile.
    removed = 0
    for orphan in existing_ids.values():
        if orphan.get("status") != "removed":
            ops.append(UpdateOne(
                {"id": orphan["id"]},
                {"$set": {"status": "removed", "updated_at": now}},
            ))
            removed += 1

    print(f"[plan] created={created}  updated={updated}  removed={removed}  total_ops={len(ops)}")

    if execute and ops:
        for i in range(0, len(ops), 500):
            await db.listings.bulk_write(ops[i:i + 500], ordered=False)
        print(f"[write] committed {len(ops)} ops")

    if execute:
        total_mirrored = await db.listings.count_documents(
            {"seller_id": seller["id"], "status": "active"}
        )
        total_active_listings = await db.listings.count_documents({"status": "active"})
        print(f"\n[after]")
        print(f"    mirrored active:        {total_mirrored}")
        print(f"    total active listings:  {total_active_listings}")


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    print(f"\nMode: {'EXECUTE' if args.execute else 'DRY-RUN'}\n{'=' * 40}")
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    await sync(db, execute=args.execute)


if __name__ == "__main__":
    asyncio.run(main())
