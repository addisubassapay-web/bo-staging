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
#
# STORAGE: every ingested product lives permanently in MongoDB Atlas (`products`
# collection). No TTL, no cleanup — see routers/products.py for the read APIs.
CATEGORY_URLS = [
    # ── Women ───────────────────────────────────────────────────
    ("women", "https://www.amazon.com/s?i=fashion-womens&s=exact-aware-popularity-rank"),
    ("women", "https://www.amazon.com/s?i=fashion-womens-shoes&s=exact-aware-popularity-rank"),
    ("women", "https://www.amazon.com/s?i=fashion-womens-handbags&s=exact-aware-popularity-rank"),
    ("women", "https://www.amazon.com/s?i=fashion-womens-intimate&s=exact-aware-popularity-rank"),
    ("women", "https://www.amazon.com/s?i=fashion-womens-jewelry&s=exact-aware-popularity-rank"),
    ("women", "https://www.amazon.com/s?i=fashion-womens-watches&s=exact-aware-popularity-rank"),
    # ── Men ─────────────────────────────────────────────────────
    ("men", "https://www.amazon.com/s?i=fashion-mens&s=exact-aware-popularity-rank"),
    ("men", "https://www.amazon.com/s?i=fashion-mens-shoes&s=exact-aware-popularity-rank"),
    ("men", "https://www.amazon.com/s?i=fashion-mens-watches&s=exact-aware-popularity-rank"),
    ("men", "https://www.amazon.com/s?i=fashion-mens-big-and-tall&s=exact-aware-popularity-rank"),
    ("men", "https://www.amazon.com/s?i=luggage&s=exact-aware-popularity-rank"),
    # ── Kids / Baby ─────────────────────────────────────────────
    ("kids", "https://www.amazon.com/s?i=fashion-baby&s=exact-aware-popularity-rank"),
    ("kids", "https://www.amazon.com/s?i=fashion-boys&s=exact-aware-popularity-rank"),
    ("kids", "https://www.amazon.com/s?i=fashion-girls&s=exact-aware-popularity-rank"),
    ("kids", "https://www.amazon.com/s?i=baby-products&s=exact-aware-popularity-rank"),
    ("kids", "https://www.amazon.com/s?i=fashion-baby-boys&s=exact-aware-popularity-rank"),
    ("kids", "https://www.amazon.com/s?i=fashion-baby-girls&s=exact-aware-popularity-rank"),
    # ── Electronics ─────────────────────────────────────────────
    ("electronics", "https://www.amazon.com/s?i=electronics&s=exact-aware-popularity-rank"),
    ("electronics", "https://www.amazon.com/s?i=computers&s=exact-aware-popularity-rank"),
    ("electronics", "https://www.amazon.com/s?i=mobile&s=exact-aware-popularity-rank"),
    ("electronics", "https://www.amazon.com/s?i=videogames&s=exact-aware-popularity-rank"),
    ("electronics", "https://www.amazon.com/s?i=musical-instruments&s=exact-aware-popularity-rank"),
    ("electronics", "https://www.amazon.com/s?i=photo&s=exact-aware-popularity-rank"),
    ("electronics", "https://www.amazon.com/s?i=wireless&s=exact-aware-popularity-rank"),
    # ── Home ────────────────────────────────────────────────────
    ("home", "https://www.amazon.com/s?i=garden&s=exact-aware-popularity-rank"),
    ("home", "https://www.amazon.com/s?i=kitchen&s=exact-aware-popularity-rank"),
    ("home", "https://www.amazon.com/s?i=furniture&s=exact-aware-popularity-rank"),
    ("home", "https://www.amazon.com/s?i=hi&s=exact-aware-popularity-rank"),  # tools & home improvement
    ("home", "https://www.amazon.com/s?i=appliances&s=exact-aware-popularity-rank"),
    ("home", "https://www.amazon.com/s?i=lawngarden&s=exact-aware-popularity-rank"),
    ("home", "https://www.amazon.com/s?i=pets&s=exact-aware-popularity-rank"),
    # ── Beauty ──────────────────────────────────────────────────
    ("beauty", "https://www.amazon.com/s?i=beauty&s=exact-aware-popularity-rank"),
    ("beauty", "https://www.amazon.com/s?i=luxury-beauty&s=exact-aware-popularity-rank"),
    ("beauty", "https://www.amazon.com/s?i=hpc&s=exact-aware-popularity-rank"),
    ("beauty", "https://www.amazon.com/s?i=premium-beauty&s=exact-aware-popularity-rank"),
    ("beauty", "https://www.amazon.com/s?i=grocery&s=exact-aware-popularity-rank"),
    # ── Sports ──────────────────────────────────────────────────
    ("sports", "https://www.amazon.com/s?i=sporting&s=exact-aware-popularity-rank"),
    ("sports", "https://www.amazon.com/s?i=outdoor&s=exact-aware-popularity-rank"),
    ("sports", "https://www.amazon.com/s?i=fitness&s=exact-aware-popularity-rank"),
    ("sports", "https://www.amazon.com/s?i=automotive&s=exact-aware-popularity-rank"),
    # ── Toys ────────────────────────────────────────────────────
    ("toys", "https://www.amazon.com/s?i=toys-and-games&s=exact-aware-popularity-rank"),
    ("toys", "https://www.amazon.com/s?i=arts-crafts&s=exact-aware-popularity-rank"),
    ("toys", "https://www.amazon.com/s?i=collectibles&s=exact-aware-popularity-rank"),
    # ── Books ───────────────────────────────────────────────────
    ("books", "https://www.amazon.com/s?i=stripbooks&s=exact-aware-popularity-rank"),
    ("books", "https://www.amazon.com/s?i=audible&s=exact-aware-popularity-rank"),
    ("books", "https://www.amazon.com/s?i=digital-text&s=exact-aware-popularity-rank"),
    ("books", "https://www.amazon.com/s?i=magazines&s=exact-aware-popularity-rank"),
    # ── Handmade ────────────────────────────────────────────────
    ("handmade", "https://www.amazon.com/s?i=handmade&s=exact-aware-popularity-rank"),
    ("handmade", "https://www.amazon.com/s?i=arts-crafts&s=exact-aware-popularity-rank"),
    ("handmade", "https://www.amazon.com/s?i=industrial&s=exact-aware-popularity-rank"),
]



def _get_tokens() -> List[str]:
    tokens: List[str] = []
    primary = os.environ.get("APIFY_TOKEN")
    fallback = os.environ.get("APIFY_TOKEN_FALLBACK")
    if primary:
        tokens.append(primary)
    if fallback and fallback != primary:
        tokens.append(fallback)
    if not tokens:
        raise RuntimeError("APIFY_TOKEN missing from environment")
    return tokens


def _get_client(token: Optional[str] = None) -> ApifyClient:
    if token is None:
        token = _get_tokens()[0]
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
    secondary_slugs: Optional[List[str]] = None,
    cats_by_slug: Optional[Dict[str, Dict]] = None,
) -> Optional[Dict]:
    price = _first_price(item)
    if price is None or price < 0.99:
        return None
    title = (item.get("title") or "").strip()
    if not title:
        return None
    item_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    # Resolve secondary category IDs (dedup, exclude primary)
    secondary_ids: List[str] = []
    if secondary_slugs and cats_by_slug:
        for s in secondary_slugs:
            c = cats_by_slug.get(s)
            if c and c["id"] != cat["id"] and c["id"] not in secondary_ids:
                secondary_ids.append(c["id"])
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
        "secondary_categories": secondary_ids,
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


DEMO_SELLER_USERNAMES = [
    "sophia_style", "urban_finds", "vintage_maven", "tech_haven", "cozy_home",
]


async def _get_sellers(db) -> List[Dict]:
    """Only distribute Apify imports across the curated demo sellers.
    This prevents test users (from e2e runs) from accumulating product listings.
    """
    return await db.users.find(
        {"username": {"$in": DEMO_SELLER_USERNAMES}, "role": "user"},
        {"_id": 0, "id": 1, "username": 1},
    ).to_list(50)


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
    target_count: int = 30000,
    replace_existing: bool = False,
) -> Dict:
    """Scrape Amazon via Apify and import as listings.

    Defaults to APPEND mode: new products join the catalog without wiping the
    existing content. Dedup is performed via `apify_asin` — items whose ASIN
    already lives in the DB are skipped (or updated if `refresh_existing`).
    Pass `replace_existing=True` to nuke the entire listings collection first
    (rare — usually only for a clean initial seed).
    """
    cats = await _get_categories_by_slug(db)
    sellers = await _get_sellers(db)
    if not cats or len(sellers) < 3:
        return {"ok": False, "error": "Need categories + at least 3 seller users seeded"}

    per_url = max(500, target_count // len(CATEGORY_URLS))
    urls = [{"url": url} for (_slug, url) in CATEGORY_URLS if _slug in cats]
    slugs = [slug for (slug, url) in CATEGORY_URLS if slug in cats]

    client = _get_client()
    tokens = _get_tokens()

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
    dataset_id = None
    last_error: Optional[str] = None
    for idx, token in enumerate(tokens):
        attempt_client = _get_client(token)
        try:
            dataset_id = await loop.run_in_executor(
                None, _run_actor_sync, attempt_client, urls, per_url
            )
            if dataset_id:
                client = attempt_client  # use the working client for dataset fetch
                if idx > 0:
                    logger.info(f"Apify primary token failed; used fallback token #{idx}")
                break
        except Exception as e:
            last_error = str(e)
            logger.warning(f"Apify token #{idx} failed: {e}")
            continue

    if not dataset_id:
        err_msg = last_error or "No dataset returned"
        logger.exception(f"Apify actor failed on all tokens: {err_msg}")
        await db.sync_state.update_one(
            {"id": "apify"},
            {"$set": {"sync_running": False, "message": f"Actor error: {err_msg}"}},
        )
        return {"ok": False, "error": err_msg}

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
        existing_asins: set = set()
    else:
        # Append mode — dedup by apify_asin so re-runs never duplicate a product.
        existing_asins = {
            d.get("apify_asin")
            for d in await db.listings.find(
                {"apify_asin": {"$ne": None, "$exists": True}},
                {"_id": 0, "apify_asin": 1},
            ).to_list(50000)
            if d.get("apify_asin")
        }

    # Distribute items across categories using the keyword classifier + a fair
    # round-robin over UNIQUE catalog slugs when the classifier finds nothing.
    from services.category_classifier import classify as _classify
    to_insert: List[Dict] = []
    per_cat: Dict[str, int] = {}
    idx = 0
    skipped_dupes = 0
    total_raw = len(items)
    unique_slugs = list(dict.fromkeys(slugs))  # preserve order, drop dups
    # Never fallback to "other" alone — spread fallbacks across every real category
    fallback_pool = [s for s in unique_slugs if s != "other"] or unique_slugs
    for it in items:
        asin = it.get("asin")
        if asin and asin in existing_asins:
            skipped_dupes += 1
            continue
        matched = _classify(it, unique_slugs)  # ordered list of slug tags
        if matched:
            primary_slug = matched[0]
            secondary_slugs = matched[1:]
        else:
            primary_slug = fallback_pool[idx % len(fallback_pool)]
            secondary_slugs = []
        cat = cats.get(primary_slug) or cats.get("other")
        if not cat:
            continue
        seller = sellers[idx % len(sellers)]
        listing = _build_listing(it, cat, seller, secondary_slugs=secondary_slugs, cats_by_slug=cats)
        if listing:
            to_insert.append(listing)
            if asin:
                existing_asins.add(asin)
            per_cat[primary_slug] = per_cat.get(primary_slug, 0) + 1
            idx += 1
            # Persist per-category counts every 200 imports so mid-run status is live
            if idx % 200 == 0:
                await db.sync_state.update_one(
                    {"id": "apify"},
                    {"$set": {
                        "per_category": dict(per_cat),
                        "message": f"Classifying — {idx} of {total_raw} raw items imported",
                    }},
                )

    if to_insert:
        # feature ~40 items
        for f in random.sample(to_insert, min(40, len(to_insert))):
            f["featured"] = True
        for i in range(0, len(to_insert), 1000):
            await db.listings.insert_many(to_insert[i : i + 1000])

        # Mirror to the permanent `products` catalog (MongoDB Atlas) via upsert
        # on sku (=apify_asin). This guarantees every Apify-scraped row shows
        # on `/api/products` immediately — no separate bridge step needed.
        product_ops = []
        from pymongo import UpdateOne  # local import — avoids adding to top-level deps
        mirror_ts = datetime.now(timezone.utc)
        for l in to_insert:
            asin = l.get("apify_asin")
            if not asin:
                continue
            product_ops.append(UpdateOne(
                {"sku": asin},
                {
                    "$setOnInsert": {
                        "id": str(uuid.uuid4()),
                        "created_at": mirror_ts,
                        "sku": asin,
                    },
                    "$set": {
                        "title": l.get("title") or "",
                        "description": l.get("description") or "",
                        "price": float(l.get("price") or 0.0),
                        "currency": "USD",
                        "images": list(l.get("images") or []),
                        "category": l.get("category_name") or None,
                        "source_url": l.get("apify_url") or None,
                        "is_active": True,
                        "updated_at": mirror_ts,
                    },
                },
                upsert=True,
            ))
        if product_ops:
            for i in range(0, len(product_ops), 500):
                await db.products.bulk_write(product_ops[i : i + 500], ordered=False)

    completed_at = datetime.now(timezone.utc)
    await db.sync_state.update_one(
        {"id": "apify"},
        {"$set": {
            "sync_running": False,
            "last_sync_at": completed_at,
            "imported_count": len(to_insert),
            "raw_items": len(items),
            "skipped_dupes": skipped_dupes,
            "per_category": per_cat,
            "dataset_id": dataset_id,
            "message": f"Imported {len(to_insert)} new · skipped {skipped_dupes} duplicates · of {len(items)} raw items",
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
    """Rotate featured, tick views/likes, mark a few active items sold, and revive some sold items.

    Guardrails:
      * Never mark any item sold when active count is at or below ACTIVE_FLOOR (keeps the marketplace populated).
      * Resurrect a handful of sold listings back to active on every tick so the demo stays lively.
    """
    ACTIVE_FLOOR = 60      # never dip below this many active listings
    REVIVE_PER_TICK = 5    # bring this many sold items back to active each minute
    SELL_PER_TICK = 3      # mark this many active items as sold (only if above floor)

    changes = {"featured_rotated": 0, "sold": 0, "revived": 0, "views_bumped": 0}

    total_count = await db.listings.count_documents({})
    if total_count == 0:
        return changes

    # Revive some sold items back to active first
    sold_sample = await db.listings.aggregate([
        {"$match": {"status": "sold"}},
        {"$sample": {"size": REVIVE_PER_TICK}},
        {"$project": {"_id": 0, "id": 1}},
    ]).to_list(REVIVE_PER_TICK)
    if sold_sample:
        r = await db.listings.update_many(
            {"id": {"$in": [d["id"] for d in sold_sample]}},
            {"$set": {"status": "active"}},
        )
        changes["revived"] = r.modified_count

    active_count = await db.listings.count_documents({"status": "active"})
    if active_count == 0:
        return changes

    await db.listings.update_many({"featured": True}, {"$set": {"featured": False}})
    feat_sample = await db.listings.aggregate([
        {"$match": {"status": "active"}},
        {"$sample": {"size": min(40, active_count)}},
        {"$project": {"_id": 0, "id": 1}},
    ]).to_list(40)
    ids = [d["id"] for d in feat_sample]
    if ids:
        r = await db.listings.update_many({"id": {"$in": ids}}, {"$set": {"featured": True}})
        changes["featured_rotated"] = r.modified_count

    # Only mark items sold when active count is safely above the floor.
    if active_count - SELL_PER_TICK >= ACTIVE_FLOOR:
        sell_sample = await db.listings.aggregate([
            {"$match": {"status": "active"}},
            {"$sample": {"size": SELL_PER_TICK}},
            {"$project": {"_id": 0, "id": 1}},
        ]).to_list(SELL_PER_TICK)
        if sell_sample:
            r = await db.listings.update_many(
                {"id": {"$in": [d["id"] for d in sell_sample]}},
                {"$set": {"status": "sold"}},
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
        "next_scheduled_at": state.get("next_scheduled_at").isoformat() if state.get("next_scheduled_at") else None,
        "schedule_interval_days": state.get("schedule_interval_days", 30),
        "auto_schedule_enabled": bool(state.get("auto_schedule_enabled", True)),
    }
