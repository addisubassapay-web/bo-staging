"""
Users router — public user snapshot endpoint.

Extraction step 1 of the server.py modularization. This endpoint is
fully self-contained (only touches db.users, returns a plain dict), so it
serves as a safe proof of the extraction pattern.

Additional user/auth endpoints will follow in staged commits, each
migrating helper functions (hash_password, credit_wallet, etc.) into
routers.deps before moving the route bodies.
"""
from __future__ import annotations
from fastapi import APIRouter, HTTPException

from .deps import get_db

router = APIRouter()


@router.get("/users/{user_id}/public")
async def get_public_user(user_id: str):
    """Public snapshot: verification badges, rating, sales — safe for anonymous viewing."""
    db = get_db()
    u = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    if not u:
        raise HTTPException(404, "User not found")
    return {
        "id": u["id"],
        "username": u.get("username"),
        "avatar": u.get("avatar"),
        "bio": u.get("bio", ""),
        "rating": u.get("rating", 5.0),
        "sales_count": u.get("sales_count", 0),
        "email_verified": bool(u.get("email_verified")),
        "phone_verified": bool(u.get("phone_verified")),
        "seller_status": u.get("seller_status", "none"),
        "created_at": u.get("created_at"),
    }
