"""
Coupons CRUD — moves the static coupon table into MongoDB so marketing
can add, toggle, and delete codes without a deploy.

Every route lives here to keep the concern testable and to give the
future Coupons Admin UI a single import surface.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
import uuid

from .deps import get_db, get_current_user, require_admin

router = APIRouter()


class Coupon(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    code: str
    percent: float = 0.0
    max_off: float = 100.0
    min_subtotal: float = 0.0
    tier: bool = False
    description: str = ""
    active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CouponUpsert(BaseModel):
    code: str
    percent: float = 0.0
    max_off: float = 100.0
    min_subtotal: float = 0.0
    tier: bool = False
    description: str = ""
    active: bool = True


class CouponValidate(BaseModel):
    code: str
    subtotal: float
    item_count: int = 1
    currency: Optional[str] = None


async def _ensure_seed(db):
    """First-run seed so the same defaults appear until an admin edits them."""
    if await db.coupons.count_documents({}) > 0:
        return
    defaults = [
        Coupon(code="WELCOME10", percent=0.10, max_off=15, min_subtotal=10, description="10% off — first order"),
        Coupon(code="FLASH20",   percent=0.20, max_off=30, min_subtotal=20, description="20% off — flash sale"),
        Coupon(code="MERCURI-GLOBAL5", percent=0.05, max_off=8,  min_subtotal=0,  description="5% off — everyone"),
        Coupon(code="GULF15",    percent=0.15, max_off=25, min_subtotal=30, description="15% off — Gulf shoppers"),
        Coupon(code="BULK",      tier=True,    description="Auto wholesale tier — 5+ items 5%, 10+ items 10%"),
    ]
    await db.coupons.insert_many([c.model_dump() for c in defaults])


# =========================
# Admin CRUD
# =========================
@router.get("/admin/coupons")
async def list_coupons(_admin: dict = Depends(require_admin)):
    db = get_db()
    await _ensure_seed(db)
    items = await db.coupons.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return items


@router.post("/admin/coupons")
async def create_coupon(payload: CouponUpsert, _admin: dict = Depends(require_admin)):
    db = get_db()
    code = payload.code.strip().upper()
    if not code:
        raise HTTPException(400, "Code required")
    existing = await db.coupons.find_one({"code": code}, {"_id": 0, "id": 1})
    if existing:
        raise HTTPException(400, f"Coupon {code} already exists")
    doc = Coupon(**{**payload.model_dump(), "code": code}).model_dump()
    await db.coupons.insert_one(doc)
    return {"ok": True, "coupon": {**doc, "_id": None} | {k: v for k, v in doc.items() if k != "_id"}}


@router.put("/admin/coupons/{coupon_id}")
async def update_coupon(coupon_id: str, payload: CouponUpsert, _admin: dict = Depends(require_admin)):
    db = get_db()
    updates = payload.model_dump()
    updates["code"] = payload.code.strip().upper()
    r = await db.coupons.update_one({"id": coupon_id}, {"$set": updates})
    if r.matched_count == 0:
        raise HTTPException(404, "Coupon not found")
    fresh = await db.coupons.find_one({"id": coupon_id}, {"_id": 0})
    return {"ok": True, "coupon": fresh}


@router.delete("/admin/coupons/{coupon_id}")
async def delete_coupon(coupon_id: str, _admin: dict = Depends(require_admin)):
    db = get_db()
    r = await db.coupons.delete_one({"id": coupon_id})
    if r.deleted_count == 0:
        raise HTTPException(404, "Coupon not found")
    return {"ok": True}


# =========================
# Public validation (replaces the static /api/checkout/coupon/validate)
# =========================
@router.post("/coupons/validate")
async def validate_coupon(payload: CouponValidate, user: dict = Depends(get_current_user)):
    db = get_db()
    await _ensure_seed(db)
    code = (payload.code or "").strip().upper()
    if not code:
        raise HTTPException(400, "Enter a coupon code")
    entry = await db.coupons.find_one({"code": code, "active": True}, {"_id": 0})
    if not entry:
        raise HTTPException(404, "Invalid coupon code")

    subtotal = max(0.0, float(payload.subtotal or 0))
    items = max(1, int(payload.item_count or 1))

    if entry.get("tier"):
        if items >= 10:
            pct, label = 0.10, "Wholesale tier: 10% off (10+ items)"
        elif items >= 5:
            pct, label = 0.05, "Wholesale tier: 5% off (5+ items)"
        else:
            raise HTTPException(400, "Add 5+ items for the wholesale tier")
        discount = round(subtotal * pct, 2)
        return {"code": code, "valid": True, "discount": discount, "percent": pct, "description": label}

    if subtotal < float(entry.get("min_subtotal", 0)):
        raise HTTPException(400, f"Coupon needs a subtotal of at least ${entry['min_subtotal']:.2f}")
    discount = min(
        round(subtotal * float(entry["percent"]), 2),
        float(entry["max_off"]),
    )
    return {"code": code, "valid": True, "discount": discount, "percent": entry["percent"], "description": entry["description"]}
