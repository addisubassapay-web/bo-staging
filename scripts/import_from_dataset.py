"""Import listings from an already-completed Apify dataset (no new credits burned).

Usage:
    python /app/scripts/import_from_dataset.py <dataset_id>
"""
import asyncio
import os
import sys
from typing import Dict, List

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from apify_client import ApifyClient

# Reuse the transformation helpers from apify_sync
sys.path.insert(0, "/app/backend")
from apify_sync import _build_listing  # type: ignore

load_dotenv("/app/backend/.env")


# Map Amazon breadcrumb keywords → our category slugs (same as apify_sync CATEGORY_URLS)
BREADCRUMB_MAP: List[tuple[str, str]] = [
    ("boys",              "kids"),
    ("girls",             "kids"),
    ("baby",              "kids"),
    ("toys",              "toys"),
    ("games",             "toys"),
    ("women",             "women"),
    ("men",               "men"),
    ("beauty",            "beauty"),
    ("makeup",            "beauty"),
    ("skin care",         "beauty"),
    ("electronics",       "electronics"),
    ("computers",         "electronics"),
    ("cell phones",       "electronics"),
    ("camera",            "electronics"),
    ("headphones",        "electronics"),
    ("sports",            "sports"),
    ("outdoors",          "sports"),
    ("fitness",           "sports"),
    ("home",              "home"),
    ("kitchen",           "home"),
    ("furniture",         "home"),
    ("bed",               "home"),
    ("garden",            "home"),
    ("books",             "books"),
    ("handmade",          "handmade"),
]


def _classify(item: Dict, slugs_by_key: Dict[str, Dict]) -> Dict:
    crumbs = (item.get("breadCrumbs") or "").lower()
    for needle, slug in BREADCRUMB_MAP:
        if needle in crumbs and slug in slugs_by_key:
            return slugs_by_key[slug]
    return slugs_by_key.get("other") or next(iter(slugs_by_key.values()))


async def main(dataset_id: str) -> None:
    client = ApifyClient(os.environ["APIFY_TOKEN"])
    mongo = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = mongo[os.environ["DB_NAME"]]

    info = client.dataset(dataset_id).get()
    total = info.item_count if info else 0
    print(f"Dataset {dataset_id}: {total} items available")

    cats = {c["slug"]: c for c in await db.categories.find({}, {"_id": 0}).to_list(200)}
    sellers = await db.users.find({"role": "user"}, {"_id": 0, "id": 1, "username": 1}).to_list(200)
    if not cats or not sellers:
        print("ERROR: run POST /api/seed first — need categories and demo sellers.")
        return

    to_insert: List[Dict] = []
    per_cat: Dict[str, int] = {}
    seen_asins: set[str] = set()

    for idx, item in enumerate(client.dataset(dataset_id).iterate_items()):
        asin = item.get("asin")
        if asin and asin in seen_asins:
            continue
        if asin:
            seen_asins.add(asin)
        cat = _classify(item, cats)
        if not cat:
            continue
        seller = sellers[idx % len(sellers)]
        listing = _build_listing(item, cat, seller)
        if not listing:
            continue
        to_insert.append(listing)
        per_cat[cat["slug"]] = per_cat.get(cat["slug"], 0) + 1
        if idx % 200 == 0:
            print(f"  processed {idx}, built {len(to_insert)} listings so far")

    print(f"\nBuilt {len(to_insert)} listings from {total} raw items")
    if not to_insert:
        return

    # Wipe existing catalog and replace with real Amazon data
    d1 = await db.listings.delete_many({})
    d2 = await db.favorites.delete_many({})
    d3 = await db.cart_items.delete_many({})
    print(f"Wiped listings={d1.deleted_count} favorites={d2.deleted_count} cart={d3.deleted_count}")

    # Chunked insert
    for i in range(0, len(to_insert), 500):
        chunk = to_insert[i : i + 500]
        await db.listings.insert_many(chunk)
        print(f"  inserted {i + len(chunk)}/{len(to_insert)}")

    # Update sync_state so status card shows real numbers
    from datetime import datetime, timezone

    await db.sync_state.update_one(
        {"id": "apify"},
        {
            "$set": {
                "last_sync_at": datetime.now(timezone.utc),
                "sync_running": False,
                "imported_count": len(to_insert),
                "raw_items": total,
                "per_category": per_cat,
                "message": f"Imported {len(to_insert)} real Amazon products from dataset {dataset_id}.",
            }
        },
        upsert=True,
    )

    print(f"\n✅ Done — {len(to_insert)} real Amazon listings live.")
    print(f"Per-category: {dict(sorted(per_cat.items(), key=lambda x: -x[1]))}")


if __name__ == "__main__":
    ds = sys.argv[1] if len(sys.argv) > 1 else "4l18Zx7sRwgZJBbBy"
    asyncio.run(main(ds))
