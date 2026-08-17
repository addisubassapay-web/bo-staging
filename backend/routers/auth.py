"""
Auth router — register, login, and current-user endpoints.

Extracted from server.py in Server-Split Phase B. Uses the shim helpers
declared in `routers.deps` (which lazy-import from server) plus a lazy
import of the auth Pydantic models to avoid a circular import at
module-load time.

Security additions (Feb 2026):
- Rate-limited login: after MAX_FAILED_ATTEMPTS bad passwords the account
  is soft-locked for LOCKOUT_MINUTES. Successful login clears the counter.
- Generic error message to avoid revealing which field was wrong.
- IP-scoped throttle fallback for unknown-email attempts.
"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request

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

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15
GENERIC_INVALID = "Invalid email or password"


def _models():
    """Lazy import server-side Pydantic models. Server.py finishes loading
    before any router endpoint fires, so this is always safe at call time."""
    from server import User, UserCreate, UserLogin, UserPublic, AuthResponse
    return User, UserCreate, UserLogin, UserPublic, AuthResponse


def _now():
    return datetime.now(timezone.utc)


async def _register_failed(db, user):
    attempts = int(user.get("failed_login_attempts", 0)) + 1
    updates: dict = {"failed_login_attempts": attempts, "last_failed_at": _now()}
    if attempts >= MAX_FAILED_ATTEMPTS:
        updates["locked_until"] = _now() + timedelta(minutes=LOCKOUT_MINUTES)
    await db.users.update_one({"id": user["id"]}, {"$set": updates})


async def _clear_failed(db, user_id):
    await db.users.update_one(
        {"id": user_id},
        {"$set": {"failed_login_attempts": 0, "locked_until": None, "last_login_at": _now()}},
    )


def _seconds_left(locked_until) -> int:
    if not locked_until:
        return 0
    if locked_until.tzinfo is None:
        locked_until = locked_until.replace(tzinfo=timezone.utc)
    return max(0, int((locked_until - _now()).total_seconds()))


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
async def login(payload: dict, request: Request):
    _U, _UC, UserLogin, UserPublic, AuthResponse = _models()
    body = UserLogin(**payload)
    db = get_db()
    user = await db.users.find_one({"email": body.email})

    # Rate-limit unknown emails per IP so attackers can't enumerate accounts.
    if not user:
        ip = (request.client.host if request.client else "unknown")
        key = f"ip:{ip}"
        ip_row = await db.login_throttle.find_one({"key": key}, {"_id": 0})
        attempts = int((ip_row or {}).get("attempts", 0)) + 1
        window_start = (ip_row or {}).get("window_start") or _now()
        if window_start.tzinfo is None:
            window_start = window_start.replace(tzinfo=timezone.utc)
        if (_now() - window_start).total_seconds() > LOCKOUT_MINUTES * 60:
            attempts = 1
            window_start = _now()
        await db.login_throttle.update_one(
            {"key": key},
            {"$set": {"attempts": attempts, "window_start": window_start, "last_at": _now()}},
            upsert=True,
        )
        if attempts > MAX_FAILED_ATTEMPTS * 2:
            raise HTTPException(status_code=429, detail="Too many attempts from this network. Try again later.")
        raise HTTPException(status_code=401, detail=GENERIC_INVALID)

    # Soft-lock check
    locked_until = user.get("locked_until")
    secs = _seconds_left(locked_until)
    if secs > 0:
        raise HTTPException(
            status_code=423,
            detail={
                "detail": f"Account locked after too many failed attempts. Retry in {secs}s.",
                "retry_after": secs,
            },
        )

    if not verify_password(body.password, user.get("password_hash", "")):
        await _register_failed(db, user)
        remaining = MAX_FAILED_ATTEMPTS - (int(user.get("failed_login_attempts", 0)) + 1)
        if remaining <= 0:
            raise HTTPException(
                status_code=423,
                detail={
                    "detail": f"Too many failed attempts. Account locked for {LOCKOUT_MINUTES} minutes.",
                    "retry_after": LOCKOUT_MINUTES * 60,
                },
            )
        raise HTTPException(status_code=401, detail=GENERIC_INVALID)

    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="Account disabled")

    await _clear_failed(db, user["id"])
    token = create_token(user["id"], user["role"])
    return AuthResponse(token=token, user=UserPublic(**to_public_user(user)))


@router.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    _U, _UC, _UL, UserPublic, _AR = _models()
    return UserPublic(**user)


@router.post("/auth/forgot-password")
async def forgot_password(payload: dict):
    """Start a password reset. Returns 200 regardless of whether the email
    exists (prevents user enumeration). Generates a one-time token stored
    with a 60-minute expiry and dispatches an email (mock provider until a
    real EMAIL_PROVIDER key is set)."""
    import secrets
    email = (payload.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(400, "Email is required")
    db = get_db()
    user = await db.users.find_one({"email": email}, {"_id": 0, "id": 1, "username": 1})
    if user:
        token = secrets.token_urlsafe(32)
        await db.password_resets.insert_one({
            "token": token,
            "user_id": user["id"],
            "email": email,
            "created_at": _now(),
            "expires_at": _now() + timedelta(minutes=60),
            "used_at": None,
        })
        # Email dispatch — mock provider logs the reset URL. When
        # EMAIL_PROVIDER is set later this will send a real message.
        import os, logging
        reset_url = f"{os.environ.get('FRONTEND_ORIGIN', 'https://mercari-clone-1.preview.emergentagent.com')}/reset-password?token={token}"
        logging.getLogger("email").info(
            f"[mock_email] password_reset to={email} url={reset_url}"
        )
        await db.email_log.insert_one({
            "id": token[:16],
            "kind": "password_reset",
            "to": email,
            "user_id": user["id"],
            "url": reset_url,
            "provider": "mock",
            "sent_at": _now(),
        })
    # Always the same response — no user enumeration.
    return {"ok": True, "message": "If that email is registered, a reset link is on its way."}


@router.post("/auth/reset-password")
async def reset_password(payload: dict):
    """Consume a one-time reset token and set a new password. Also clears
    any active lockout so the user can immediately sign in."""
    token = (payload.get("token") or "").strip()
    new_password = payload.get("new_password") or ""
    if not token or len(new_password) < 6:
        raise HTTPException(400, "Token required and password must be at least 6 characters")
    db = get_db()
    row = await db.password_resets.find_one({"token": token}, {"_id": 0})
    if not row:
        raise HTTPException(400, "Invalid or expired reset link")
    if row.get("used_at"):
        raise HTTPException(400, "This reset link has already been used")
    expires = row.get("expires_at")
    if expires and expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if not expires or expires < _now():
        raise HTTPException(400, "This reset link has expired. Request a new one.")

    await db.users.update_one(
        {"id": row["user_id"]},
        {"$set": {
            "password_hash": hash_password(new_password),
            "failed_login_attempts": 0,
            "locked_until": None,
            "password_updated_at": _now(),
        }},
    )
    await db.password_resets.update_one({"token": token}, {"$set": {"used_at": _now()}})
    return {"ok": True, "message": "Password updated. You can now sign in."}
