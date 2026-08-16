"""
Stores router — public store search.

New in Phase C polish. Extends the existing store endpoints (still in
server.py) with a name/slug fuzzy search that powers the storefront
discovery UI.
"""
from __future__ import annotations
import re
from typing import List, Optional
from fastapi import APIRouter

from .deps import get_db

router = APIRouter()


@router.get("/stores-search")
async def search_stores(
    q: Optional[str] = None,
    tier: Optional[str] = None,
    limit: int = 24,
    skip: int = 0,
):
    """Search seller storefronts by name or slug. Case-insensitive substring
    match. Optional `tier` filter (bronze/silver/gold). Sorted by follower
    count desc then featured_rank asc so popular stores surface first."""
    db = get_db()
    query: dict = {}
    q = (q or "").strip()
    if q:
        rx = {"$regex": re.escape(q), "$options": "i"}
        query["$or"] = [{"name": rx}, {"slug": rx}, {"tagline": rx}]
    if tier and tier.lower() in ("bronze", "silver", "gold"):
        query["tier"] = tier.lower()

    limit = max(1, min(int(limit or 24), 60))
    skip = max(0, int(skip or 0))

    cursor = db.stores.find(
        query,
        {"_id": 0, "id": 1, "name": 1, "slug": 1, "tagline": 1, "logo": 1,
         "banner": 1, "tier": 1, "followers_count": 1, "sales_count": 1,
         "featured_rank": 1, "created_at": 1, "owner_id": 1},
    ).sort([("followers_count", -1), ("featured_rank", 1)]).skip(skip).limit(limit)
    items = await cursor.to_list(limit)
    total = await db.stores.count_documents(query)
    return {"items": items, "total": total, "q": q}


@router.get("/stores-search/count")
async def count_stores(q: Optional[str] = None, tier: Optional[str] = None):
    db = get_db()
    query: dict = {}
    q = (q or "").strip()
    if q:
        rx = {"$regex": re.escape(q), "$options": "i"}
        query["$or"] = [{"name": rx}, {"slug": rx}, {"tagline": rx}]
    if tier and tier.lower() in ("bronze", "silver", "gold"):
        query["tier"] = tier.lower()
    return {"total": await db.stores.count_documents(query)}
