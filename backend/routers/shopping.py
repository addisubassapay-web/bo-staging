"""
Favorites + Cart router — Server-Split Phase C.

Small, self-contained slice extracted from server.py. Both feature areas
share a similar pattern: (user_id, listing_id) collection joined with the
listings collection to return full Listing objects.
"""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import List
from fastapi import APIRouter, Depends

from .deps import get_db, get_current_user

router = APIRouter()


def _models():
    from server import Listing, Favorite, CartItem
    return Listing, Favorite, CartItem


# =========================
# Favorites
# =========================
@router.get("/favorites")
async def get_favorites(user: dict = Depends(get_current_user)):
    Listing, _F, _C = _models()
    db = get_db()
    favs = await db.favorites.find({"user_id": user["id"]}, {"_id": 0}).to_list(500)
    ids = [f["listing_id"] for f in favs]
    docs = await db.listings.find({"id": {"$in": ids}}, {"_id": 0}).to_list(500)
    return [Listing(**d) for d in docs]


@router.post("/favorites/{listing_id}")
async def add_favorite(listing_id: str, user: dict = Depends(get_current_user)):
    _L, Favorite, _C = _models()
    db = get_db()
    existing = await db.favorites.find_one({"user_id": user["id"], "listing_id": listing_id})
    if existing:
        return {"ok": True, "already": True}
    fav = Favorite(user_id=user["id"], listing_id=listing_id)
    await db.favorites.insert_one(fav.model_dump())
    await db.listings.update_one({"id": listing_id}, {"$inc": {"likes_count": 1}})
    return {"ok": True}


@router.delete("/favorites/{listing_id}")
async def remove_favorite(listing_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    result = await db.favorites.delete_one({"user_id": user["id"], "listing_id": listing_id})
    if result.deleted_count > 0:
        await db.listings.update_one({"id": listing_id}, {"$inc": {"likes_count": -1}})
    return {"ok": True}


# =========================
# Cart
# =========================
@router.get("/cart")
async def get_cart(user: dict = Depends(get_current_user)):
    Listing, _F, _C = _models()
    db = get_db()
    items = await db.cart_items.find({"user_id": user["id"]}, {"_id": 0}).to_list(500)
    ids = [i["listing_id"] for i in items]
    docs = await db.listings.find({"id": {"$in": ids}, "status": "active"}, {"_id": 0}).to_list(500)
    return [Listing(**d) for d in docs]


@router.post("/cart/{listing_id}")
async def add_to_cart(listing_id: str, user: dict = Depends(get_current_user)):
    _L, _F, CartItem = _models()
    db = get_db()
    existing = await db.cart_items.find_one({"user_id": user["id"], "listing_id": listing_id})
    if existing:
        return {"ok": True, "already": True}
    item = CartItem(user_id=user["id"], listing_id=listing_id)
    await db.cart_items.insert_one(item.model_dump())
    return {"ok": True}


@router.delete("/cart/{listing_id}")
async def remove_from_cart(listing_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    await db.cart_items.delete_one({"user_id": user["id"], "listing_id": listing_id})
    return {"ok": True}
