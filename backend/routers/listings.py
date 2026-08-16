"""
Listings router — read-only endpoints. Server-Split Phase D (step 1).

Extracted so far:
  - GET /listings/{listing_id}  (single item + views_count increment)

Deferred to Phase E (larger extraction with helper coupling):
  - GET  /listings           (full search + _build_listings_query)
  - GET  /listings/count
  - POST /listings           (seller gate + ensure_store_for_user)
  - PUT  /listings/{id}      (price-drop wishlist alerts)
  - DELETE /listings/{id}
  - POST /listings/import[/bulk]
"""
from __future__ import annotations
from fastapi import APIRouter, HTTPException

from .deps import get_db

router = APIRouter()


def _models():
    from server import Listing
    return Listing


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
