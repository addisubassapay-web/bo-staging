"""
Google Auth router — Emergent-managed OAuth session exchange.

Flow:
1. Frontend redirects to https://auth.emergentagent.com/?redirect=<origin>/auth/callback
2. User completes Google sign-in and is redirected back with #session_id=... in the URL fragment
3. Frontend POSTs the session_id to /api/auth/google/session
4. This endpoint calls Emergent's /oauth/session-data to fetch verified user data
5. Idempotently upsert the user (link by email) and return our own JWT so the
   existing AuthContext + protected routes keep working unchanged.
"""
from __future__ import annotations
import re
import uuid
import httpx
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .deps import get_db, create_token, get_settings, credit_wallet

router = APIRouter()

EMERGENT_SESSION_DATA_URL = "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data"


class GoogleSessionExchange(BaseModel):
    session_id: str
    referral_code: str | None = None


def _slugify_username(name: str) -> str:
    base = re.sub(r"[^a-zA-Z0-9]+", "_", (name or "").lower()).strip("_")
    base = base[:16] or "user"
    return base


@router.post("/auth/google/session")
async def google_session_exchange(payload: GoogleSessionExchange):
    if not payload.session_id or len(payload.session_id) < 8:
        raise HTTPException(400, "Missing session_id")

    # 1) Exchange session_id for verified Google profile data
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                EMERGENT_SESSION_DATA_URL,
                headers={"X-Session-ID": payload.session_id},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"Auth service unreachable: {exc}") from exc

    if resp.status_code != 200:
        raise HTTPException(401, f"Session exchange failed ({resp.status_code})")

    profile = resp.json() or {}
    email = (profile.get("email") or "").strip().lower()
    name = profile.get("name") or ""
    picture = profile.get("picture") or None
    if not email:
        raise HTTPException(400, "No email returned by auth provider")

    db = get_db()

    # 2) Find existing user by email — Google-created accounts are linked, not duplicated
    existing = await db.users.find_one({"email": email}, {"_id": 0})

    if existing:
        # Refresh avatar / login timestamp if we now have fresher data
        updates: dict = {"last_google_login_at": datetime.now(timezone.utc)}
        if picture and not existing.get("avatar"):
            updates["avatar"] = picture
        if updates:
            await db.users.update_one({"id": existing["id"]}, {"$set": updates})
        user_doc = await db.users.find_one({"id": existing["id"]}, {"_id": 0, "password_hash": 0})
        token = create_token(user_doc["id"], user_doc.get("role", "user"))
        return {
            "token": token,
            "user": user_doc,
            "created": False,
        }

    # 3) Create a brand-new user linked to Google (no password_hash)
    # Optional referral resolution — same behaviour as /auth/register
    referred_by = None
    if payload.referral_code:
        ref = await db.users.find_one(
            {"referral_code": payload.referral_code.upper()}, {"_id": 0, "id": 1}
        )
        if ref:
            referred_by = ref["id"]

    # Ensure username is unique
    base_username = _slugify_username(name or email.split("@")[0])
    username = base_username
    n = 0
    while await db.users.find_one({"username": username}, {"_id": 0, "id": 1}):
        n += 1
        username = f"{base_username}{n}"

    new_id = str(uuid.uuid4())
    referral_code = uuid.uuid4().hex[:8].upper()
    doc = {
        "id": new_id,
        "email": email,
        "username": username,
        "full_name": name,
        "avatar": picture,
        "role": "user",
        "is_active": True,
        "auth_provider": "google",
        "email_verified": True,  # Google verifies emails
        "phone_verified": False,
        "seller_status": "none",
        "referral_code": referral_code,
        "referred_by": referred_by,
        "wallet_balance": 0.0,
        "wallet_frozen_balance": 0.0,
        "sales_count": 0,
        "rating": 5.0,
        "created_at": datetime.now(timezone.utc),
        "last_google_login_at": datetime.now(timezone.utc),
    }
    await db.users.insert_one(doc)

    # Signup bonus — mirror behaviour of the /auth/register endpoint
    settings = await get_settings()
    bonus = float(settings.get("signup_bonus", 0) or 0)
    if bonus > 0:
        await credit_wallet(new_id, bonus, "bonus", "Signup bonus")

    user_doc = await db.users.find_one({"id": new_id}, {"_id": 0, "password_hash": 0})
    token = create_token(new_id, "user")
    return {"token": token, "user": user_doc, "created": True}
