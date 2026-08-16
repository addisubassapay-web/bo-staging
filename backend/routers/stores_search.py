"""
Stores router — public store search.

Powers storefront discovery UI. Case-insensitive substring match against
store name, slug, tagline, bio AND the owner's username so buyers can find
sellers by handle. Returns every store regardless of `is_active` so the
search truly surfaces "every store created by users".
"""
from __future__ import annotations
import re
from typing import List, Optional
from fastapi import APIRouter, Query

from .deps import get_db

router = APIRouter()

VALID_TIERS = ("none", "bronze", "silver", "gold")


async def _build_query(db, q: str, tier: Optional[str], include_inactive: bool) -> dict:
    query: dict = {}
    if not include_inactive:
        query["is_active"] = True
    if tier and tier.lower() in VALID_TIERS:
        query["verified_tier"] = tier.lower()

    q = (q or "").strip()
    if q:
        rx = {"$regex": re.escape(q), "$options": "i"}
        # Also match owner's username so /stores-search?q=elona resolves to Elona's store
        owner_ids: List[str] = [
            u["id"]
            for u in await db.users.find(
                {"username": rx}, {"_id": 0, "id": 1}
            ).to_list(200)
        ]
        or_clause: List[dict] = [
            {"name": rx},
            {"slug": rx},
            {"tagline": rx},
            {"bio": rx},
        ]
        if owner_ids:
            or_clause.append({"owner_id": {"$in": owner_ids}})
        query["$or"] = or_clause
    return query


@router.get("/stores-search")
async def search_stores(
    q: Optional[str] = None,
    tier: Optional[str] = None,
    limit: int = 24,
    skip: int = 0,
    include_inactive: bool = Query(True, description="If false, only return active stores"),
):
    """Search seller storefronts by name, slug, tagline, bio, or owner
    username. Optional `tier` filter (none/bronze/silver/gold). Sorted by
    follower count desc, featured_rank asc, then newest so popular stores
    surface first but every store is reachable via pagination."""
    db = get_db()
    query = await _build_query(db, q or "", tier, include_inactive)

    limit = max(1, min(int(limit or 24), 60))
    skip = max(0, int(skip or 0))

    cursor = (
        db.stores.find(
            query,
            {"_id": 0, "id": 1, "name": 1, "slug": 1, "tagline": 1, "logo": 1,
             "banner": 1, "verified_tier": 1, "followers_count": 1, "total_sales": 1,
             "featured_rank": 1, "created_at": 1, "owner_id": 1, "is_active": 1},
        )
        .sort([("followers_count", -1), ("featured_rank", 1), ("created_at", -1)])
        .skip(skip)
        .limit(limit)
    )
    items = await cursor.to_list(limit)

    # Enrich with owner username so the UI can render "by @username"
    if items:
        owner_ids = list({s["owner_id"] for s in items if s.get("owner_id")})
        owners = await db.users.find(
            {"id": {"$in": owner_ids}}, {"_id": 0, "id": 1, "username": 1, "avatar": 1}
        ).to_list(len(owner_ids))
        by_id = {o["id"]: o for o in owners}
        for s in items:
            owner = by_id.get(s.get("owner_id")) or {}
            s["owner_username"] = owner.get("username")
            s["owner_avatar"] = owner.get("avatar")

    total = await db.stores.count_documents(query)
    return {"items": items, "total": total, "q": (q or "").strip()}


@router.get("/stores-search/count")
async def count_stores(
    q: Optional[str] = None,
    tier: Optional[str] = None,
    include_inactive: bool = Query(True),
):
    db = get_db()
    query = await _build_query(db, q or "", tier, include_inactive)
    return {"total": await db.stores.count_documents(query)}
