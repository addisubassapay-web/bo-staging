"""
Auth router — register, login, and current-user endpoints.

Extracted from server.py in Server-Split Phase B. Uses the shim helpers
declared in `routers.deps` (which lazy-import from server) plus a lazy
import of the auth Pydantic models to avoid a circular import at
module-load time.
"""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException

from .deps import (
    get_db,
    get_current_user,
    hash_password,
    verify_password,
    create_token,
    to_public_user,
    get_settings,
    credit_wallet,
)

router = APIRouter()


def _models():
    """Lazy import server-side Pydantic models. Server.py finishes loading
    before any router endpoint fires, so this is always safe at call time."""
    from server import User, UserCreate, UserLogin, UserPublic, AuthResponse
    return User, UserCreate, UserLogin, UserPublic, AuthResponse


@router.post("/auth/register")
async def register(payload: dict):
    User, UserCreate, _UL, UserPublic, AuthResponse = _models()
    body = UserCreate(**payload)
    db = get_db()
    existing = await db.users.find_one(
        {"$or": [{"email": body.email}, {"username": body.username}]}
    )
    if existing:
        raise HTTPException(status_code=400, detail="Email or username already exists")
    referred_by = None
    if body.referral_code:
        ref = await db.users.find_one(
            {"referral_code": body.referral_code.upper()}, {"_id": 0, "id": 1}
        )
        if ref:
            referred_by = ref["id"]
    user = User(email=body.email, username=body.username, referred_by=referred_by)
    doc = user.model_dump()
    doc["password_hash"] = hash_password(body.password)
    await db.users.insert_one(doc)
    settings = await get_settings()
    if settings.get("signup_bonus", 0) > 0:
        await credit_wallet(user.id, settings["signup_bonus"], "bonus", "Signup bonus")
    token = create_token(user.id, user.role)
    fresh = await db.users.find_one({"id": user.id}, {"_id": 0, "password_hash": 0})
    return AuthResponse(token=token, user=UserPublic(**fresh))


@router.post("/auth/login")
async def login(payload: dict):
    _U, _UC, UserLogin, UserPublic, AuthResponse = _models()
    body = UserLogin(**payload)
    db = get_db()
    user = await db.users.find_one({"email": body.email})
    if not user or not verify_password(body.password, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="Account disabled")
    token = create_token(user["id"], user["role"])
    return AuthResponse(token=token, user=UserPublic(**to_public_user(user)))


@router.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    _U, _UC, _UL, UserPublic, _AR = _models()
    return UserPublic(**user)
