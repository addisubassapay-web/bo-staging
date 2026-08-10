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
        return {"items": [], "queries": []}
    db = get_db()
    rx = {"$regex": re.escape(q), "$options": "i"}
    docs = await db.listings.find(
        {"status": "active", "$or": [{"title": rx}, {"brand": rx}]},
        {"_id": 0, "id": 1, "title": 1, "images": 1, "price": 1, "brand": 1, "category_name": 1},
    ).limit(limit).to_list(limit)
    items = [{
        "id": d["id"],
        "title": d["title"],
        "image": (d.get("images") or [None])[0],
        "price": d["price"],
        "brand": d.get("brand") or "",
        "category_name": d.get("category_name") or "",
    } for d in docs]
    brand_matches = await db.listings.distinct("brand", {"brand": rx, "status": "active"})
    cat_matches = await db.listings.distinct("category_name", {"category_name": rx, "status": "active"})
    queries = [b for b in brand_matches if b][:4] + [c for c in cat_matches if c][:4]
    return {"items": items, "queries": queries[:8]}


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
