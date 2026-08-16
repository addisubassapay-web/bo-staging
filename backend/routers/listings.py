"""
Listings router — read-only endpoints. Server-Split Phases D–F.

Extracted so far:
  - GET /listings/{listing_id}  (single item + views_count increment)
  - GET /listings/count         (total count with same filter shape as /listings)

Deferred to Phase G:
  - GET  /listings           (full search + _build_listings_query heavy pipeline)
  - POST /listings           (seller gate + ensure_store_for_user)
  - PUT  /listings/{id}      (price-drop wishlist alerts)
  - DELETE /listings/{id}
  - POST /listings/import[/bulk]
"""
from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, HTTPException

from .deps import get_db, build_listings_query

router = APIRouter()


def _models():
    from server import Listing
    return Listing


@router.get("/listings/count")
async def count_listings(
    q: Optional[str] = None,
    category_id: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    condition: Optional[str] = None,
    brand: Optional[str] = None,
    featured: Optional[bool] = None,
    seller_id: Optional[str] = None,
    status_filter: Optional[str] = "active",
):
    """Total item count for the same filter shape as /listings — used to render pagination."""
    db = get_db()
    query = build_listings_query(
        q=q, category_id=category_id, price_min=min_price, price_max=max_price,
        condition=condition, brand=brand, featured=featured, seller_id=seller_id,
        status_filter=status_filter,
    )
    total = await db.listings.count_documents(query)
    return {"total": total}


@router.get("/listings/{listing_id}")
async def get_listing(listing_id: str):
    Listing = _models()
    db = get_db()
    doc = await db.listings.find_one({"id": listing_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Listing not found")
    await db.listings.update_one({"id": listing_id}, {"$inc": {"views_count": 1}})
    doc["views_count"] = doc.get("views_count", 0) + 1
    return Listing(**doc)
