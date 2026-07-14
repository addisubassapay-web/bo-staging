"""Apify Amazon Crawler integration.
Uses junglee/amazon-crawler to scrape live Amazon.com products across
bestseller categories and imports them as marketplace listings.
"""
import os
import random
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional
import uuid

from apify_client import ApifyClient

logger = logging.getLogger(__name__)

ACTOR_ID = "junglee/amazon-crawler"

# Amazon department search URLs → our category slug
# Multiple `/s?i=<dept>` URLs per category (this format works reliably with the actor).
# NOTE: `/s?k=<keyword>` (keyword search) also works but consumes MORE credits per item
# because the actor visits more pages. Keep this list to department URLs.
CATEGORY_URLS = [
    # Women
    ("women", "https://www.amazon.com/s?i=fashion-womens&s=exact-aware-popularity-rank"),
    ("women", "https://www.amazon.com/s?i=fashion-womens-shoes&s=exact-aware-popularity-rank"),
    ("women", "https://www.amazon.com/s?i=fashion-womens-handbags&s=exact-aware-popularity-rank"),
    # Men
    ("men", "https://www.amazon.com/s?i=fashion-mens&s=exact-aware-popularity-rank"),
    ("men", "https://www.amazon.com/s?i=fashion-mens-shoes&s=exact-aware-popularity-rank"),
    ("men", "https://www.amazon.com/s?i=fashion-mens-watches&s=exact-aware-popularity-rank"),
    # Kids
    ("kids", "https://www.amazon.com/s?i=fashion-baby&s=exact-aware-popularity-rank"),
    ("kids", "https://www.amazon.com/s?i=fashion-boys&s=exact-aware-popularity-rank"),
    ("kids", "https://www.amazon.com/s?i=fashion-girls&s=exact-aware-popularity-rank"),
    # Electronics
    ("electronics", "https://www.amazon.com/s?i=electronics&s=exact-aware-popularity-rank"),
    ("electronics", "https://www.amazon.com/s?i=computers&s=exact-aware-popularity-rank"),
    ("electronics", "https://www.amazon.com/s?i=mobile&s=exact-aware-popularity-rank"),
    # Home
    ("home", "https://www.amazon.com/s?i=garden&s=exact-aware-popularity-rank"),
    ("home", "https://www.amazon.com/s?i=kitchen&s=exact-aware-popularity-rank"),
    ("home", "https://www.amazon.com/s?i=furniture&s=exact-aware-popularity-rank"),
    # Beauty
    ("beauty", "https://www.amazon.com/s?i=beauty&s=exact-aware-popularity-rank"),
    ("beauty", "https://www.amazon.com/s?i=luxury-beauty&s=exact-aware-popularity-rank"),
    ("beauty", "https://www.amazon.com/s?i=hpc&s=exact-aware-popularity-rank"),
    # Sports
    ("sports", "https://www.amazon.com/s?i=sporting&s=exact-aware-popularity-rank"),
    ("sports", "https://www.amazon.com/s?i=outdoor&s=exact-aware-popularity-rank"),
    # Toys
    ("toys", "https://www.amazon.com/s?i=toys-and-games&s=exact-aware-popularity-rank"),
    ("toys", "https://www.amazon.com/s?i=videogames&s=exact-aware-popularity-rank"),
    # Books
    ("books", "https://www.amazon.com/s?i=stripbooks&s=exact-aware-popularity-rank"),
    ("books", "https://www.amazon.com/s?i=audible&s=exact-aware-popularity-rank"),
    # Handmade
    ("handmade", "https://www.amazon.com/s?i=handmade&s=exact-aware-popularity-rank"),
    # Other
    ("other", "https://www.amazon.com/s?i=office-products&s=exact-aware-popularity-rank"),
    ("other", "https://www.amazon.com/s?i=pet-supplies&s=exact-aware-popularity-rank"),
    ("other", "https://www.amazon.com/s?i=automotive&s=exact-aware-popularity-rank"),
]


def _get_client() -> ApifyClient:
    token = os.environ.get("APIFY_TOKEN")
    if not token:
        raise RuntimeError("APIFY_TOKEN missing from environment")
    return ApifyClient(token)


def _first_price(item: Dict) -> Optional[float]:
    p = item.get("price")
    if isinstance(p, dict) and p.get("value") is not None:
        try:
            return round(float(p["value"]), 2)
        except (ValueError, TypeError):
            return None
    if isinstance(p, (int, float)):
        return round(float(p), 2)
    return None


def _list_price(item: Dict) -> Optional[float]:
    lp = item.get("listPrice")
    if isinstance(lp, dict) and lp.get("value") is not None:
        try:
            return round(float(lp["value"]), 2)
        except (ValueError, TypeError):
            return None
    return None


def _images(item: Dict, limit: int = 3) -> List[str]:
    imgs: List[str] = []
    for k in ("highResolutionImages", "galleryThumbnails"):
        v = item.get(k)
        if isinstance(v, list):
            imgs.extend([u for u in v if isinstance(u, str) and u.startswith("http")])
    thumb = item.get("thumbnailImage")
    if isinstance(thumb, str) and thumb.startswith("http"):
        imgs.append(thumb)
    # de-dup preserving order
    seen = set()
    unique = []
    for u in imgs:
        if u not in seen:
            seen.add(u)
            unique.append(u)
    return unique[:limit] or (["https://m.media-amazon.com/images/G/01/gc/designs/livepreview/default_ph.png"] if not unique else unique)


def _condition_guess(item: Dict) -> str:
    """Amazon items are new by default."""
    return "new"


def _description(item: Dict) -> str:
    parts: List[str] = []
    if item.get("description"):
        parts.append(str(item["description"]))
    feats = item.get("features")
    if isinstance(feats, list) and feats:
        parts.append("\n\nKey features:")
        for f in feats[:6]:
            parts.append(f"• {f}")
    if item.get("brand"):
        parts.append(f"\nBrand: {item['brand']}")
    return ("\n".join(parts) or "Imported from Amazon US.").strip()[:1400]


def _build_listing(
    item: Dict,
    cat: Dict,
    seller: Dict,
) -> Optional[Dict]:
    price = _first_price(item)
    if price is None or price < 0.99:
        return None
    title = (item.get("title") or "").strip()
    if not title:
        return None
    item_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    return {
        "id": item_id,
        "seller_id": seller["id"],
        "seller_name": seller["username"],
        "title": title[:180],
        "description": _description(item),
        "price": price,
        "original_price": _list_price(item),
        "category_id": cat["id"],
        "category_name": cat["name"],
        "condition": _condition_guess(item),
        "brand": (item.get("brand") or "")[:80],
        "size": "",
        "color": "",
        "images": _images(item),
        "shipping_paid_by": "seller",
        "shipping_method": "Standard",
        "status": "active",
        "likes_count": random.randint(0, 60),
        "views_count": random.randint(20, 1200),
        "featured": False,
        "store_id": None,
        "imported_from_id": None,
        "base_price": None,
        "translated": True,  # already English
        "created_at": now - timedelta(minutes=random.randint(0, 60 * 24 * 30)),
        "apify_asin": item.get("asin"),
        "apify_url": item.get("url"),
        "rating": item.get("stars"),
        "reviews_count": item.get("reviewsCount"),
    }


async def _get_categories_by_slug(db) -> Dict[str, Dict]:
    cats = await db.categories.find({}, {"_id": 0}).to_list(200)
    return {c["slug"]: c for c in cats}


async def _get_sellers(db) -> List[Dict]:
    return await db.users.find({"role": "user"}, {"_id": 0, "id": 1, "username": 1}).to_list(200)


def _run_actor_sync(client: ApifyClient, urls: List[Dict], max_per_url: int) -> Optional[str]:
    """Run the actor (blocking, called from thread executor)."""
    run_input = {
        "categoryOrProductUrls": urls,
        "maxItemsPerStartUrl": max_per_url,
        "proxyConfiguration": {"useApifyProxy": True},
    }
    run = client.actor(ACTOR_ID).call(run_input=run_input)
    if getattr(run, "status", None) != "SUCCEEDED":
        logger.warning(f"Actor status: {getattr(run, 'status', None)}")
    return getattr(run, "default_dataset_id", None)


async def import_from_apify(
    db,
    target_count: int = 5000,
    replace_existing: bool = True,
) -> Dict:
    """Scrape Amazon via Apify and import as listings."""
    cats = await _get_categories_by_slug(db)
    sellers = await _get_sellers(db)
    if not cats or len(sellers) < 3:
        return {"ok": False, "error": "Need categories + at least 3 seller users seeded"}

    per_url = max(50, target_count // len(CATEGORY_URLS))
    urls = [{"url": url} for (_slug, url) in CATEGORY_URLS if _slug in cats]
    slugs = [slug for (slug, url) in CATEGORY_URLS if slug in cats]

    client = _get_client()

    # Record start state
    now = datetime.now(timezone.utc)
    await db.sync_state.update_one(
        {"id": "apify"},
        {"$set": {
            "id": "apify",
            "source": ACTOR_ID,
            "sync_running": True,
            "target_count": target_count,
            "started_at": now,
            "message": f"Running actor for {len(urls)} categories, up to {per_url} each",
        }},
        upsert=True,
    )

    # The actor call blocks — run in a thread so we don't block the event loop
    loop = asyncio.get_event_loop()
    try:
        dataset_id = await loop.run_in_executor(None, _run_actor_sync, client, urls, per_url)
    except Exception as e:
        logger.exception("Apify actor failed")
        await db.sync_state.update_one(
            {"id": "apify"},
            {"$set": {"sync_running": False, "message": f"Actor error: {e}"}},
        )
        return {"ok": False, "error": str(e)}

    if not dataset_id:
        await db.sync_state.update_one(
            {"id": "apify"}, {"$set": {"sync_running": False, "message": "No dataset returned"}}
        )
        return {"ok": False, "error": "No dataset returned"}

    # Fetch items from Apify dataset (also blocking → thread)
    def _fetch_items():
        return list(client.dataset(dataset_id).iterate_items())
    items = await loop.run_in_executor(None, _fetch_items)

    if not items:
        await db.sync_state.update_one(
            {"id": "apify"},
            {"$set": {"sync_running": False, "message": "Actor returned 0 items — likely out of Apify credits. Existing listings kept."}},
        )
        return {"ok": False, "error": "Actor returned 0 items — check your Apify credit balance."}

    if replace_existing:
        await db.listings.delete_many({})
        await db.favorites.delete_many({})
        await db.cart_items.delete_many({})

    # Distribute items across categories — the actor may return them in category order,
    # but we don't have guaranteed per-item category, so we round-robin over slugs
    to_insert: List[Dict] = []
    per_cat: Dict[str, int] = {}
    idx = 0
    for it in items:
        # try to detect category from the actor's breadCrumbs, else round-robin
        slug_hit = None
        crumbs = it.get("breadCrumbs")
        if isinstance(crumbs, str):
            low = crumbs.lower()
            for slug in slugs:
                if slug in low:
                    slug_hit = slug
                    break
        if not slug_hit:
            slug_hit = slugs[idx % len(slugs)]
        cat = cats.get(slug_hit) or cats.get("other")
        if not cat:
            continue
        seller = sellers[idx % len(sellers)]
        listing = _build_listing(it, cat, seller)
        if listing:
            to_insert.append(listing)
            per_cat[slug_hit] = per_cat.get(slug_hit, 0) + 1
            idx += 1

    if to_insert:
        # feature ~40 items
        for f in random.sample(to_insert, min(40, len(to_insert))):
            f["featured"] = True
        for i in range(0, len(to_insert), 1000):
            await db.listings.insert_many(to_insert[i : i + 1000])

    completed_at = datetime.now(timezone.utc)
    await db.sync_state.update_one(
        {"id": "apify"},
        {"$set": {
            "sync_running": False,
            "last_sync_at": completed_at,
            "imported_count": len(to_insert),
            "raw_items": len(items),
            "per_category": per_cat,
            "dataset_id": dataset_id,
            "message": f"Imported {len(to_insert)} of {len(items)} raw items",
        }},
    )

    return {
        "ok": True,
        "imported": len(to_insert),
        "raw": len(items),
        "per_category": per_cat,
        "dataset_id": dataset_id,
    }


async def simulate_live_update(db) -> Dict:
    """Rotate featured, tick views/likes, mark random items sold."""
    changes = {"featured_rotated": 0, "sold": 0, "views_bumped": 0}
    active_count = await db.listings.count_documents({"status": "active"})
    if active_count == 0:
        return changes

    await db.listings.update_many({"featured": True}, {"$set": {"featured": False}})
    sample = await db.listings.aggregate([
        {"$match": {"status": "active"}},
        {"$sample": {"size": min(40, active_count)}},
        {"$project": {"_id": 0, "id": 1}},
    ]).to_list(40)
    ids = [d["id"] for d in sample]
    if ids:
        r = await db.listings.update_many({"id": {"$in": ids}}, {"$set": {"featured": True}})
        changes["featured_rotated"] = r.modified_count

    sold_sample = await db.listings.aggregate([
        {"$match": {"status": "active"}},
        {"$sample": {"size": 3}},
        {"$project": {"_id": 0, "id": 1}},
    ]).to_list(3)
    if sold_sample:
        r = await db.listings.update_many(
            {"id": {"$in": [d["id"] for d in sold_sample]}}, {"$set": {"status": "sold"}}
        )
        changes["sold"] = r.modified_count

    view_sample = await db.listings.aggregate([
        {"$match": {"status": "active"}},
        {"$sample": {"size": 40}},
        {"$project": {"_id": 0, "id": 1}},
    ]).to_list(40)
    for doc in view_sample:
        await db.listings.update_one(
            {"id": doc["id"]},
            {"$inc": {"views_count": random.randint(1, 8), "likes_count": random.randint(0, 2)}},
        )
    changes["views_bumped"] = len(view_sample)

    await db.sync_state.update_one(
        {"id": "apify"},
        {"$set": {"last_live_tick": datetime.now(timezone.utc), "active_listings": active_count}},
        upsert=True,
    )
    return changes


async def get_sync_status(db) -> Dict:
    state = await db.sync_state.find_one({"id": "apify"}, {"_id": 0}) or {}
    active = await db.listings.count_documents({"status": "active"})
    sold = await db.listings.count_documents({"status": "sold"})
    total = await db.listings.count_documents({})
    return {
        "source": state.get("source", ACTOR_ID),
        "last_sync_at": state.get("last_sync_at").isoformat() if state.get("last_sync_at") else None,
        "started_at": state.get("started_at").isoformat() if state.get("started_at") else None,
        "last_live_tick": state.get("last_live_tick").isoformat() if state.get("last_live_tick") else None,
        "imported_count": state.get("imported_count", 0),
        "raw_items": state.get("raw_items", 0),
        "active_listings": active,
        "sold_listings": sold,
        "total_listings": total,
        "target_count": state.get("target_count", 0),
        "live_sync_enabled": True,
        "sync_running": bool(state.get("sync_running")),
        "message": state.get("message", ""),
        "per_category": state.get("per_category", {}),
    }
