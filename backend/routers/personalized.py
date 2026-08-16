"""
Personalized deals feed — region-tuned "For You" grid.

Blends the buyer's recent browse history (view events + favorites) with a
region-aware price filter so shoppers in different markets get a grid that
feels native. Currently region tuning targets Gulf/AED shoppers (task ask)
but the same shape works for any region — just add an entry to REGION_TUNING.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, Depends

from .deps import get_db, get_current_user

router = APIRouter()

# Region tuning — approx local-currency sweet spots converted to USD baseline
# so we can filter listings.price directly (USD is the storage unit).
REGION_TUNING = {
    # Gulf shoppers — AED-friendly range roughly ~40 to ~1000 AED
    "GULF": {"currencies": {"AED"}, "usd_min": 10.0, "usd_max": 300.0, "boost_categories": ["home", "beauty", "electronics", "kids"]},
    # LatAm shoppers — MXN/BRL common buys ~50-500 MXN / 30-300 BRL
    "LATAM": {"currencies": {"MXN", "BRL"}, "usd_min": 5.0, "usd_max": 150.0, "boost_categories": ["beauty", "kids", "sports"]},
    # EU shoppers — EUR/GBP common buys ~10-200
    "EU": {"currencies": {"EUR", "GBP"}, "usd_min": 10.0, "usd_max": 250.0, "boost_categories": ["home", "beauty", "handmade"]},
    # India shoppers — INR common buys ~100-5000
    "IN": {"currencies": {"INR"}, "usd_min": 3.0, "usd_max": 120.0, "boost_categories": ["beauty", "home", "kids"]},
}


def _detect_region(currency: Optional[str]) -> Optional[dict]:
    if not currency:
        return None
    for region_meta in REGION_TUNING.values():
        if currency in region_meta["currencies"]:
            return region_meta
    return None


@router.get("/deals/personalized")
async def personalized_deals(
    currency: Optional[str] = None,
    limit: int = 24,
    user: dict = Depends(get_current_user),
):
    """Blend recent browse history + region-tuned price filter into a
    ranked list of active listings. Falls back gracefully to trending
    picks when the user has no history yet."""
    db = get_db()
    limit = max(4, min(int(limit or 24), 60))

    region = _detect_region((currency or "").upper())

    # 1) Browse-history signal — last 30 days of favorites + recently viewed
    since = datetime.now(timezone.utc) - timedelta(days=30)
    fav_ids = [
        f["listing_id"] async for f in db.favorites.find(
            {"user_id": user["id"]}, {"_id": 0, "listing_id": 1},
        )
    ]
    view_ids = [
        v["listing_id"] async for v in db.view_events.find(
            {"user_id": user["id"], "at": {"$gte": since}},
            {"_id": 0, "listing_id": 1},
        ).sort("at", -1).limit(50)
    ] if "view_events" in await db.list_collection_names() else []
    seed_ids = list({*fav_ids, *view_ids})

    # 2) Category affinity — most-common categories from seed listings
    aff_categories: list[str] = []
    if seed_ids:
        pipeline = [
            {"$match": {"id": {"$in": seed_ids}}},
            {"$group": {"_id": "$category_id", "n": {"$sum": 1}}},
            {"$sort": {"n": -1}},
            {"$limit": 5},
        ]
        aff_categories = [d["_id"] async for d in db.listings.aggregate(pipeline) if d.get("_id")]

    # 3) Build the query — active listings, exclude already-seen seeds
    query: dict = {"status": "active"}
    if seed_ids:
        query["id"] = {"$nin": seed_ids}
    if region:
        query["price"] = {"$gte": region["usd_min"], "$lte": region["usd_max"]}
    boost_cats = list({*(aff_categories or []), *(region["boost_categories"] if region else [])})
    if boost_cats:
        query["category_id"] = {"$in": boost_cats}

    projection = {"_id": 0}
    items = await db.listings.find(query, projection).sort(
        [("likes_count", -1), ("views_count", -1), ("created_at", -1)]
    ).limit(limit).to_list(limit)

    # 4) Backfill with trending picks if the region+affinity query is thin
    if len(items) < limit:
        seen = {i["id"] for i in items} | set(seed_ids)
        backfill_query = {"status": "active", "id": {"$nin": list(seen)}}
        if region:
            backfill_query["price"] = {"$gte": region["usd_min"], "$lte": region["usd_max"]}
        more = await db.listings.find(backfill_query, projection).sort(
            [("likes_count", -1), ("views_count", -1)]
        ).limit(limit - len(items)).to_list(limit - len(items))
        items.extend(more)

    return {
        "items": items,
        "count": len(items),
        "personalized": bool(seed_ids),
        "region_tuned": bool(region),
        "signals": {
            "seed_ids": len(seed_ids),
            "affinity_categories": aff_categories,
            "region_currency": currency,
            "usd_price_range": [region["usd_min"], region["usd_max"]] if region else None,
        },
    }
