"""
Search + Recommendations router.

Endpoints extracted from server.py in Phase 6 refactor step 1:
- GET  /api/search/suggest
- GET  /api/for-you
- POST /api/recently-viewed/{listing_id}
- GET  /api/recently-viewed
- GET  /api/listings/{listing_id}/bundle

These endpoints depend only on the DB + current-user helpers — no cross-module
imports needed. Kept behaviour-identical to the original inline versions.
"""
from __future__ import annotations
import re
from typing import List
from fastapi import APIRouter, Depends, HTTPException

from .deps import get_db, get_current_user, now_utc

router = APIRouter()


@router.get("/search/suggest")
async def search_suggest(q: str = "", limit: int = 8):
    q = (q or "").strip()
    if len(q) < 2:
        return {"items": [], "queries": [], "brands": [], "categories": []}
    db = get_db()
    rx = {"$regex": re.escape(q), "$options": "i"}
    # Product matches
    docs = await db.listings.find(
        {"status": "active", "$or": [{"title": rx}, {"brand": rx}]},
        {"_id": 0, "id": 1, "title": 1, "images": 1, "price": 1, "brand": 1, "category_name": 1, "category_id": 1},
    ).limit(limit).to_list(limit)
    items = [{
        "id": d["id"],
        "title": d["title"],
        "image": (d.get("images") or [None])[0],
        "price": d["price"],
        "brand": d.get("brand") or "",
        "category_name": d.get("category_name") or "",
    } for d in docs]
    # Brand suggestions (with counts)
    brand_pipe = [
        {"$match": {"status": "active", "brand": rx}},
        {"$group": {"_id": "$brand", "n": {"$sum": 1}}},
        {"$sort": {"n": -1}},
        {"$limit": 5},
    ]
    brand_agg = [b async for b in db.listings.aggregate(brand_pipe)]
    brands = [{"name": b["_id"], "count": b["n"]} for b in brand_agg if b.get("_id")]
    # Category suggestions (from taxonomy — safer than listing category_name text)
    cat_docs = await db.categories.find(
        {"$or": [{"name": rx}, {"slug": rx}]},
        {"_id": 0, "id": 1, "name": 1, "slug": 1, "icon": 1},
    ).limit(5).to_list(5)
    categories = cat_docs
    # Query token suggestions (unique titles containing q, first token span)
    title_docs = await db.listings.find(
        {"status": "active", "title": rx},
        {"_id": 0, "title": 1},
    ).limit(30).to_list(30)
    seen: set = set()
    query_tokens: list = []
    ql = q.lower()
    for d in title_docs:
        t = (d.get("title") or "").lower()
        # Take a phrase of 2-3 words centered on the query
        idx = t.find(ql)
        if idx == -1:
            continue
        # Expand to word boundaries and include a couple of following words
        start = t.rfind(" ", 0, idx) + 1
        end = idx + len(ql)
        for _ in range(2):
            ns = t.find(" ", end + 1)
            if ns == -1:
                break
            end = ns
        phrase = t[start:end].strip()
        if 3 <= len(phrase) <= 40 and phrase not in seen:
            seen.add(phrase)
            query_tokens.append(phrase)
        if len(query_tokens) >= 6:
            break
    return {
        "items": items,
        "queries": query_tokens,
        "brands": brands,
        "categories": categories,
    }


@router.get("/search/facets")
async def search_facets(
    q: str = "",
    category_id: str = "",
    condition: str = "",
    min_price: float | None = None,
    max_price: float | None = None,
):
    """Return aggregated brand counts + price range for the current search filters.
    Powers advanced filter panel in Search page."""
    db = get_db()
    query: dict = {"status": "active"}
    if q:
        rx = {"$regex": re.escape(q), "$options": "i"}
        query["$or"] = [{"title": rx}, {"description": rx}, {"brand": rx}]
    if category_id:
        query["category_id"] = category_id
    if condition:
        query["condition"] = condition
    if min_price is not None or max_price is not None:
        pr: dict = {}
        if min_price is not None:
            pr["$gte"] = min_price
        if max_price is not None:
            pr["$lte"] = max_price
        query["price"] = pr

    # Top brands
    brand_pipe = [
        {"$match": query},
        {"$group": {"_id": "$brand", "n": {"$sum": 1}}},
        {"$sort": {"n": -1}},
        {"$limit": 20},
    ]
    brands = [
        {"name": b["_id"], "count": b["n"]}
        async for b in db.listings.aggregate(brand_pipe)
        if b.get("_id")
    ]
    # Condition counts
    cond_pipe = [
        {"$match": query},
        {"$group": {"_id": "$condition", "n": {"$sum": 1}}},
        {"$sort": {"n": -1}},
    ]
    conditions = [
        {"value": c["_id"], "count": c["n"]}
        async for c in db.listings.aggregate(cond_pipe)
        if c.get("_id")
    ]
    # Price bounds
    price_pipe = [
        {"$match": query},
        {"$group": {"_id": None, "min": {"$min": "$price"}, "max": {"$max": "$price"}}},
    ]
    price_agg = [p async for p in db.listings.aggregate(price_pipe)]
    price = {"min": 0, "max": 0}
    if price_agg:
        price = {"min": float(price_agg[0].get("min") or 0), "max": float(price_agg[0].get("max") or 0)}
    total = await db.listings.count_documents(query)
    return {"brands": brands, "conditions": conditions, "price": price, "total": total}


@router.get("/search/trending")
async def search_trending(limit: int = 8):
    """Trending queries derived from the most popular active listings' brands + categories."""
    db = get_db()
    pipe = [
        {"$match": {"status": "active"}},
        {"$sort": {"views_count": -1, "likes_count": -1}},
        {"$limit": 400},
        {"$group": {"_id": "$brand", "n": {"$sum": "$views_count"}}},
        {"$sort": {"n": -1}},
        {"$limit": limit},
    ]
    brand_docs = [b async for b in db.listings.aggregate(pipe)]
    trending = [b["_id"] for b in brand_docs if b.get("_id")][:limit]
    return {"trending": trending}


@router.get("/for-you")
async def for_you(limit: int = 12, user: dict = Depends(get_current_user)):
    db = get_db()
    fav_docs = await db.favorites.find({"user_id": user["id"]}, {"_id": 0}).to_list(200)
    fav_listing_ids = [f["listing_id"] for f in fav_docs]
    order_docs = await db.orders.find({"buyer_id": user["id"]}, {"_id": 0, "listing_id": 1}).to_list(200)
    order_listing_ids = [o["listing_id"] for o in order_docs if o.get("listing_id")]
    seen_ids = list(set(fav_listing_ids + order_listing_ids))

    if not seen_ids:
        docs = await db.listings.find(
            {"status": "active", "seller_id": {"$ne": user["id"]}}, {"_id": 0},
        ).sort([("views_count", -1), ("likes_count", -1)]).limit(limit).to_list(limit)
        return docs

    hist = await db.listings.find(
        {"id": {"$in": seen_ids}}, {"_id": 0, "category_id": 1, "brand": 1}
    ).to_list(len(seen_ids))
    cat_ids = list({h["category_id"] for h in hist if h.get("category_id")})
    brands = list({h["brand"] for h in hist if h.get("brand")})
    query: dict = {"status": "active", "id": {"$nin": seen_ids}, "seller_id": {"$ne": user["id"]}}
    if cat_ids or brands:
        query["$or"] = [{"category_id": {"$in": cat_ids}}, {"brand": {"$in": brands}}]
    docs = await db.listings.find(query, {"_id": 0}).sort([
        ("is_flash_deal", -1), ("views_count", -1), ("likes_count", -1)
    ]).limit(limit).to_list(limit)
    if len(docs) < limit:
        need = limit - len(docs)
        extra = await db.listings.find(
            {"status": "active", "id": {"$nin": seen_ids + [d["id"] for d in docs]},
             "seller_id": {"$ne": user["id"]}},
            {"_id": 0},
        ).sort([("views_count", -1), ("likes_count", -1)]).limit(need).to_list(need)
        docs.extend(extra)
    return docs


@router.post("/recently-viewed/{listing_id}")
async def track_recently_viewed(listing_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    listing = await db.listings.find_one({"id": listing_id}, {"_id": 0, "id": 1})
    if not listing:
        raise HTTPException(404, "Listing not found")
    await db.recently_viewed.update_one(
        {"user_id": user["id"], "listing_id": listing_id},
        {"$set": {"user_id": user["id"], "listing_id": listing_id, "viewed_at": now_utc()}},
        upsert=True,
    )
    docs = await db.recently_viewed.find(
        {"user_id": user["id"]}, {"_id": 0, "viewed_at": 1, "listing_id": 1}
    ).sort("viewed_at", -1).to_list(200)
    if len(docs) > 24:
        stale_ids = [d["listing_id"] for d in docs[24:]]
        await db.recently_viewed.delete_many({"user_id": user["id"], "listing_id": {"$in": stale_ids}})
    return {"ok": True}


@router.get("/recently-viewed")
async def get_recently_viewed(limit: int = 12, user: dict = Depends(get_current_user)):
    db = get_db()
    entries = await db.recently_viewed.find(
        {"user_id": user["id"]}, {"_id": 0, "listing_id": 1, "viewed_at": 1}
    ).sort("viewed_at", -1).limit(limit).to_list(limit)
    if not entries:
        return []
    ids = [e["listing_id"] for e in entries]
    docs = await db.listings.find({"id": {"$in": ids}, "status": "active"}, {"_id": 0}).to_list(len(ids))
    order = {i: idx for idx, i in enumerate(ids)}
    docs.sort(key=lambda d: order.get(d["id"], 999))
    return docs


@router.get("/listings/{listing_id}/bundle")
async def listing_bundle(listing_id: str, limit: int = 6):
    db = get_db()
    src = await db.listings.find_one({"id": listing_id}, {"_id": 0, "seller_id": 1, "category_id": 1})
    if not src:
        raise HTTPException(404, "Listing not found")
    docs = await db.listings.find(
        {"seller_id": src["seller_id"], "id": {"$ne": listing_id}, "status": "active"},
        {"_id": 0},
    ).sort([("category_id", -1 if src.get("category_id") else 1), ("views_count", -1)]).limit(limit).to_list(limit)
    return docs


@router.get("/listings/{listing_id}/similar")
async def listing_similar(listing_id: str, limit: int = 12):
    """You may also like — items in the same category with a similar price band, from any seller.
    Falls back to popular items in the same category if too few similar-price matches."""
    db = get_db()
    src = await db.listings.find_one(
        {"id": listing_id},
        {"_id": 0, "seller_id": 1, "category_id": 1, "price": 1, "brand": 1},
    )
    if not src:
        raise HTTPException(404, "Listing not found")
    price = float(src.get("price") or 0)
    # ±40% band, min $5 spread
    spread = max(5.0, price * 0.4)
    lo, hi = max(0.0, price - spread), price + spread
    q_base = {
        "id": {"$ne": listing_id},
        "status": "active",
        "category_id": src.get("category_id"),
    }
    close = await db.listings.find(
        {**q_base, "price": {"$gte": lo, "$lte": hi}},
        {"_id": 0},
    ).sort([("views_count", -1), ("likes_count", -1)]).limit(limit).to_list(limit)
    if len(close) < limit:
        need = limit - len(close)
        have_ids = [d["id"] for d in close]
        rest = await db.listings.find(
            {**q_base, "id": {"$nin": have_ids + [listing_id]}},
            {"_id": 0},
        ).sort([("views_count", -1), ("likes_count", -1)]).limit(need).to_list(need)
        close.extend(rest)
    return close
