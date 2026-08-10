"""
Discovery + Seller dashboard router.

Endpoints:
- GET /api/shelves           — curated category "shelves" for the Home page
- GET /api/seller/dashboard  — live earnings, payouts, impressions for the seller
"""
from __future__ import annotations
from datetime import timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .deps import get_db, get_current_user, now_utc

router = APIRouter()


# Fallback shelf definitions (used only when the DB collection is missing).
SHELVES = [
    {"id": "fashion-day",   "title": "Fashion of the day",   "subtitle": "Trending styles",       "category_slugs": ["women", "men"], "sort": [("views_count", -1)], "limit": 8},
    {"id": "tech-under-50", "title": "Tech under $50",       "subtitle": "Gadgets, cables, extras", "category_slugs": ["electronics"], "price_lte": 50, "sort": [("likes_count", -1)], "limit": 8},
    {"id": "home-essentials","title": "Home essentials",     "subtitle": "Everyday for every home","category_slugs": ["home"], "sort": [("views_count", -1)], "limit": 8},
    {"id": "beauty-buzz",   "title": "Beauty buzz",          "subtitle": "Skincare, makeup & more","category_slugs": ["beauty"], "sort": [("likes_count", -1)], "limit": 8},
    {"id": "kids-fun",      "title": "For the kids",         "subtitle": "Toys, books & more",     "category_slugs": ["kids", "toys", "books"], "sort": [("views_count", -1)], "limit": 8},
]


@router.get("/shelves")
async def category_shelves():
    """Return curated category shelves for the Home page (admin-editable via DB)."""
    db = get_db()
    # Try DB-configured shelves first; fall back to defaults
    shelf_defs = await db.shelves.find({"enabled": True}, {"_id": 0}).sort("order", 1).to_list(50)
    if not shelf_defs:
        shelf_defs = [{**s, "enabled": True} for s in SHELVES]

    all_slugs = list({s for sh in shelf_defs for s in sh["category_slugs"]})
    cats = await db.categories.find({"slug": {"$in": all_slugs}}, {"_id": 0, "id": 1, "slug": 1}).to_list(100)
    slug_to_id = {c["slug"]: c["id"] for c in cats}

    out = []
    for sh in shelf_defs:
        ids = [slug_to_id[s] for s in sh["category_slugs"] if s in slug_to_id]
        if not ids:
            continue
        query = {"status": "active", "category_id": {"$in": ids}}
        if sh.get("price_lte") is not None:
            query["price"] = {"$lte": sh["price_lte"]}
        sort_field = "likes_count" if sh.get("sort_by") == "likes" else "views_count"
        sort_spec = sh.get("sort") or [(sort_field, -1)]
        limit = sh.get("limit", 8)
        docs = await db.listings.find(query, {"_id": 0}).sort(sort_spec).limit(limit).to_list(limit)
        if docs:
            out.append({
                "id": sh["id"],
                "title": sh["title"],
                "subtitle": sh["subtitle"],
                "category_slugs": sh["category_slugs"],
                "listings": docs,
            })
    return out


@router.get("/seller/dashboard")
async def seller_dashboard(user: dict = Depends(get_current_user)):
    """Live seller metrics: earnings series, pending payouts, active listings, deal impressions."""
    db = get_db()
    now = now_utc()
    since_30d = now - timedelta(days=30)

    orders = await db.orders.find(
        {"seller_id": user["id"], "created_at": {"$gte": since_30d}},
        {"_id": 0, "amount": 1, "platform_fee": 1, "shipping_fee": 1, "created_at": 1, "status": 1},
    ).to_list(2000)

    # Build a per-day earnings series across the last 30 days.
    buckets: dict[str, float] = {}
    for i in range(30, -1, -1):
        d = (now - timedelta(days=i)).strftime("%Y-%m-%d")
        buckets[d] = 0.0
    for o in orders:
        c = o.get("created_at")
        if isinstance(c, str):
            key = c[:10]
        else:
            key = c.strftime("%Y-%m-%d") if c else None
        if key and key in buckets:
            buckets[key] += float(o.get("amount", 0)) - float(o.get("platform_fee", 0))
    series = [{"date": d, "earnings": round(v, 2)} for d, v in buckets.items()]

    total_earnings = sum(x["earnings"] for x in series)
    total_orders = len(orders)
    today_key = now.strftime("%Y-%m-%d")
    today_orders = sum(1 for o in orders if (
        (o.get("created_at").strftime("%Y-%m-%d") if hasattr(o.get("created_at"), "strftime") else str(o.get("created_at"))[:10]) == today_key
    ))
    today_earnings = next((x["earnings"] for x in series if x["date"] == today_key), 0.0)

    # Wallet balance and pending withdrawals
    fresh_user = await db.users.find_one({"id": user["id"]}, {"_id": 0})
    wallet_balance = float(fresh_user.get("wallet_balance", 0)) if fresh_user else 0.0
    pending_payout = 0.0
    async for w in db.withdrawals.find({"user_id": user["id"], "status": "pending"}, {"_id": 0, "amount": 1}):
        pending_payout += float(w.get("amount", 0))

    # Listings snapshot
    active_listings = await db.listings.count_documents({"seller_id": user["id"], "status": "active"})
    sold_listings = await db.listings.count_documents({"seller_id": user["id"], "status": "sold"})
    flash_listings = await db.listings.count_documents({
        "seller_id": user["id"], "is_flash_deal": True, "flash_deal_ends_at": {"$gt": now},
    })

    # Impressions = sum of views_count across all seller listings (approximation)
    agg = await db.listings.aggregate([
        {"$match": {"seller_id": user["id"]}},
        {"$group": {"_id": None, "views": {"$sum": "$views_count"}, "likes": {"$sum": "$likes_count"}}},
    ]).to_list(1)
    total_views = int(agg[0]["views"]) if agg else 0
    total_likes = int(agg[0]["likes"]) if agg else 0

    # Recent orders preview (5 most-recent)
    recent = await db.orders.find(
        {"seller_id": user["id"]}, {"_id": 0}
    ).sort("created_at", -1).limit(5).to_list(5)
    for r in recent:
        c = r.get("created_at")
        if hasattr(c, "isoformat"):
            r["created_at"] = c.isoformat()

    # Weekly earnings goal + progress
    weekly_goal = float(fresh_user.get("weekly_earnings_goal", 0) or 0) if fresh_user else 0.0
    week_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    week_earnings = 0.0
    for o in orders:
        c = o.get("created_at")
        if hasattr(c, "tzinfo") and c.tzinfo is None:
            c = c.replace(tzinfo=week_start.tzinfo)
        if c and c >= week_start:
            week_earnings += float(o.get("amount", 0)) - float(o.get("platform_fee", 0))
    weekly = {
        "goal": round(weekly_goal, 2),
        "earned": round(week_earnings, 2),
        "progress_pct": min(100, round(week_earnings / weekly_goal * 100)) if weekly_goal > 0 else 0,
    }

    return {
        "series": series,
        "totals": {
            "earnings_30d": round(total_earnings, 2),
            "orders_30d": total_orders,
            "today_earnings": today_earnings,
            "today_orders": today_orders,
            "wallet_balance": wallet_balance,
            "pending_payout": pending_payout,
        },
        "listings": {
            "active": active_listings,
            "sold": sold_listings,
            "flash": flash_listings,
        },
        "engagement": {
            "views": total_views,
            "likes": total_likes,
        },
        "weekly": weekly,
        "recent_orders": recent,
    }


class SellerGoalIn(BaseModel):
    weekly_earnings_goal: float


@router.put("/seller/goal")
async def set_seller_goal(payload: SellerGoalIn, user: dict = Depends(get_current_user)):
    if payload.weekly_earnings_goal < 0 or payload.weekly_earnings_goal > 1_000_000:
        raise HTTPException(400, "Goal out of range")
    db = get_db()
    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {"weekly_earnings_goal": float(payload.weekly_earnings_goal)}},
    )
    return {"ok": True, "weekly_earnings_goal": float(payload.weekly_earnings_goal)}


# ---- Admin Shelf Management -----------------------------------------------
DEFAULT_SHELVES_SEED = [
    {"id": "fashion-day",   "title": "Fashion of the day",  "subtitle": "Trending styles",         "category_slugs": ["women", "men"],      "price_lte": None, "sort_by": "views",  "limit": 8, "enabled": True, "order": 0},
    {"id": "tech-under-50", "title": "Tech under $50",      "subtitle": "Gadgets, cables, extras", "category_slugs": ["electronics"],       "price_lte": 50,   "sort_by": "likes",  "limit": 8, "enabled": True, "order": 1},
    {"id": "home-essentials","title": "Home essentials",    "subtitle": "Everyday for every home", "category_slugs": ["home"],              "price_lte": None, "sort_by": "views",  "limit": 8, "enabled": True, "order": 2},
    {"id": "beauty-buzz",   "title": "Beauty buzz",         "subtitle": "Skincare, makeup & more", "category_slugs": ["beauty"],            "price_lte": None, "sort_by": "likes",  "limit": 8, "enabled": True, "order": 3},
    {"id": "kids-fun",      "title": "For the kids",        "subtitle": "Toys, books & more",      "category_slugs": ["kids", "toys", "books"], "price_lte": None, "sort_by": "views",  "limit": 8, "enabled": True, "order": 4},
]


async def _ensure_shelves_seeded():
    db = get_db()
    count = await db.shelves.count_documents({})
    if count == 0:
        await db.shelves.insert_many(DEFAULT_SHELVES_SEED)


async def _require_admin(user: dict = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(403, "Admin only")
    return user


@router.get("/admin/shelves")
async def list_shelves(_admin: dict = Depends(_require_admin)):
    await _ensure_shelves_seeded()
    db = get_db()
    docs = await db.shelves.find({}, {"_id": 0}).sort("order", 1).to_list(50)
    return docs


class ShelfUpdate(BaseModel):
    title: Optional[str] = None
    subtitle: Optional[str] = None
    category_slugs: Optional[List[str]] = None
    price_lte: Optional[float] = None
    sort_by: Optional[str] = None
    limit: Optional[int] = None
    enabled: Optional[bool] = None
    order: Optional[int] = None


@router.put("/admin/shelves/{shelf_id}")
async def update_shelf(shelf_id: str, payload: ShelfUpdate, _admin: dict = Depends(_require_admin)):
    db = get_db()
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        return {"ok": True, "no_changes": True}
    r = await db.shelves.update_one({"id": shelf_id}, {"$set": updates})
    if r.matched_count == 0:
        raise HTTPException(404, "Shelf not found")
    return {"ok": True}


@router.post("/admin/shelves/reorder")
async def reorder_shelves(payload: dict, _admin: dict = Depends(_require_admin)):
    ids = payload.get("ids") or []
    if not isinstance(ids, list) or not ids:
        raise HTTPException(400, "Provide ids: [shelf_id, ...] in desired order")
    db = get_db()
    for i, sid in enumerate(ids):
        await db.shelves.update_one({"id": sid}, {"$set": {"order": i}})
    return {"ok": True, "count": len(ids)}
