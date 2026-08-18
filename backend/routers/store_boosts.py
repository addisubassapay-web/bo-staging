"""Sponsored store slots — sellers pay to boost their store to the top of
storefront search for a specific category (or globally). Admins can also
grant complimentary boosts (comp) without payment.

Data shape stored on each store doc:
    store.boosts: [
        {
            id: uuid,
            category_id: str | None,   # None = global boost
            tier: 'bronze'|'silver'|'gold',
            starts_at: datetime,
            expires_at: datetime,
            source: 'paid'|'admin_comp',
            price_paid: float | None,
            session_id: str | None,    # Stripe session (paid)
        },
        ...
    ]

Ordering: expired entries are filtered at query time; a helper index score is
also cached on the store as `active_boost_score` for fast sorts.
"""
from __future__ import annotations
import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from .deps import get_db, get_current_user, require_admin

router = APIRouter()

TIERS = {
    "bronze": {"score": 1, "days": 7,  "price": 5.0},
    "silver": {"score": 2, "days": 14, "price": 12.0},
    "gold":   {"score": 3, "days": 30, "price": 25.0},
}


# ------------------------- helpers --------------------------------------
def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _recompute_active_boost_score(db, store_id: str) -> int:
    """Cache the top active boost score on the store doc so sort is O(1)."""
    store = await db.stores.find_one({"id": store_id}, {"_id": 0, "boosts": 1})
    if not store:
        return 0
    now = _now()
    active = []
    for b in (store.get("boosts") or []):
        exp = b.get("expires_at")
        if exp is None:
            continue
        if getattr(exp, "tzinfo", None) is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp > now:
            active.append(b)
    score = max((TIERS.get(b.get("tier"), {}).get("score", 0) for b in active), default=0)
    await db.stores.update_one({"id": store_id}, {"$set": {"active_boost_score": score}})
    return score


# ------------------------- seller-facing (paid) -------------------------
class BoostCheckoutCreate(BaseModel):
    store_id: str
    tier: str  # bronze | silver | gold
    category_id: Optional[str] = None
    origin_url: str


@router.post("/store-boost/checkout")
async def create_boost_checkout(payload: BoostCheckoutCreate, request: Request,
                                user: dict = Depends(get_current_user)):
    """Create a Stripe Checkout Session for a store-boost purchase.
    On payment success the /webhook/stripe route grants the boost."""
    from routers.stripe_payments import _stripe_client
    from emergentintegrations.payments.stripe.checkout import CheckoutSessionRequest

    tier = TIERS.get(payload.tier)
    if not tier:
        raise HTTPException(400, "Unknown tier")

    db = get_db()
    store = await db.stores.find_one({"id": payload.store_id}, {"_id": 0})
    if not store:
        raise HTTPException(404, "Store not found")
    if store.get("owner_id") != user["id"] and user.get("role") != "admin":
        raise HTTPException(403, "Not your store")
    if payload.category_id:
        cat = await db.categories.find_one({"id": payload.category_id}, {"_id": 0, "id": 1})
        if not cat:
            raise HTTPException(400, "Invalid category_id")

    origin = (payload.origin_url or "").rstrip("/")
    if not origin.startswith("http"):
        raise HTTPException(400, "Invalid origin_url")

    client = _stripe_client(request)
    req = CheckoutSessionRequest(
        amount=float(tier["price"]),
        currency="usd",
        success_url=f"{origin}/payment/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{origin}/payment/cancel?boost=1",
        metadata={
            "kind": "store_boost",
            "store_id": payload.store_id,
            "owner_id": user["id"],
            "tier": payload.tier,
            "category_id": payload.category_id or "",
            "days": str(tier["days"]),
        },
    )
    session = await client.create_checkout_session(req)
    now = _now()
    await db.store_boost_orders.insert_one({
        "session_id": session.session_id,
        "store_id": payload.store_id,
        "owner_id": user["id"],
        "tier": payload.tier,
        "category_id": payload.category_id,
        "days": tier["days"],
        "price": tier["price"],
        "status": "pending",
        "created_at": now,
    })
    # Also record in payment_transactions so the shared status poller works.
    await db.payment_transactions.insert_one({
        "session_id": session.session_id,
        "user_id": user["id"],
        "amount": tier["price"],
        "currency": "usd",
        "status": "initiated",
        "payment_status": "pending",
        "kind": "store_boost",
        "store_id": payload.store_id,
        "created_at": now,
        "updated_at": now,
    })
    return {"checkout_url": session.url, "session_id": session.session_id, "amount": tier["price"]}


async def finalize_paid_boost(db, session_id: str) -> Optional[dict]:
    """Called by the Stripe webhook when a store-boost session is paid.
    Idempotent — records the boost + expires_at on the store."""
    order = await db.store_boost_orders.find_one({"session_id": session_id}, {"_id": 0})
    if not order or order.get("status") == "granted":
        return None
    tier = TIERS.get(order["tier"])
    if not tier:
        return None
    now = _now()
    boost = {
        "id": str(uuid.uuid4()),
        "category_id": order.get("category_id"),
        "tier": order["tier"],
        "starts_at": now,
        "expires_at": now + timedelta(days=int(order["days"])),
        "source": "paid",
        "price_paid": float(order["price"]),
        "session_id": session_id,
    }
    await db.stores.update_one({"id": order["store_id"]}, {"$push": {"boosts": boost}})
    await db.store_boost_orders.update_one(
        {"session_id": session_id},
        {"$set": {"status": "granted", "boost_id": boost["id"], "granted_at": now}},
    )
    await _recompute_active_boost_score(db, order["store_id"])
    return boost


@router.get("/store-boost/status/{store_id}")
async def store_boost_status(store_id: str, user: dict = Depends(get_current_user)):
    """Return active boosts + available packages for a store."""
    db = get_db()
    store = await db.stores.find_one({"id": store_id}, {"_id": 0, "id": 1, "owner_id": 1,
                                                        "boosts": 1, "name": 1})
    if not store:
        raise HTTPException(404, "Store not found")
    if store.get("owner_id") != user["id"] and user.get("role") != "admin":
        raise HTTPException(403, "Not your store")
    now = _now()
    active = []
    for b in (store.get("boosts") or []):
        exp = b.get("expires_at")
        if exp is None:
            continue
        if getattr(exp, "tzinfo", None) is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp > now:
            active.append(b)
    return {
        "store_id": store_id,
        "store_name": store.get("name"),
        "active_boosts": active,
        "tiers": [{"id": k, **v} for k, v in TIERS.items()],
    }


# ------------------------- admin-facing (comp) --------------------------
class AdminBoostCreate(BaseModel):
    store_id: str
    tier: str
    category_id: Optional[str] = None
    days: int = Field(7, ge=1, le=180)
    reason: Optional[str] = None


@router.post("/admin/store-boost")
async def admin_grant_boost(payload: AdminBoostCreate, admin: dict = Depends(require_admin)):
    """Grant a complimentary boost without payment. Great for VIP sellers,
    onboarding perks, or fixing goodwill after a support incident."""
    if payload.tier not in TIERS:
        raise HTTPException(400, "Unknown tier")
    db = get_db()
    store = await db.stores.find_one({"id": payload.store_id}, {"_id": 0, "id": 1})
    if not store:
        raise HTTPException(404, "Store not found")
    if payload.category_id:
        cat = await db.categories.find_one({"id": payload.category_id}, {"_id": 0, "id": 1})
        if not cat:
            raise HTTPException(400, "Invalid category_id")
    now = _now()
    boost = {
        "id": str(uuid.uuid4()),
        "category_id": payload.category_id,
        "tier": payload.tier,
        "starts_at": now,
        "expires_at": now + timedelta(days=payload.days),
        "source": "admin_comp",
        "granted_by": admin["id"],
        "reason": payload.reason,
    }
    await db.stores.update_one({"id": payload.store_id}, {"$push": {"boosts": boost}})
    await _recompute_active_boost_score(db, payload.store_id)
    return {"ok": True, "boost": boost}


@router.get("/admin/store-boosts")
async def admin_list_boosts(_admin: dict = Depends(require_admin), active_only: bool = True):
    """List every store that has at least one boost (active by default)."""
    db = get_db()
    now = _now()
    q = {"boosts.0": {"$exists": True}} if not active_only else {"active_boost_score": {"$gt": 0}}
    stores = await db.stores.find(
        q, {"_id": 0, "id": 1, "name": 1, "slug": 1, "owner_id": 1, "boosts": 1,
            "active_boost_score": 1},
    ).sort("active_boost_score", -1).to_list(500)
    for s in stores:
        active = []
        for b in (s.get("boosts") or []):
            exp = b.get("expires_at")
            if exp is None:
                continue
            if getattr(exp, "tzinfo", None) is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if not active_only or exp > now:
                active.append(b)
        s["boosts"] = active
    return {"items": stores, "count": len(stores)}


class RevokeBoost(BaseModel):
    store_id: str
    boost_id: str


@router.post("/admin/store-boost/revoke")
async def admin_revoke_boost(payload: RevokeBoost, _admin: dict = Depends(require_admin)):
    db = get_db()
    await db.stores.update_one(
        {"id": payload.store_id},
        {"$pull": {"boosts": {"id": payload.boost_id}}},
    )
    await _recompute_active_boost_score(db, payload.store_id)
    return {"ok": True}
