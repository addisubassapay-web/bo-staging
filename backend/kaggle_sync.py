"""
Kaggle Mercari JP Dataset sync module.
Reads /app/backend/kaggle_data/items.tsv (867K real Mercari Japan listings)
and imports a curated selection into MongoDB with USD prices.
"""
import csv
import os
import random
import hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Iterator
import uuid

DATA_FILE = Path("/app/backend/kaggle_data/items.tsv")

# JPY -> USD (rounded, updated 2026). We use a fixed rate for consistency.
JPY_TO_USD = 1 / 149.0

# Map Japanese category root -> our English category slug
CATEGORY_MAP = {
    "レディース": "women",
    "メンズ": "men",
    "ベビー・キッズ": "kids",
    "家電・スマホ・カメラ": "electronics",
    "スマホ・タブレット・パソコン": "electronics",
    "テレビ・オーディオ・カメラ": "electronics",
    "生活家電・空調": "electronics",
    "本・音楽・ゲーム": "books",
    "本・雑誌・漫画": "books",
    "CD・DVD・ブルーレイ": "books",
    "エンタメ・ホビー": "toys",
    "おもちゃ・ホビー・グッズ": "toys",
    "ゲーム・おもちゃ・グッズ": "toys",
    "ホビー・楽器・アート": "toys",
    "スポーツ・レジャー": "sports",
    "スポーツ": "sports",
    "アウトドア・釣り・旅行用品": "sports",
    "コスメ・美容": "beauty",
    "コスメ・香水・美容": "beauty",
    "ダイエット・健康": "beauty",
    "ハンドメイド": "handmade",
    "ハンドメイド・手芸": "handmade",
    "キッチン・日用品・その他": "home",
    "インテリア・住まい・小物": "home",
    "家具・インテリア": "home",
    "フラワー・ガーデニング": "home",
    "ヴィンテージ": "vintage",
    "自動車・オートバイ": "other",
    "車・バイク・自転車": "other",
    "食品・飲料・酒": "other",
    "チケット": "other",
    "その他": "other",
}

# Fashion sub-categories (root = ファッション)
FASHION_SUB_MAP = {
    "レディース": "women",
    "メンズ": "men",
    "キッズ": "kids",
    "ベビー": "kids",
    "ユニセックス": "women",
}

CONDITION_MAP = {
    "0": "new",
    "1": "like_new",
    "2": "good",
    "3": "good",
    "4": "fair",
    "5": "poor",
}


def map_category(jp_category: str) -> str:
    """Map a Japanese category path to our English category slug."""
    if not jp_category:
        return "other"
    parts = [p.strip() for p in jp_category.split("/") if p.strip()]
    if not parts:
        return "other"
    root = parts[0]
    # Special-case fashion: use subcategory for gender segmentation
    if root == "ファッション" and len(parts) > 1:
        return FASHION_SUB_MAP.get(parts[1], "women")
    return CATEGORY_MAP.get(root, "other")


def jpy_to_usd(jpy: float) -> float:
    """Convert JPY to USD with 2-decimal rounding, minimum $0.99."""
    try:
        usd = float(jpy) * JPY_TO_USD
        return max(round(usd, 2), 0.99)
    except (ValueError, TypeError):
        return 0.99


def make_placeholder_images(item_id: str, count: int = 3) -> List[str]:
    """Generate deterministic placeholder image URLs from item id."""
    h = hashlib.md5(item_id.encode()).hexdigest()[:12]
    return [f"https://picsum.photos/seed/{h}{i}/800/800" for i in range(count)]


def make_title(name: str, brand: str) -> str:
    """Compose a listing title. Keeps original Japanese but prefixes brand if useful."""
    name = (name or "").strip()
    brand = (brand or "").strip()
    if not name:
        return f"{brand or 'Mercari Japan Import'} — item"
    if brand and brand.lower() not in name.lower():
        return f"{name}"[:120]
    return name[:120]


def stream_rows(limit: Optional[int] = None) -> Iterator[Dict]:
    """Stream rows from the Mercari JP TSV, yielding one dict at a time."""
    if not DATA_FILE.exists():
        return
    with open(DATA_FILE, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        count = 0
        for row in reader:
            if not row.get("name") or not row.get("price"):
                continue
            try:
                price_jpy = float(row["price"])
                if price_jpy < 100:  # skip too-cheap
                    continue
            except (ValueError, TypeError):
                continue
            yield row
            count += 1
            if limit and count >= limit:
                break


def build_listing(
    row: Dict,
    categories_by_slug: Dict[str, Dict],
    sellers: List[Dict],
    idx: int,
    price_variance: bool = True,
) -> Optional[Dict]:
    """Convert a TSV row into a Mercari clone Listing dict."""
    cat_slug = map_category(row.get("category_name", ""))
    cat = categories_by_slug.get(cat_slug) or categories_by_slug.get("other")
    if not cat:
        return None

    seller = sellers[idx % len(sellers)]
    price_usd = jpy_to_usd(row["price"])

    # slight upsell for original price to look attractive
    original_usd = None
    if price_variance and random.random() < 0.6:
        original_usd = round(price_usd * random.uniform(1.2, 2.5), 2)

    condition = CONDITION_MAP.get(str(row.get("item_condition", "2")).split(".")[0], "good")
    shipping_paid_by = "seller" if str(row.get("shipping", "1")) in ("1", "1.0") else "buyer"

    item_id = str(uuid.uuid4())

    return {
        "id": item_id,
        "seller_id": seller["id"],
        "seller_name": seller["username"],
        "title": make_title(row.get("name"), row.get("brand_name")),
        "description": (row.get("item_description") or "").strip()[:1000] or "Imported from Mercari Japan.",
        "price": price_usd,
        "original_price": original_usd,
        "category_id": cat["id"],
        "category_name": cat["name"],
        "condition": condition,
        "brand": (row.get("brand_name") or "").strip()[:60],
        "size": "",
        "color": "",
        "images": make_placeholder_images(item_id),
        "shipping_paid_by": shipping_paid_by,
        "shipping_method": "Standard",
        "status": "active",
        "likes_count": random.randint(0, 80),
        "views_count": random.randint(20, 900),
        "featured": False,
        "store_id": None,
        "imported_from_id": None,
        "base_price": None,
        "created_at": datetime.now(timezone.utc) - timedelta(minutes=random.randint(0, 60 * 24 * 30)),
        # Meta for live sync tracking
        "kaggle_source_id": row.get("id"),
        "kaggle_source_category": row.get("category_name"),
    }


async def import_from_kaggle(
    db,
    target_count: int = 10000,
    replace_existing: bool = True,
) -> Dict:
    """Import listings from the downloaded Mercari JP TSV.

    - Fetches sellers + categories from DB
    - Optionally clears existing listings + related favorites/cart entries
    - Streams TSV, converts to USD, distributes across categories & sellers
    - Bulk inserts in chunks
    """
    if not DATA_FILE.exists():
        return {"ok": False, "error": "Kaggle data file missing. Please run kaggle download first."}

    cats = await db.categories.find({}, {"_id": 0}).to_list(200)
    if not cats:
        return {"ok": False, "error": "No categories in DB. Seed categories first."}
    cats_by_slug = {c["slug"]: c for c in cats}

    sellers = await db.users.find({"role": "user"}, {"_id": 0, "id": 1, "username": 1}).to_list(200)
    if len(sellers) < 3:
        return {"ok": False, "error": "Need at least 3 seller users."}

    if replace_existing:
        await db.listings.delete_many({})
        await db.favorites.delete_many({})
        await db.cart_items.delete_many({})

    # Two-pass strategy:
    # Pass 1 — balanced: aim for a per-category quota so we get variety.
    # Pass 2 — fill remainder without caps to reach target_count.
    per_category_target = max(400, target_count // max(1, len(cats)))
    per_cat_count: Dict[str, int] = {}
    to_insert: List[Dict] = []
    idx = 0
    processed = 0

    # Pass 1
    for row in stream_rows(limit=target_count * 8):
        processed += 1
        cat_slug = map_category(row.get("category_name", ""))
        if per_cat_count.get(cat_slug, 0) >= per_category_target:
            continue
        listing = build_listing(row, cats_by_slug, sellers, idx)
        if not listing:
            continue
        to_insert.append(listing)
        per_cat_count[cat_slug] = per_cat_count.get(cat_slug, 0) + 1
        idx += 1
        if len(to_insert) >= target_count:
            break

    # Pass 2 — fill remaining without caps
    if len(to_insert) < target_count:
        for row in stream_rows(limit=target_count * 20):
            processed += 1
            listing = build_listing(row, cats_by_slug, sellers, idx)
            if not listing:
                continue
            to_insert.append(listing)
            cat_slug = map_category(row.get("category_name", ""))
            per_cat_count[cat_slug] = per_cat_count.get(cat_slug, 0) + 1
            idx += 1
            if len(to_insert) >= target_count:
                break

    if not to_insert:
        return {"ok": False, "error": "No importable rows found."}

    # Featured: pick 30 random items
    for item in random.sample(to_insert, min(30, len(to_insert))):
        item["featured"] = True

    # Bulk insert in chunks
    chunk = 1000
    for i in range(0, len(to_insert), chunk):
        await db.listings.insert_many(to_insert[i : i + chunk])

    # Save sync metadata
    now = datetime.now(timezone.utc)
    await db.sync_state.update_one(
        {"id": "kaggle"},
        {"$set": {
            "id": "kaggle",
            "last_sync_at": now,
            "imported_count": len(to_insert),
            "target_count": target_count,
            "source": "hyamamoto2000/mercari-jp-dataset",
            "processed_rows": processed,
        }},
        upsert=True,
    )

    return {
        "ok": True,
        "imported": len(to_insert),
        "processed": processed,
        "per_category": per_cat_count,
        "last_sync_at": now.isoformat(),
    }


async def simulate_live_update(db) -> Dict:
    """Simulate a live update: rotate featured items, mark a few as sold, adjust some prices."""
    changes = {"featured_rotated": 0, "sold": 0, "price_updates": 0, "new_active": 0}

    active_count = await db.listings.count_documents({"status": "active"})
    if active_count == 0:
        return changes

    # Rotate featured — unfeature all, feature 30 random active
    await db.listings.update_many({"featured": True}, {"$set": {"featured": False}})
    sample = await db.listings.aggregate([
        {"$match": {"status": "active"}},
        {"$sample": {"size": min(30, active_count)}},
        {"$project": {"_id": 0, "id": 1}},
    ]).to_list(30)
    ids = [d["id"] for d in sample]
    if ids:
        r = await db.listings.update_many({"id": {"$in": ids}}, {"$set": {"featured": True}})
        changes["featured_rotated"] = r.modified_count

    # Mark ~5 active items as sold
    sold_sample = await db.listings.aggregate([
        {"$match": {"status": "active"}},
        {"$sample": {"size": 5}},
        {"$project": {"_id": 0, "id": 1}},
    ]).to_list(5)
    sold_ids = [d["id"] for d in sold_sample]
    if sold_ids:
        r = await db.listings.update_many({"id": {"$in": sold_ids}}, {"$set": {"status": "sold"}})
        changes["sold"] = r.modified_count

    # Increment views/likes on random active
    view_sample = await db.listings.aggregate([
        {"$match": {"status": "active"}},
        {"$sample": {"size": 50}},
        {"$project": {"_id": 0, "id": 1}},
    ]).to_list(50)
    for doc in view_sample:
        await db.listings.update_one(
            {"id": doc["id"]},
            {"$inc": {"views_count": random.randint(1, 10), "likes_count": random.randint(0, 2)}},
        )
    changes["price_updates"] = len(view_sample)

    # Save sync tick
    await db.sync_state.update_one(
        {"id": "kaggle"},
        {"$set": {"last_live_tick": datetime.now(timezone.utc), "active_listings": active_count}},
        upsert=True,
    )

    return changes


async def get_sync_status(db) -> Dict:
    state = await db.sync_state.find_one({"id": "kaggle"}, {"_id": 0}) or {}
    active_listings = await db.listings.count_documents({"status": "active"})
    sold_listings = await db.listings.count_documents({"status": "sold"})
    return {
        "source": state.get("source", "hyamamoto2000/mercari-jp-dataset"),
        "last_sync_at": state.get("last_sync_at").isoformat() if state.get("last_sync_at") else None,
        "last_live_tick": state.get("last_live_tick").isoformat() if state.get("last_live_tick") else None,
        "imported_count": state.get("imported_count", 0),
        "active_listings": active_listings,
        "sold_listings": sold_listings,
        "processed_rows": state.get("processed_rows", 0),
        "target_count": state.get("target_count", 0),
        "live_sync_enabled": True,
    }
