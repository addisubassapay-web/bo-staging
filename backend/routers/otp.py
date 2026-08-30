"""Email OTP endpoints — request & verify. Both require a logged-in user."""
from fastapi import APIRouter, Body, Depends, HTTPException

from services import email_otp
from .deps import get_current_user, get_db

router = APIRouter()


@router.post("/otp/request")
async def request_otp_endpoint(payload: dict = Body(...), user: dict = Depends(get_current_user)):
    purpose = (payload.get("purpose") or "").strip()
    try:
        return await email_otp.request_otp(get_db(), user, purpose)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        # Mailer failure — surface as 502 so the UI can show a real error
        # instead of a false "code sent" toast.
        raise HTTPException(502, str(e))


@router.post("/otp/verify")
async def verify_otp_endpoint(payload: dict = Body(...), user: dict = Depends(get_current_user)):
    purpose = (payload.get("purpose") or "").strip()
    code = (payload.get("code") or "").strip()
    try:
        token = await email_otp.verify_otp(get_db(), user, purpose, code)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "otp_token": token, "purpose": purpose, "expires_in_seconds": email_otp.OTP_TOKEN_TTL_MINUTES * 60}


@router.get("/otp/inbox")
async def otp_inbox_endpoint(user: dict = Depends(get_current_user)):
    """In-platform OTP inbox. Returns the caller's active + recent OTP
    codes so users can grab the 6-digit code inside BlueOcean itself
    instead of switching to email. Only returns codes that belong to
    the authenticated user."""
    from datetime import datetime, timezone
    db = get_db()
    now = datetime.now(timezone.utc)
    cursor = db.otp_inbox.find(
        {"user_id": user["id"], "expires_at": {"$gt": now}},
        {"_id": 0, "id": 1, "purpose": 1, "label": 1, "code": 1,
         "created_at": 1, "expires_at": 1, "read": 1},
    ).sort("created_at", -1).limit(10)
    items = [doc async for doc in cursor]
    # Mark as read (idempotent — flips false→true, TTL cleans up in 10min)
    if items:
        await db.otp_inbox.update_many(
            {"user_id": user["id"], "read": False},
            {"$set": {"read": True, "read_at": now}},
        )
    return {"items": items, "count": len(items)}

