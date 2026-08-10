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
from fastapi import Depends, HTTPException
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

async def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    if not credentials:
        raise HTTPException(401, "Not authenticated")
    try:
        payload = jwt.decode(credentials.credentials, _jwt_secret(), algorithms=[JWT_ALG])
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid token")
    db = get_db()
    user = await db.users.find_one({"id": payload.get("sub")}, {"_id": 0})
    if not user:
        raise HTTPException(401, "User not found")
    return user

async def require_admin(user: dict = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(403, "Admin only")
    return user

def now_utc() -> datetime:
    return datetime.now(timezone.utc)
