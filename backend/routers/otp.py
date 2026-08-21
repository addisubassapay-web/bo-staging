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


@router.post("/otp/verify")
async def verify_otp_endpoint(payload: dict = Body(...), user: dict = Depends(get_current_user)):
    purpose = (payload.get("purpose") or "").strip()
    code = (payload.get("code") or "").strip()
    try:
        token = await email_otp.verify_otp(get_db(), user, purpose, code)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "otp_token": token, "purpose": purpose, "expires_in_seconds": email_otp.OTP_TOKEN_TTL_MINUTES * 60}
