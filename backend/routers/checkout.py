"""
Checkout helpers — coupons + saved shipping address prefill.

Kept as a separate router so it can grow into wholesale-tier discount
rules, gift cards, etc. without touching the giant server.py.
"""
from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .deps import get_db, get_current_user

router = APIRouter()

# Static coupon table — replace with a db-backed collection when marketing
# needs to add codes at runtime. Percent = 0.10 means 10% off subtotal.
COUPONS = {
    "WELCOME10": {"percent": 0.10, "max_off": 15.0, "min_subtotal": 10.0, "description": "10% off — first order"},
    "FLASH20":   {"percent": 0.20, "max_off": 30.0, "min_subtotal": 20.0, "description": "20% off — flash sale"},
    "MERCURI-GLOBAL5": {"percent": 0.05, "max_off": 8.0,  "min_subtotal": 0.0,  "description": "5% off — everyone"},
    "GULF15":    {"percent": 0.15, "max_off": 25.0, "min_subtotal": 30.0, "description": "15% off — Gulf shoppers"},
    "BULK":      {"tier": True,    "description": "Auto wholesale tier — 5+ items 5%, 10+ items 10%"},
}


class CouponValidate(BaseModel):
    code: str
    subtotal: float
    item_count: int = 1
    currency: Optional[str] = None


@router.post("/checkout/coupon/validate")
async def validate_coupon(payload: CouponValidate, user: dict = Depends(get_current_user)):
    """Instant coupon validation. Returns discount amount + reason so the
    Checkout UI can show inline feedback without a page reload."""
    code = (payload.code or "").strip().upper()
    if not code:
        raise HTTPException(400, "Enter a coupon code")
    entry = COUPONS.get(code)
    if not entry:
        raise HTTPException(404, "Invalid coupon code")

    subtotal = max(0.0, float(payload.subtotal or 0))
    items = max(1, int(payload.item_count or 1))

    # Automatic wholesale tier
    if entry.get("tier"):
        if items >= 10:
            pct, label = 0.10, "Wholesale tier: 10% off (10+ items)"
        elif items >= 5:
            pct, label = 0.05, "Wholesale tier: 5% off (5+ items)"
        else:
            raise HTTPException(400, "Add 5+ items for the wholesale tier")
        discount = round(subtotal * pct, 2)
        return {
            "code": code, "valid": True, "discount": discount,
            "percent": pct, "description": label,
        }

    # Percent coupon
    if subtotal < float(entry.get("min_subtotal", 0)):
        raise HTTPException(400, f"Coupon needs a subtotal of at least ${entry['min_subtotal']:.2f}")
    discount = min(
        round(subtotal * float(entry["percent"]), 2),
        float(entry["max_off"]),
    )
    return {
        "code": code, "valid": True, "discount": discount,
        "percent": entry["percent"], "description": entry["description"],
    }


@router.get("/checkout/last-address")
async def last_shipping_address(user: dict = Depends(get_current_user)):
    """Return the shipping address the user used on their most recent order,
    so Checkout can prefill the form for a one-tap repeat purchase."""
    db = get_db()
    last = await db.orders.find_one(
        {"buyer_id": user["id"], "shipping_address": {"$exists": True, "$ne": {}}},
        {"_id": 0, "shipping_address": 1, "created_at": 1},
        sort=[("created_at", -1)],
    )
    if not last or not last.get("shipping_address"):
        return {"has_saved": False, "address": {}}
    return {"has_saved": True, "address": last["shipping_address"]}
