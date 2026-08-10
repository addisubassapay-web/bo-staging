"""
Discovery + Seller dashboard router.

Endpoints:
- GET /api/shelves           — curated category "shelves" for the Home page
- GET /api/seller/dashboard  — live earnings, payouts, impressions for the seller
"""
from __future__ import annotations
from datetime import timedelta
from fastapi import APIRouter, Depends

from .deps import get_db, get_current_user, now_utc

router = APIRouter()


# Curated shelf definitions — each shelf targets a specific slice of the catalog.
# Kept small on purpose so the Home page stays snappy.
SHELVES = [
    {"id": "fashion-day",   "title": "Fashion of the day",   "subtitle": "Trending styles",       "category_slugs": ["women", "men"], "sort": [("views_count", -1)], "limit": 8},
    {"id": "tech-under-50", "title": "Tech under $50",       "subtitle": "Gadgets, cables, extras", "category_slugs": ["electronics"], "price_lte": 50, "sort": [("likes_count", -1)], "limit": 8},
    {"id": "home-essentials","title": "Home essentials",     "subtitle": "Everyday for every home","category_slugs": ["home"], "sort": [("views_count", -1)], "limit": 8},
    {"id": "beauty-buzz",   "title": "Beauty buzz",          "subtitle": "Skincare, makeup & more","category_slugs": ["beauty"], "sort": [("likes_count", -1)], "limit": 8},
    {"id": "kids-fun",      "title": "For the kids",         "subtitle": "Toys, books & more",     "category_slugs": ["kids", "toys", "books"], "sort": [("views_count", -1)], "limit": 8},
]


@router.get("/shelves")
async def category_shelves():
    """Return curated category shelves for the Home page."""
    db = get_db()
    # Resolve category slugs to ids once
    all_slugs = list({s for sh in SHELVES for s in sh["category_slugs"]})
    cats = await db.categories.find({"slug": {"$in": all_slugs}}, {"_id": 0, "id": 1, "slug": 1}).to_list(100)
    slug_to_id = {c["slug"]: c["id"] for c in cats}

    out = []
    for sh in SHELVES:
        ids = [slug_to_id[s] for s in sh["category_slugs"] if s in slug_to_id]
        if not ids:
            continue
        query = {"status": "active", "category_id": {"$in": ids}}
        if sh.get("price_lte") is not None:
            query["price"] = {"$lte": sh["price_lte"]}
        docs = await db.listings.find(query, {"_id": 0}).sort(sh["sort"]).limit(sh["limit"]).to_list(sh["limit"])
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
        "recent_orders": recent,
    }
