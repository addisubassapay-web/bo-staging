"""Email OTP service for sensitive actions (withdrawals, seller apply, cashouts, password reset).

Design:
- 6-digit code emailed to the user via existing Hostinger SMTP (`services/mailer`).
- Code stored as SHA-256 hash — never plaintext.
- 10-minute TTL enforced with Mongo TTL index on `expires_at`.
- Rate-limited: at most 5 requests / hour per (user, purpose).
- Verification returns a short-lived opaque token that guards the actual sensitive endpoint.
"""
from __future__ import annotations

import hashlib
import logging
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

OTP_TTL_MINUTES = 10
OTP_TOKEN_TTL_MINUTES = 5
MAX_REQUESTS_PER_HOUR = 5
MAX_VERIFY_ATTEMPTS = 5

VALID_PURPOSES = {"withdrawal", "cashout", "seller_apply", "password_reset"}
PURPOSE_LABELS = {
    "withdrawal": "wallet withdrawal",
    "cashout": "seller cashout",
    "seller_apply": "seller application",
    "password_reset": "password reset",
}


def _hash(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


async def ensure_indexes(db):
    """Idempotent — safe to call on every startup."""
    await db.email_otps.create_index("expires_at", expireAfterSeconds=0)
    await db.email_otps.create_index([("user_id", 1), ("purpose", 1)])
    await db.otp_tokens.create_index("expires_at", expireAfterSeconds=0)


async def request_otp(db, user: dict, purpose: str) -> dict:
    """Create + email a fresh OTP. Returns metadata (not the code)."""
    if purpose not in VALID_PURPOSES:
        raise ValueError(f"Unknown purpose. Valid: {sorted(VALID_PURPOSES)}")

    now = datetime.now(timezone.utc)
    hour_ago = now - timedelta(hours=1)
    # Count BEFORE any mutation so the rate-limit isn't reset by our own delete.
    recent = await db.email_otps.count_documents({
        "user_id": user["id"], "purpose": purpose, "created_at": {"$gte": hour_ago},
    })
    if recent >= MAX_REQUESTS_PER_HOUR:
        raise ValueError(f"Too many OTP requests. Try again in an hour.")

    code = f"{secrets.randbelow(1_000_000):06d}"
    otp_doc = {
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "purpose": purpose,
        "code_hash": _hash(code),
        "attempts": 0,
        "created_at": now,
        "expires_at": now + timedelta(minutes=OTP_TTL_MINUTES),
        "used_at": None,
    }
    # Invalidate any previous unused OTPs for the same (user, purpose) — but
    # KEEP the row so it still counts toward the hourly quota. We just mark it
    # `used_at` so it can't be verified anymore. TTL cleans it up in 10 min.
    await db.email_otps.update_many(
        {"user_id": user["id"], "purpose": purpose, "used_at": None},
        {"$set": {"used_at": now, "superseded": True}},
    )
    await db.email_otps.insert_one(otp_doc)

    # Send the email — never block on failure
    label = PURPOSE_LABELS[purpose]
    subject = f"Your Ocean verification code: {code}"
    html = f"""
    <div style="font-family:system-ui,Segoe UI,Arial,sans-serif;max-width:520px;margin:0 auto;color:#111">
      <h2 style="color:#FF211F;margin:0 0 12px">Confirm your {label}</h2>
      <p>Hi {user.get('username','there')},</p>
      <p>Use this 6-digit code to confirm your <b>{label}</b>. The code expires in {OTP_TTL_MINUTES} minutes.</p>
      <div style="font-size:32px;letter-spacing:8px;font-weight:bold;background:#FFF3F2;color:#FF211F;text-align:center;padding:18px;border-radius:8px;margin:16px 0">{code}</div>
      <p style="color:#666;font-size:13px">If you didn't request this, ignore this email — nothing will happen.</p>
      <p style="color:#666;font-size:12px;margin-top:20px">— Ocean Trust &amp; Safety</p>
    </div>
    """
    try:
        from services import mailer
        await mailer.send_email(
            to=user["email"], subject=subject, html=html,
            tags=["email_otp", f"otp_{purpose}"],
        )
    except Exception as e:
        # Roll back the DB row so a retry can create a fresh code, then
        # surface the failure to the caller so the UI shows a real error
        # instead of a false "code sent" success.
        logger.error(f"email_otp mailer failed for {user['id']}: {e}")
        try:
            await db.email_otps.update_one({"id": otp_doc["id"]}, {"$set": {"superseded": True, "used_at": now}})
        except Exception:
            pass
        raise RuntimeError(f"Could not send the verification email: {e}") from e
    return {
        "ok": True,
        "purpose": purpose,
        "expires_in_seconds": OTP_TTL_MINUTES * 60,
        "sent_to_email": user["email"],
    }


async def verify_otp(db, user: dict, purpose: str, code: str) -> str:
    """Verify the code. Returns a short-lived opaque token that must be
    supplied to the guarded endpoint via `x-otp-token` header. Raises
    ValueError on any failure."""
    if purpose not in VALID_PURPOSES:
        raise ValueError("Invalid purpose")
    code = (code or "").strip()
    if len(code) != 6 or not code.isdigit():
        raise ValueError("Enter the 6-digit code from your email")

    now = datetime.now(timezone.utc)
    otp = await db.email_otps.find_one({
        "user_id": user["id"], "purpose": purpose, "used_at": None,
        "expires_at": {"$gt": now},
    })
    if not otp:
        raise ValueError("No active code. Request a new one.")
    if otp.get("attempts", 0) >= MAX_VERIFY_ATTEMPTS:
        raise ValueError("Too many wrong attempts. Request a new code.")
    if otp["code_hash"] != _hash(code):
        await db.email_otps.update_one({"id": otp["id"]}, {"$inc": {"attempts": 1}})
        raise ValueError("Incorrect code")

    # Mark OTP as used + issue a token
    await db.email_otps.update_one({"id": otp["id"]}, {"$set": {"used_at": now}})

    # Successfully receiving + reading a code from the account email proves
    # email ownership — so mark the user email_verified if they weren't
    # already. Idempotent; skipped when the flag is already set.
    if not user.get("email_verified"):
        try:
            await db.users.update_one(
                {"id": user["id"], "email_verified": {"$ne": True}},
                {"$set": {"email_verified": True, "email_verified_at": now}},
            )
        except Exception as e:
            logger.warning(f"verify_otp: failed to backfill email_verified for {user['id']}: {e}")

    token = f"otp_{secrets.token_urlsafe(24)}"
    await db.otp_tokens.insert_one({
        "token": token,
        "user_id": user["id"],
        "purpose": purpose,
        "issued_at": now,
        "expires_at": now + timedelta(minutes=OTP_TOKEN_TTL_MINUTES),
    })
    return token


async def consume_token(db, user_id: str, purpose: str, token: Optional[str]) -> None:
    """Called from a sensitive endpoint to redeem the OTP token.
    Deletes the token so it can only be used once. Raises ValueError on failure."""
    if not token or not token.startswith("otp_"):
        raise ValueError(f"Missing OTP token. Verify your email first (purpose={purpose}).")
    now = datetime.now(timezone.utc)
    doc = await db.otp_tokens.find_one_and_delete({
        "token": token, "user_id": user_id, "purpose": purpose,
        "expires_at": {"$gt": now},
    })
    if not doc:
        raise ValueError("OTP token expired or already used. Verify again.")
