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
    # Normalize inputs to prevent case-collision duplicates (e.g. "Foo@X.com"
    # vs "foo@x.com" being treated as separate accounts). EmailStr keeps the
    # case from Pydantic; lowercase it explicitly here so lookups match.
    email_norm = (body.email or "").strip().lower()
    username_norm = (body.username or "").strip()
    if not email_norm or not username_norm:
        raise HTTPException(status_code=400, detail="Email and username are required")
    existing = await db.users.find_one(
        {"$or": [{"email": email_norm}, {"username": username_norm}]}
    )
    if existing:
        raise HTTPException(status_code=400, detail="Email or username already exists")
    referred_by = None
    settings = await get_settings()
    invite_only = bool(settings.get("invite_only_signup", False))
    code = (body.referral_code or "").strip().upper()
    if code:
        ref = await db.users.find_one(
            {"referral_code": code}, {"_id": 0, "id": 1}
        )
        if not ref:
            # In invite-only mode a bad code must block. Outside invite-only
            # we silently ignore a bad code (legacy behaviour) so a typo doesn't
            # break a happy-path signup.
            if invite_only:
                raise HTTPException(status_code=403, detail="Invitation code is invalid or expired")
        else:
            referred_by = ref["id"]
    elif invite_only:
        raise HTTPException(status_code=403, detail="Registration is invite-only. Please enter a valid invitation code from a member.")
    user = User(email=email_norm, username=username_norm, referred_by=referred_by)
    doc = user.model_dump()
    doc["email"] = email_norm
    doc["username"] = username_norm
    doc["password_hash"] = hash_password(body.password)
    try:
        await db.users.insert_one(doc)
    except Exception as e:
        # Cover the concurrent-signup race: two requests both passed the
        # `existing` check, but Mongo's unique index on email/username
        # rejected the second insert. Return the friendly 400 instead of 500.
        if "duplicate key" in str(e).lower() or getattr(e, "code", None) == 11000:
            raise HTTPException(status_code=400, detail="Email or username already exists")
        raise
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
    email_lc = (body.email or "").strip().lower()
    user = await db.users.find_one({"email": email_lc})

    # Rate-limit unknown emails per IP so attackers can't enumerate accounts.
    if not user:
        # Prefer the first hop in X-Forwarded-For when present (we sit behind
        # the k8s ingress + a CDN). Falling back to request.client.host means
        # the throttle counts against the pod IP, which round-robins and
        # dilutes the limit. Use the first non-empty forwarded hop.
        xff = request.headers.get("x-forwarded-for", "")
        client_ip = None
        if xff:
            for hop in xff.split(","):
                hop = hop.strip()
                if hop:
                    client_ip = hop
                    break
        if not client_ip:
            client_ip = request.headers.get("x-real-ip") or (request.client.host if request.client else "unknown")
        key = f"ip:{client_ip}"
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

    # Legacy-account bypass: users flagged `must_change_password=True` (bulk
    # admin reset or migrated legacy accounts) are allowed to sign in with
    # ANY non-empty password — but only when the admin toggle
    # `legacy_bypass_enabled` is on in settings. The JWT they receive is
    # gated by `_PWD_CHANGE_ALLOWED_PATHS` in server.py, so the ONLY endpoint
    # they can hit is /auth/change-password — every other route returns 403
    # with password_change_required=True. is_active is still enforced.
    settings = await get_settings()
    bypass_toggle = bool(settings.get("legacy_bypass_enabled", True))
    legacy_bypass = bool(user.get("must_change_password", False)) and bypass_toggle

    if legacy_bypass:
        # Sanity: reject blank passwords so accidental empty submits don't
        # log the account in silently.
        if not (body.password or "").strip():
            raise HTTPException(status_code=401, detail=GENERIC_INVALID)
        # Audit the bypass so we have a paper-trail if anything goes wrong.
        try:
            await db.auth_audit.insert_one({
                "kind": "legacy_bypass_login",
                "user_id": user["id"],
                "email": user.get("email"),
                "ip": (request.client.host if request.client else "unknown"),
                "user_agent": request.headers.get("user-agent", ""),
                "at": _now(),
            })
        except Exception:
            pass
    else:
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
    return AuthResponse(
        token=token,
        user=UserPublic(**to_public_user(user)),
        password_change_required=bool(user.get("must_change_password", False)),
    )


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
        import os, logging
        reset_url = f"{os.environ['FRONTEND_ORIGIN']}/reset-password?token={token}"
        await db.password_resets.insert_one({
            "token": token,
            "user_id": user["id"],
            "email": email,
            "created_at": _now(),
            "expires_at": _now() + timedelta(minutes=60),
            "used_at": None,
        })
        # Send the real email (Hostinger SMTP when EMAIL_PROVIDER is set,
        # mock fallback otherwise). Failures never break the request.
        try:
            from services import mailer
            from services.email_templates import password_reset as tpl
            subject, html = tpl(reset_url, username=user.get("username"))
            result = await mailer.send_email(
                to=email, subject=subject, html=html, tags=["password_reset"]
            )
            provider = result.get("provider", "mock")
        except Exception as e:
            provider = f"error: {e}"
            logging.getLogger("email").error(f"password_reset mailer failed: {e}")

        await db.email_log.insert_one({
            "id": token[:16],
            "kind": "password_reset",
            "to": email,
            "user_id": user["id"],
            "url": reset_url,
            "provider": provider,
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
            # Clear any admin-imposed "must change" flag — the user has now
            # picked their own credential via the emailed reset link.
            "must_change_password": False,
        }},
    )
    await db.password_resets.update_one({"token": token}, {"$set": {"used_at": _now()}})
    return {"ok": True, "message": "Password updated. You can now sign in."}


@router.post("/auth/change-password")
async def change_password(payload: dict, user: dict = Depends(get_current_user)):
    """Change your own password. Required for users flagged
    `must_change_password` (admin reset or legacy migration); optional
    otherwise. `old_password` is required unless the flag is set, so an
    admin-reset user can pick a new one without knowing the temp password
    (they already proved possession via the JWT they got from login).
    """
    new_password = (payload.get("new_password") or "").strip()
    if len(new_password) < 6:
        raise HTTPException(400, "New password must be at least 6 characters")
    db = get_db()
    fresh = await db.users.find_one({"id": user["id"]})
    if not fresh:
        raise HTTPException(404, "User not found")
    must_change = bool(fresh.get("must_change_password", False))
    if not must_change:
        # Standard flow — require old password proof.
        old_password = payload.get("old_password") or ""
        if not old_password or not verify_password(old_password, fresh.get("password_hash", "")):
            raise HTTPException(401, "Current password is incorrect")
    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {
            "password_hash": hash_password(new_password),
            "must_change_password": False,
            "password_updated_at": _now(),
            "failed_login_attempts": 0,
            "locked_until": None,
        }},
    )
    return {"ok": True, "message": "Password updated."}
