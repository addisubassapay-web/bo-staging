"""
Shared dependency helpers for router modules.

This module centralizes the common FastAPI dependencies that all future
router extractions will need. It preserves the behaviour of the original
inline versions in server.py exactly — router files import from here
and server.py continues to work unchanged.
"""
from __future__ import annotations
import os
from datetime import datetime, timezone
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from motor.motor_asyncio import AsyncIOMotorClient

# --- Mongo client ---
_client: Optional[AsyncIOMotorClient] = None
_db = None

def get_db():
    global _client, _db
    if _db is None:
        _client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        _db = _client[os.environ["DB_NAME"]]
    return _db

# --- JWT constants (must match server.py). Read lazily so env is loaded first. ---
JWT_ALG = "HS256"

def _jwt_secret() -> str:
    return os.environ.get("JWT_SECRET", "change-me")

security = HTTPBearer(auto_error=False)

# Same allow-list as server.py::get_current_user — must stay in sync with it.
_PWD_CHANGE_ALLOWED_PATHS = frozenset({
    "/api/auth/change-password",
    "/api/auth/me",
    "/api/auth/logout",
    "/api/health",
})


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    # Dual-mode auth: accept EITHER the Authorization: Bearer header (legacy
    # localStorage flow) OR the HTTPOnly `bo_token` cookie (issued on
    # /auth/login). Falling back to the cookie means a session survives
    # frontend cache clears / storage wipes / accidental log-outs, which
    # otherwise surfaced as a scary "Not authenticated" toast on every
    # authenticated action.
    token = None
    if credentials and credentials.credentials:
        token = credentials.credentials
    else:
        token = request.cookies.get("bo_token")
    if not token:
        raise HTTPException(401, "Not authenticated")
    try:
        payload = jwt.decode(token, _jwt_secret(), algorithms=[JWT_ALG])
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid token")
    db = get_db()
    user = await db.users.find_one({"id": payload.get("sub")}, {"_id": 0})
    if not user:
        raise HTTPException(401, "User not found")
    # Server-side "must change password" gate.
    if user.get("must_change_password"):
        path = request.url.path.rstrip("/") or "/"
        if path not in _PWD_CHANGE_ALLOWED_PATHS:
            raise HTTPException(
                status_code=403,
                detail={
                    "message": "Password change required before continuing.",
                    "password_change_required": True,
                },
            )
    return user

async def require_admin(user: dict = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(403, "Admin only")
    return user


async def get_current_user_optional(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    """Return the current user if a valid bearer OR cookie is supplied,
    else None. Never raises — used by endpoints that accept both
    authenticated and guest callers."""
    token = None
    if credentials and credentials.credentials:
        token = credentials.credentials
    else:
        token = request.cookies.get("bo_token")
    if not token:
        return None
    try:
        payload = jwt.decode(token, _jwt_secret(), algorithms=[JWT_ALG])
    except jwt.PyJWTError:
        return None
    db = get_db()
    user = await db.users.find_one({"id": payload.get("sub")}, {"_id": 0})
    return user or None

def now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Phase A shims — thin wrappers around helpers currently defined in server.py.
# Router modules should import from here, NOT from server, to avoid circular
# imports at module-load time. Each shim lazy-imports its target the first
# time it is called (after server.py has finished loading).
#
# Once every route is extracted out of server.py we'll move the helper bodies
# themselves into this module and drop the shims.
# ---------------------------------------------------------------------------
def hash_password(password: str) -> str:
    from server import hash_password as _impl
    return _impl(password)

def verify_password(plain: str, hashed: str) -> bool:
    from server import verify_password as _impl
    return _impl(plain, hashed)

def create_token(user_id: str, role: str) -> str:
    from server import create_token as _impl
    return _impl(user_id, role)

def to_public_user(user: dict) -> dict:
    from server import to_public_user as _impl
    return _impl(user)

async def get_settings() -> dict:
    from server import get_settings as _impl
    return await _impl()

async def credit_wallet(user_id: str, amount: float, tx_type: str, description: str,
                        related_id: Optional[str] = None, frozen: bool = False):
    from server import credit_wallet as _impl
    return await _impl(user_id, amount, tx_type, description, related_id, frozen)

async def notify(user_id: str, ntype: str, title: str, body: str = "", link: Optional[str] = None):
    from server import notify as _impl
    return await _impl(user_id, ntype, title, body, link)

# Phase E shims — helpers needed by the listings/import extraction.
async def ensure_store_for_user(user_id: str):
    from server import ensure_store_for_user as _impl
    return await _impl(user_id)

def build_listings_query(q=None, category_id=None, price_min=None, price_max=None,
                         condition=None, featured=None, seller_id=None, brand=None,
                         status_filter="active"):
    from server import _build_listings_query as _impl
    # Underlying signature: (q, category_id, min_price, max_price, condition,
    # featured, seller_id, status_filter, brand=None). Pass by keyword so
    # future arg-order changes don't silently break.
    return _impl(q=q, category_id=category_id, min_price=price_min, max_price=price_max,
                 condition=condition, featured=featured, seller_id=seller_id,
                 status_filter=status_filter, brand=brand)

async def notify_store_followers(store_id: str, title: str, listing_id=None, bulk: bool = False):
    from server import _notify_store_followers as _impl
    return await _impl(store_id, title, listing_id, bulk)
