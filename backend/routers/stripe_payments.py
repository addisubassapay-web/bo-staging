"""Stripe Checkout — real card payments for marketplace orders.

Flow:
  1. Frontend calls POST /api/checkout/stripe-session with the same OrderCreate
     payload it would send to /api/orders. We compute the exact total, save the
     pending payload (keyed by session_id) and return a hosted Stripe URL.
  2. Buyer completes payment on Stripe. Stripe redirects to
     /payment/success?session_id=cs_… on the frontend.
  3. Success page polls GET /api/payments/status/{session_id}. When Stripe
     confirms `paid`, we finalize the order (same code path as a wallet order)
     and return the created order id — so the buyer sees the same confirmation
     screen as before.
  4. In parallel, /api/webhook/stripe finalizes idempotently (belt-and-braces).

The finalize step reuses the SAME logic as the wallet checkout so all the
existing side-effects (seller earnings frozen, referral chain payouts,
notifications, dropship wholesale debit, etc.) apply automatically.
"""
from __future__ import annotations
import os
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from .deps import get_db, get_current_user

logger = logging.getLogger("stripe_payments")
router = APIRouter()


# --- Config ---------------------------------------------------------------
def _stripe_key() -> str:
    return os.environ.get("STRIPE_API_KEY") or "sk_test_emergent"


def _webhook_url_from(request: Request) -> str:
    """Build the webhook URL Stripe should deliver events to. Must be the
    exact path `/api/webhook/stripe` for the emergent helper."""
    host = str(request.base_url).rstrip("/")
    return f"{host}/api/webhook/stripe"


def _stripe_client(request: Request):
    from emergentintegrations.payments.stripe.checkout import StripeCheckout
    return StripeCheckout(api_key=_stripe_key(), webhook_url=_webhook_url_from(request))


# --- Order shim (reuse server.py logic) -----------------------------------
async def _finalize_paid_order(db, session_id: str) -> Optional[dict]:
    """Idempotent — finalizes a pending order once Stripe confirms payment.
    Returns the created order dict on success, or None if already finalized /
    not found."""
    pending = await db.stripe_pending_orders.find_one({"session_id": session_id}, {"_id": 0})
    if not pending:
        return None
    if pending.get("finalized_order_id"):
        return await db.orders.find_one({"id": pending["finalized_order_id"]}, {"_id": 0})

    # Import here to avoid a top-level circular import.
    from server import create_order, OrderCreate

    buyer = await db.users.find_one({"id": pending["buyer_id"]}, {"_id": 0, "password_hash": 0})
    if not buyer:
        logger.error(f"stripe finalize: buyer not found for session {session_id}")
        return None

    payload_dict = pending["payload"]
    # Ensure the payment method is recorded as `card` — the existing code
    # already handles this branch and creates the order at status=paid.
    payload_dict = {**payload_dict, "payment_method": "card"}
    order_payload = OrderCreate(**payload_dict)
    try:
        order = await create_order(order_payload, user=buyer)
    except HTTPException as e:
        # Stash the failure so admins can retry / refund manually.
        await db.stripe_pending_orders.update_one(
            {"session_id": session_id},
            {"$set": {"finalize_error": e.detail, "finalize_status": "failed",
                      "updated_at": datetime.now(timezone.utc)}},
        )
        logger.error(f"stripe finalize failed for {session_id}: {e.detail}")
        return None

    order_id = order.id if hasattr(order, "id") else order.get("id")
    await db.stripe_pending_orders.update_one(
        {"session_id": session_id},
        {"$set": {"finalized_order_id": order_id, "finalize_status": "done",
                  "updated_at": datetime.now(timezone.utc)}},
    )
    # Also mark the payment_transactions ledger.
    await db.payment_transactions.update_one(
        {"session_id": session_id, "payment_status": {"$ne": "paid"}},
        {"$set": {"payment_status": "paid", "status": "completed",
                  "order_id": order_id, "updated_at": datetime.now(timezone.utc)}},
    )
    return order.model_dump() if hasattr(order, "model_dump") else order


# --- Request / response models --------------------------------------------
class CheckoutSessionCreate(BaseModel):
    listing_id: str
    quantity: int = Field(1, ge=1, le=99)
    shipping_address: dict
    origin_url: str  # e.g. window.location.origin
    affiliate_code: Optional[str] = None
    share_ref: Optional[str] = None


# --- Endpoints ------------------------------------------------------------
@router.post("/checkout/stripe-session")
async def create_stripe_session(
    payload: CheckoutSessionCreate,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Create a Stripe Checkout Session for a marketplace order. Amounts are
    computed server-side (never trust the client). Persists the pending
    order payload so we can finalize on webhook / status poll."""
    from emergentintegrations.payments.stripe.checkout import CheckoutSessionRequest

    db = get_db()
    listing = await db.listings.find_one({"id": payload.listing_id, "status": "active"}, {"_id": 0})
    if not listing:
        raise HTTPException(404, "Listing not available")
    if listing["seller_id"] == user["id"]:
        raise HTTPException(400, "Cannot buy your own listing")

    # Compute the exact total the buyer will pay. Mirrors create_order()'s math.
    from server import get_settings
    settings = await get_settings()
    qty = max(1, min(int(payload.quantity or 1), 99))
    unit = float(listing["price"])
    gross = round(unit * qty, 2)
    tiers = settings.get("bulk_discount_tiers") or [
        {"min_qty": 5, "discount_pct": 5.0},
        {"min_qty": 10, "discount_pct": 10.0},
    ]
    active = max(
        (t for t in tiers if qty >= int(t.get("min_qty", 0))),
        key=lambda t: float(t.get("min_qty", 0)), default=None,
    )
    bulk_pct = float(active["discount_pct"]) if active else 0.0
    bulk_amt = round(gross * bulk_pct / 100.0, 2)
    amount = round(gross - bulk_amt, 2)
    shipping_fee = 0.0 if listing.get("shipping_paid_by") == "seller" else 5.99
    total = round(amount + shipping_fee, 2)
    if total < 0.5:
        raise HTTPException(400, "Order total is below Stripe's minimum")

    origin = (payload.origin_url or "").rstrip("/")
    if not origin.startswith("http"):
        raise HTTPException(400, "Invalid origin_url")

    client = _stripe_client(request)
    req = CheckoutSessionRequest(
        amount=float(total),
        currency="usd",
        success_url=f"{origin}/payment/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{origin}/payment/cancel?listing_id={payload.listing_id}",
        metadata={
            "buyer_id": user["id"],
            "listing_id": payload.listing_id,
            "listing_title": listing.get("title", "")[:200],
            "quantity": str(qty),
        },
    )
    session = await client.create_checkout_session(req)

    now = datetime.now(timezone.utc)
    await db.stripe_pending_orders.insert_one({
        "session_id": session.session_id,
        "buyer_id": user["id"],
        "amount": total,
        "currency": "usd",
        "listing_id": payload.listing_id,
        "payload": payload.model_dump(),
        "finalize_status": "pending",
        "finalized_order_id": None,
        "created_at": now,
        "updated_at": now,
    })
    await db.payment_transactions.insert_one({
        "session_id": session.session_id,
        "user_id": user["id"],
        "amount": total,
        "currency": "usd",
        "status": "initiated",
        "payment_status": "pending",
        "listing_id": payload.listing_id,
        "created_at": now,
        "updated_at": now,
    })

    return {"checkout_url": session.url, "session_id": session.session_id, "amount": total}


@router.get("/payments/status/{session_id}")
async def get_payment_status(session_id: str, request: Request):
    """Poll endpoint used by the /payment/success page. If Stripe reports the
    session as paid we finalize the marketplace order inline (idempotent).
    Unauthenticated — returns only status fields (no PII)."""
    db = get_db()
    record = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
    if not record:
        raise HTTPException(404, "Transaction not found")

    if record.get("payment_status") != "paid":
        try:
            client = _stripe_client(request)
            status = await client.get_checkout_status(session_id)
            if status.payment_status == "paid" or status.status == "complete":
                await db.payment_transactions.update_one(
                    {"session_id": session_id, "payment_status": {"$ne": "paid"}},
                    {"$set": {"payment_status": "paid", "status": "completed",
                              "updated_at": datetime.now(timezone.utc)}},
                )
                # Trigger order finalization now (same as webhook path).
                await _finalize_paid_order(db, session_id)
                # Also finalize store-boost purchases (idempotent).
                try:
                    from .store_boosts import finalize_paid_boost
                    await finalize_paid_boost(db, session_id)
                except Exception:
                    logger.exception("boost finalize failed for %s", session_id)
                record = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
        except Exception as e:
            logger.warning(f"stripe status poll failed for {session_id}: {e}")

    pending = await db.stripe_pending_orders.find_one({"session_id": session_id}, {"_id": 0})
    order_id = (pending or {}).get("finalized_order_id")
    return {
        "session_id": session_id,
        "status": record.get("status"),
        "payment_status": record.get("payment_status"),
        "amount": record.get("amount"),
        "currency": record.get("currency"),
        "order_id": order_id,
    }


@router.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    """Idempotent webhook receiver. Path must be `/api/webhook/stripe` — the
    emergent helper library expects that exact URL when computing signatures."""
    db = get_db()
    body = await request.body()
    sig = request.headers.get("Stripe-Signature", "")
    try:
        client = _stripe_client(request)
        event = await client.handle_webhook(body, sig)
    except Exception as e:
        logger.error(f"stripe webhook signature/parse error: {e}")
        raise HTTPException(400, "Invalid webhook payload")

    session_id = event.session_id if hasattr(event, "session_id") else None
    payment_status = event.payment_status if hasattr(event, "payment_status") else None

    if session_id and payment_status == "paid":
        await db.payment_transactions.update_one(
            {"session_id": session_id, "payment_status": {"$ne": "paid"}},
            {"$set": {"payment_status": "paid", "status": "completed",
                      "updated_at": datetime.now(timezone.utc)}},
        )
        await _finalize_paid_order(db, session_id)
        # Also grant store boost if this session was a boost purchase.
        try:
            from .store_boosts import finalize_paid_boost
            await finalize_paid_boost(db, session_id)
        except Exception:
            logger.exception("boost finalize failed for %s", session_id)

    return {"received": True}
