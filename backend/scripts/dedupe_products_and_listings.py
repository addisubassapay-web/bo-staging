"""Deduplicate the product catalog + marketplace listings.

Problem: over successive Apify runs (and imports from seller stores) the
same real product ended up in multiple `products` rows and multiple
`listings` rows. The mirror sync then multiplied them again.

Strategy:
  Pass 1 (products): group by `title` — keep the newest row, delete the
    rest. Also point any `listings.imported_from_id` that referenced a
    deleted product at the surviving row so mirror listings stay linked.

  Pass 2 (listings): group by `(title, seller_id)` — keep the newest,
    remove the rest. This nukes triplicate Eddy-Boss BIODANCE rows.

  Pass 3 (cross-seller dedupe): for every title, if a seller-owned
    listing exists, DELETE the Mercari Store mirror. Peer-to-peer
    sellers get priority since they add trust + variety.

Usage:
    python scripts/dedupe_products_and_listings.py            # dry-run
    python scripts/dedupe_products_and_listings.py --execute
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from motor.motor_asyncio import AsyncIOMotorClient


async def dedupe_products(db, execute: bool) -> int:
    """Collapse duplicate product rows by title. Newest wins."""
    products = await db.products.find(
        {"is_active": True},
        {"_id": 0, "id": 1, "title": 1, "created_at": 1, "updated_at": 1},
    ).to_list(50_000)
    by_title: dict = defaultdict(list)
    for p in products:
        t = (p.get("title") or "").strip().lower()
        if t:
            by_title[t].append(p)

    delete_ids: list = []
    remap: dict = {}  # deleted_id -> kept_id
    for _title, group in by_title.items():
        if len(group) < 2:
            continue
        group.sort(key=lambda x: x.get("created_at") or x.get("updated_at") or "", reverse=True)
        kept = group[0]
        for old in group[1:]:
            delete_ids.append(old["id"])
            remap[old["id"]] = kept["id"]

    print(f"[products] duplicate rows to delete: {len(delete_ids)}")
    if execute and delete_ids:
        # Repoint any listing.imported_from_id to the kept product id
        for old_id, new_id in remap.items():
            await db.listings.update_many(
                {"imported_from_id": old_id},
                {"$set": {"imported_from_id": new_id}},
            )
        # Delete the duplicate products
        await db.products.delete_many({"id": {"$in": delete_ids}})
    return len(delete_ids)


async def dedupe_same_seller_listings(db, execute: bool) -> int:
    """Collapse (title, seller_id) duplicates in listings."""
    active = await db.listings.find(
        {"status": "active"},
        {"_id": 0, "id": 1, "title": 1, "seller_id": 1, "created_at": 1},
    ).to_list(100_000)
    groups: dict = defaultdict(list)
    for l in active:
        key = ((l.get("title") or "").strip().lower(), l.get("seller_id"))
        if key[0] and key[1]:
            groups[key].append(l)

    delete_ids: list = []
    for _key, group in groups.items():
        if len(group) < 2:
            continue
        group.sort(key=lambda x: x.get("created_at") or "", reverse=True)
        for old in group[1:]:
            delete_ids.append(old["id"])

    print(f"[listings same-seller] duplicates to delete: {len(delete_ids)}")
    if execute and delete_ids:
        await db.listings.delete_many({"id": {"$in": delete_ids}})
    return len(delete_ids)


async def dedupe_cross_seller_mirror(db, execute: bool) -> int:
    """When a peer-to-peer seller listing already exists for a title,
    delete the Mercari Store mirror. Peer listings add trust/variety."""
    merchari = await db.users.find_one({"username": "mercari_store"})
    if not merchari:
        print("[mirror] mercari_store seller not found — skipping")
        return 0

    # Collect all non-Mercari active titles
    peer_titles: set = set()
    async for l in db.listings.find(
        {"status": "active", "seller_id": {"$ne": merchari["id"]}},
        {"_id": 0, "title": 1},
    ):
        t = (l.get("title") or "").strip().lower()
        if t:
            peer_titles.add(t)

    # Mercari mirrors that share a title with a peer seller
    delete_ids: list = []
    async for l in db.listings.find(
        {"seller_id": merchari["id"], "status": "active"},
        {"_id": 0, "id": 1, "title": 1},
    ):
        if (l.get("title") or "").strip().lower() in peer_titles:
            delete_ids.append(l["id"])

    print(f"[mirror] Mercari duplicates of peer listings to remove: {len(delete_ids)}")
    if execute and delete_ids:
        # Soft-remove so future mirror syncs don't re-recreate them
        await db.listings.update_many(
            {"id": {"$in": delete_ids}},
            {"$set": {"status": "removed"}},
        )
    return len(delete_ids)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()

    print(f"\nMode: {'EXECUTE' if args.execute else 'DRY-RUN'}\n{'=' * 40}")
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    p = await dedupe_products(db, args.execute)
    l = await dedupe_same_seller_listings(db, args.execute)
    m = await dedupe_cross_seller_mirror(db, args.execute)

    if args.execute:
        active_listings = await db.listings.count_documents({"status": "active"})
        active_products = await db.products.count_documents({"is_active": True})
        print(f"\n[after]  active listings: {active_listings}   active products: {active_products}")

    print(f"\nDone. products removed={p}  same-seller listings removed={l}  mirror-dupes removed={m}")


if __name__ == "__main__":
    asyncio.run(main())
