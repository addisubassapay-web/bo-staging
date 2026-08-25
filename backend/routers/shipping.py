"""Shipping router — label purchase, tracking lookup, manual stage advance.

Extracted from `server.py`. This isolates the shipping surface from the
core order-CRUD flow so it can evolve (real EasyPost/Shippo integration,
tracking webhooks, printable-label improvements) without churning the
6000+ line monolith. The `shipping_progress_loop` background task stays
in server.py — it needs the app-lifetime `db` handle already there.

Routes registered under `/api/`:
  POST /orders/{order_id}/shipping-label   → create a label (mock provider)
  GET  /orders/{order_id}/label.svg        → render printable label (JWT auth)
  GET  /orders/{order_id}/tracking         → return current shipping timeline
  POST /orders/{order_id}/shipping-advance → seller/admin manually advance
"""
from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from shipping_providers import get_provider as get_shipping_provider, event_details

from .deps import get_db, get_current_user, notify

router = APIRouter()
logger = logging.getLogger(__name__)


JWT_SECRET = os.environ.get("JWT_SECRET", "change-me")
JWT_ALG = "HS256"


class ShippingLabelResponse(BaseModel):
    tracking_number: str
    carrier: str
    label_url: str
    estimated_delivery: str
    cost: float
    dev_mock: bool = True


class AdvanceShippingRequest(BaseModel):
    to_status: Optional[str] = None  # optional target; if omitted advance by one stage


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


@router.post("/orders/{order_id}/shipping-label", response_model=ShippingLabelResponse)
async def create_shipping_label(order_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(404, "Order not found")
    if order["seller_id"] != user["id"] and user.get("role") != "admin":
        raise HTTPException(403, "Only the seller can purchase a label")
    if order.get("tracking_number"):
        return ShippingLabelResponse(
            tracking_number=order["tracking_number"],
            carrier=order.get("carrier", "USPS"),
            label_url=f"/api/orders/{order_id}/label.svg",
            estimated_delivery=order.get("estimated_delivery", "2-5 business days"),
            cost=float(order.get("shipping_fee", 0)),
            dev_mock=order.get("shipping_provider", "mock") == "mock",
        )
    provider = get_shipping_provider()
    label = provider.create_label(order)
    initial_event = event_details("label_created", label.carrier)
    await db.orders.update_one(
        {"id": order_id},
        {"$set": {
            "tracking_number": label.tracking_number,
            "carrier": label.carrier,
            "label_url": f"/api/orders/{order_id}/label.svg",
            "shipping_status": "label_created",
            "shipping_provider": label.provider,
            "estimated_delivery": label.estimated_delivery,
            "shipping_events": [initial_event],
            "label_created_at": _now_utc(),
        }},
    )
    await notify(
        order["buyer_id"], "order", "Shipping label created",
        f"Tracking: {label.tracking_number} via {label.carrier}",
        f"/order/{order_id}",
    )
    logger.info(
        f"[shipping:{label.provider}] Label created for order {order_id}: "
        f"{label.carrier} {label.tracking_number}"
    )
    return ShippingLabelResponse(
        tracking_number=label.tracking_number,
        carrier=label.carrier,
        label_url=f"/api/orders/{order_id}/label.svg",
        estimated_delivery=label.estimated_delivery,
        cost=label.cost,
        dev_mock=label.dev_mock,
    )


@router.get("/orders/{order_id}/label.svg")
async def render_shipping_label(order_id: str, request: Request):
    """Render a printable shipping label as SVG with a QR-style block and barcode."""
    # Auth via header OR ?auth= query param (so <img>/<iframe> can render it)
    token = None
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1]
    token = token or request.query_params.get("auth")
    if not token:
        raise HTTPException(401, "Missing auth token")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        uid = payload.get("sub") or payload.get("user_id")
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid token")
    db = get_db()
    user = await db.users.find_one({"id": uid}, {"_id": 0})
    if not user:
        raise HTTPException(401, "Invalid user")

    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order or not order.get("tracking_number"):
        raise HTTPException(404, "Label not generated for this order")
    if order["seller_id"] != user["id"] and user.get("role") != "admin":
        raise HTTPException(403, "Only the seller/admin can view this label")

    return Response(content=_render_label_svg(order, order_id), media_type="image/svg+xml")


def _render_label_svg(order: dict, order_id: str) -> str:
    """Render a printable 4x6-style shipping label as inline SVG."""
    tracking = order.get("tracking_number", "")
    carrier = order.get("carrier", "USPS")
    est = order.get("estimated_delivery", "")
    addr = order.get("address", {}) or {}
    seller_name = order.get("seller_name", "")
    buyer_name = addr.get("full_name") or order.get("buyer_name", "")
    street = addr.get("street", "")
    csz = " ".join(
        str(v) for v in [addr.get("city", ""), addr.get("state", ""), addr.get("zip", "")] if v
    ).strip()
    country = addr.get("country", "")

    # Deterministic QR-like grid from tracking number
    h = hashlib.sha256(tracking.encode()).digest()
    grid_bits = []
    for byte in h:
        for i in range(8):
            grid_bits.append((byte >> i) & 1)
    qr_cells = []
    cell_size = 10
    qr_origin_x, qr_origin_y = 470, 210
    for row in range(16):
        for col in range(16):
            if grid_bits[row * 16 + col]:
                x = qr_origin_x + col * cell_size
                y = qr_origin_y + row * cell_size
                qr_cells.append(f'<rect x="{x}" y="{y}" width="{cell_size}" height="{cell_size}" fill="black" />')

    def finder(cx, cy):
        return (
            f'<rect x="{cx}" y="{cy}" width="70" height="70" fill="black" />'
            f'<rect x="{cx+10}" y="{cy+10}" width="50" height="50" fill="white" />'
            f'<rect x="{cx+20}" y="{cy+20}" width="30" height="30" fill="black" />'
        )
    corners = finder(qr_origin_x - 10, qr_origin_y - 10) + finder(qr_origin_x + 100, qr_origin_y - 10) + finder(qr_origin_x - 10, qr_origin_y + 100)

    bars = []
    x = 40
    for byte in h[:24]:
        widths = [2, 3, 4, 5]
        w = widths[byte % 4]
        gap = 1 + (byte >> 4) % 3
        bars.append(f'<rect x="{x}" y="480" width="{w}" height="90" fill="black" />')
        x += w + gap

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 700" width="640" height="700" style="font-family: 'Helvetica Neue', Arial, sans-serif;">
  <rect width="640" height="700" fill="white" stroke="#111" stroke-width="3"/>
  <!-- Header band -->
  <rect x="0" y="0" width="640" height="60" fill="#FF211F"/>
  <text x="20" y="40" fill="white" font-size="26" font-weight="800">MERCHARI-GLOBAL — SHIPPING LABEL</text>
  <text x="580" y="40" fill="white" font-size="14" text-anchor="end">MOCK / DEV</text>

  <!-- Carrier & tracking -->
  <text x="20" y="105" fill="#666" font-size="11" letter-spacing="2">CARRIER</text>
  <text x="20" y="135" fill="#111" font-size="28" font-weight="700">{carrier}</text>
  <text x="20" y="175" fill="#666" font-size="11" letter-spacing="2">TRACKING</text>
  <text x="20" y="200" fill="#111" font-size="18" font-family="ui-monospace, Menlo, monospace" font-weight="600">{tracking}</text>

  <!-- Ship-to block -->
  <line x1="20" y1="220" x2="440" y2="220" stroke="#111" stroke-width="1"/>
  <text x="20" y="245" fill="#666" font-size="11" letter-spacing="2">SHIP TO</text>
  <text x="20" y="275" fill="#111" font-size="22" font-weight="700">{buyer_name}</text>
  <text x="20" y="305" fill="#111" font-size="16">{street}</text>
  <text x="20" y="330" fill="#111" font-size="16">{csz}</text>
  <text x="20" y="355" fill="#111" font-size="16">{country}</text>

  <!-- From block -->
  <text x="20" y="395" fill="#666" font-size="11" letter-spacing="2">FROM</text>
  <text x="20" y="415" fill="#111" font-size="14">{seller_name}</text>
  <text x="20" y="435" fill="#666" font-size="12">Est. delivery: {est}</text>

  <!-- Barcode -->
  {''.join(bars)}
  <text x="40" y="595" fill="#111" font-size="12" font-family="ui-monospace, Menlo, monospace">{tracking}</text>

  <!-- QR block -->
  {corners}
  {''.join(qr_cells)}
  <text x="470" y="395" fill="#666" font-size="11" letter-spacing="2">SCAN AT DROP-OFF</text>

  <!-- Footer -->
  <rect x="0" y="670" width="640" height="30" fill="#FFF0E6"/>
  <text x="20" y="690" fill="#FF211F" font-size="12" font-weight="600">MERCHARI-GLOBAL — Powered by pluggable shipping adapter</text>
  <text x="620" y="690" fill="#FF211F" font-size="11" text-anchor="end" font-family="ui-monospace, Menlo, monospace">#{order_id[:8]}</text>
</svg>'''
    return svg


@router.get("/orders/{order_id}/tracking")
async def get_tracking(order_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(404, "Order not found")
    if user["id"] not in (order.get("buyer_id"), order.get("seller_id")) and user.get("role") != "admin":
        raise HTTPException(403, "Not allowed")
    if not order.get("tracking_number"):
        return {"has_label": False}
    events = order.get("shipping_events") or []
    if not events:
        # Backfill for legacy orders — synthesize a single label_created event.
        created = order.get("label_created_at") or order.get("created_at") or _now_utc()
        if isinstance(created, str):
            try:
                created = datetime.fromisoformat(created.replace("Z", "+00:00"))
            except Exception:
                created = _now_utc()
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        events = [{
            "status": "label_created",
            "at": created.isoformat(),
            "location": "Origin facility",
            "description": "Shipping label created",
        }]
        await db.orders.update_one(
            {"id": order_id},
            {"$set": {"shipping_events": events, "label_created_at": created}},
        )
    return {
        "has_label": True,
        "tracking_number": order["tracking_number"],
        "carrier": order.get("carrier"),
        "label_url": order.get("label_url"),
        "estimated_delivery": order.get("estimated_delivery"),
        "current_status": order.get("shipping_status", "label_created"),
        "provider": order.get("shipping_provider", "mock"),
        "events": events,
        "dev_mock": order.get("shipping_provider", "mock") == "mock",
    }


@router.post("/orders/{order_id}/shipping-advance")
async def advance_shipping(order_id: str, payload: AdvanceShippingRequest, user: dict = Depends(get_current_user)):
    """Seller/admin manually advances shipping status by one stage (or to a target status)."""
    db = get_db()
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(404, "Order not found")
    if order["seller_id"] != user["id"] and user.get("role") != "admin":
        raise HTTPException(403, "Only the seller or admin can advance shipping")
    if not order.get("tracking_number"):
        raise HTTPException(400, "No shipping label on this order")
    stages = ["label_created", "picked_up", "in_transit", "out_for_delivery", "delivered"]
    current = order.get("shipping_status", "label_created")
    if current == "delivered":
        raise HTTPException(400, "Order already delivered")
    if payload.to_status:
        if payload.to_status not in stages:
            raise HTTPException(400, "Invalid target status")
        if stages.index(payload.to_status) <= stages.index(current):
            raise HTTPException(400, "Target status must be beyond current")
        next_status = payload.to_status
    else:
        next_status = stages[stages.index(current) + 1]
    ev = event_details(next_status, order.get("carrier", "Carrier"))
    await db.orders.update_one(
        {"id": order_id},
        {"$set": {"shipping_status": next_status}, "$push": {"shipping_events": ev}},
    )
    await notify(
        order["buyer_id"], "order",
        f"Shipping update: {next_status.replace('_',' ').title()}",
        ev["description"], f"/order/{order_id}",
    )
    return {"ok": True, "current_status": next_status, "event": ev}
