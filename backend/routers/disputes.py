"""Disputes / returns router — extracted from server.py.

Buyer files dispute → optional auto-refund → admin resolves → dispute chat
thread powers the back-and-forth. Ledger book-keeping and notifications
are delegated to shared helpers.
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from models.disputes import (
    Dispute, DisputeCreate, DisputeResolveIn,
    DisputeMessage, DisputeMessageCreate, DISPUTE_STATUSES,
)
from services import ledger
from .deps import get_db, get_current_user, require_admin, notify, get_settings

router = APIRouter()
logger = logging.getLogger(__name__)


async def _get_order_or_404(order_id: str) -> dict:
    db = get_db()
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(404, "Order not found")
    return order


async def _dispute_role_for(user: dict, d: dict) -> str:
    if user.get("role") == "admin":
        return "admin"
    if user["id"] == d.get("buyer_id"):
        return "buyer"
    if user["id"] == d.get("seller_id"):
        return "seller"
    raise HTTPException(403, "Not allowed")


@router.post("/disputes", response_model=Dispute)
async def create_dispute(payload: DisputeCreate, user: dict = Depends(get_current_user)):
    """Buyer opens a dispute on one of their orders. Delivered/paid/shipped orders eligible."""
    order = await _get_order_or_404(payload.order_id)
    if order["buyer_id"] != user["id"]:
        raise HTTPException(403, "Only the buyer can open a dispute for this order")
    if order.get("status") not in ("paid", "shipped", "delivered"):
        raise HTTPException(400, "This order is not eligible for a dispute")
    db = get_db()
    existing = await db.disputes.find_one(
        {"order_id": payload.order_id, "status": {"$in": ["open", "reviewing"]}}, {"_id": 0}
    )
    if existing:
        raise HTTPException(400, "An open dispute already exists for this order")
    if not (payload.description or "").strip():
        raise HTTPException(400, "Please describe what went wrong")

    dispute = Dispute(
        order_id=order["id"],
        buyer_id=user["id"],
        buyer_name=user["username"],
        seller_id=order["seller_id"],
        listing_id=order["listing_id"],
        listing_title=order["listing_title"],
        listing_image=order.get("listing_image"),
        amount=float(order.get("amount", 0)),
        reason=payload.reason,
        description=payload.description.strip(),
        photos=[p for p in (payload.photos or []) if isinstance(p, str)][:8],
    )
    doc = dispute.model_dump()
    await db.disputes.insert_one(doc)

    # Auto-refund rule: if the dispute amount is under the admin-configured threshold,
    # resolve immediately with a wallet refund so support only reviews high-value cases.
    settings = await get_settings()
    threshold = float(settings.get("dispute_auto_refund_threshold") or 0.0)
    excluded = set(settings.get("dispute_auto_refund_excluded_reasons") or [])
    if (
        threshold > 0
        and dispute.amount > 0
        and dispute.amount <= threshold
        and dispute.reason not in excluded
    ):
        now = datetime.now(timezone.utc)
        resolution_msg = f"Auto-refunded — orders at or under ${threshold:.2f} are refunded instantly."
        await ledger.refund_credit(
            db,
            user_id=dispute.buyer_id,
            amount=dispute.amount,
            order_id=order["id"],
            description=f"Auto-refund for dispute #{dispute.id[:8]}",
        )
        seller_debit = float(order["seller_earnings"]) if order.get("seller_earnings") is not None else dispute.amount
        await ledger.apply_entry(
            db,
            user_id=dispute.seller_id,
            delta=-seller_debit,
            tx_type="refund",
            description=f"Auto-refund chargeback for dispute #{dispute.id[:8]}",
            related_id=order["id"],
        )
        await db.orders.update_one({"id": order["id"]}, {"$set": {"status": "cancelled"}})
        await db.disputes.update_one(
            {"id": dispute.id},
            {"$set": {
                "status": "refunded",
                "resolution": resolution_msg,
                "admin_notes": f"Auto-refunded (threshold=${threshold:.2f})",
                "resolved_at": now,
            }},
        )
        await notify(
            dispute.buyer_id, "dispute", "Refund issued automatically",
            resolution_msg, "/wallet",
        )
        await notify(
            dispute.seller_id, "dispute", "Dispute auto-refunded",
            f"An order under ${threshold:.2f} was automatically refunded to the buyer.",
            "/profile?tab=disputes",
        )
        fresh = await db.disputes.find_one({"id": dispute.id}, {"_id": 0})
        return Dispute(**fresh)

    await notify(
        order["seller_id"], "dispute",
        f"Buyer opened a dispute on '{order['listing_title']}'",
        payload.description[:120],
        "/profile?tab=disputes",
    )
    return dispute


@router.get("/disputes/mine", response_model=List[Dispute])
async def my_disputes(user: dict = Depends(get_current_user)):
    """Return disputes where the current user is either buyer or seller."""
    db = get_db()
    docs = await db.disputes.find(
        {"$or": [{"buyer_id": user["id"]}, {"seller_id": user["id"]}]}, {"_id": 0}
    ).sort("created_at", -1).to_list(200)
    return [Dispute(**d) for d in docs]


@router.get("/disputes/{dispute_id}", response_model=Dispute)
async def get_dispute(dispute_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    d = await db.disputes.find_one({"id": dispute_id}, {"_id": 0})
    if not d:
        raise HTTPException(404, "Dispute not found")
    if user.get("role") != "admin" and user["id"] not in (d["buyer_id"], d["seller_id"]):
        raise HTTPException(403, "Not allowed")
    return Dispute(**d)


@router.get("/admin/disputes", response_model=List[Dispute])
async def admin_list_disputes(
    status_filter: Optional[str] = Query(None, alias="status"),
    _admin: dict = Depends(require_admin),
):
    db = get_db()
    q: dict = {}
    if status_filter and status_filter in DISPUTE_STATUSES:
        q["status"] = status_filter
    docs = await db.disputes.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    return [Dispute(**d) for d in docs]


@router.post("/admin/disputes/{dispute_id}/resolve", response_model=Dispute)
async def admin_resolve_dispute(
    dispute_id: str, payload: DisputeResolveIn, _admin: dict = Depends(require_admin),
):
    db = get_db()
    d = await db.disputes.find_one({"id": dispute_id}, {"_id": 0})
    if not d:
        raise HTTPException(404, "Dispute not found")
    if d["status"] in ("refunded", "rejected"):
        raise HTTPException(400, f"Dispute already {d['status']}")

    now = datetime.now(timezone.utc)
    updates: dict = {
        "admin_notes": (payload.admin_notes or d.get("admin_notes", "")).strip(),
    }
    if payload.resolution is not None:
        updates["resolution"] = payload.resolution.strip()

    if payload.action == "review":
        updates["status"] = "reviewing"
    elif payload.action == "reject":
        updates["status"] = "rejected"
        updates["resolved_at"] = now
        await notify(
            d["buyer_id"], "dispute",
            "Your dispute was reviewed",
            (updates.get("resolution") or "Our team sided with the seller after review.")[:200],
            "/profile?tab=disputes",
        )
    elif payload.action == "refund":
        updates["status"] = "refunded"
        updates["resolved_at"] = now
        amount = float(d.get("amount", 0))
        if amount > 0:
            await ledger.refund_credit(
                db,
                user_id=d["buyer_id"],
                amount=amount,
                order_id=d["order_id"],
                description=f"Refund for dispute #{dispute_id[:8]}",
            )
            order = await db.orders.find_one({"id": d["order_id"]}, {"_id": 0})
            seller_debit = float(order["seller_earnings"]) if (order and order.get("seller_earnings") is not None) else amount
            await ledger.apply_entry(
                db,
                user_id=d["seller_id"],
                delta=-seller_debit,
                tx_type="refund",
                description=f"Chargeback for dispute #{dispute_id[:8]}",
                related_id=dispute_id,
            )
        await db.orders.update_one({"id": d["order_id"]}, {"$set": {"status": "cancelled"}})
        await notify(
            d["buyer_id"], "dispute",
            "Refund issued",
            (updates.get("resolution") or f"We refunded ${amount:.2f} to your wallet.")[:200],
            "/wallet",
        )
        await notify(
            d["seller_id"], "dispute",
            "Dispute resolved with refund",
            "The buyer was refunded and the sale was cancelled.",
            "/profile?tab=disputes",
        )

    await db.disputes.update_one({"id": dispute_id}, {"$set": updates})
    fresh = await db.disputes.find_one({"id": dispute_id}, {"_id": 0})
    return Dispute(**fresh)


# ---- Dispute chat thread ----------------------------------------------------

@router.get("/disputes/{dispute_id}/messages", response_model=List[DisputeMessage])
async def list_dispute_messages(dispute_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    d = await db.disputes.find_one({"id": dispute_id}, {"_id": 0})
    if not d:
        raise HTTPException(404, "Dispute not found")
    await _dispute_role_for(user, d)
    docs = await db.dispute_messages.find(
        {"dispute_id": dispute_id}, {"_id": 0}
    ).sort("created_at", 1).to_list(500)
    return [DisputeMessage(**m) for m in docs]


@router.post("/disputes/{dispute_id}/messages", response_model=DisputeMessage)
async def post_dispute_message(
    dispute_id: str, payload: DisputeMessageCreate, user: dict = Depends(get_current_user),
):
    db = get_db()
    d = await db.disputes.find_one({"id": dispute_id}, {"_id": 0})
    if not d:
        raise HTTPException(404, "Dispute not found")
    role = await _dispute_role_for(user, d)
    if d.get("status") in ("refunded", "rejected"):
        raise HTTPException(400, "This dispute is closed")
    body = (payload.body or "").strip()
    photos = [p for p in (payload.photos or []) if isinstance(p, str)][:8]
    if not body and not photos:
        raise HTTPException(400, "Message body or at least one photo is required")

    msg = DisputeMessage(
        dispute_id=dispute_id,
        sender_id=user["id"],
        sender_name=user["username"],
        sender_role=role,
        body=body,
        photos=photos,
    )
    await db.dispute_messages.insert_one(msg.model_dump())

    # Notify the other party (or both parties if admin)
    recipients: List[str] = []
    if role == "buyer":
        recipients = [d["seller_id"]]
    elif role == "seller":
        recipients = [d["buyer_id"]]
    elif role == "admin":
        recipients = [d["buyer_id"], d["seller_id"]]
    for rid in recipients:
        try:
            await notify(
                rid, "dispute",
                f"New message on dispute for '{d['listing_title']}'",
                body[:120] if body else "New photo attached",
                "/disputes",
            )
        except Exception as e:
            logger.warning(f"dispute message notify failed: {e}")
    return msg
