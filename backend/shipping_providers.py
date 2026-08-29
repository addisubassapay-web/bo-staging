"""
Shipping provider adapter — pluggable interface.

Switch providers via env `SHIPPING_PROVIDER=mock|easypost|shippo`.
Only the mock provider is implemented. EasyPost/Shippo stubs raise NotImplementedError
until the user supplies API keys — see /app/memory/PRD.md.
"""
from __future__ import annotations
import os
import secrets
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional


class ShippingLabel:
    def __init__(self, tracking_number: str, carrier: str, label_url: str,
                 estimated_delivery: str, cost: float, provider: str, dev_mock: bool = False):
        self.tracking_number = tracking_number
        self.carrier = carrier
        self.label_url = label_url
        self.estimated_delivery = estimated_delivery
        self.cost = float(cost)
        self.provider = provider
        self.dev_mock = dev_mock

    def to_dict(self) -> dict:
        return {
            "tracking_number": self.tracking_number,
            "carrier": self.carrier,
            "label_url": self.label_url,
            "estimated_delivery": self.estimated_delivery,
            "cost": self.cost,
            "provider": self.provider,
            "dev_mock": self.dev_mock,
        }


class ShippingProvider:
    name = "base"

    def create_label(self, order: dict) -> ShippingLabel:
        raise NotImplementedError

    def poll_status(self, tracking_number: str) -> Optional[str]:
        """Poll external carrier for status. Returns status string or None."""
        return None


class MockShippingProvider(ShippingProvider):
    name = "mock"
    CARRIERS = ["USPS", "UPS", "FedEx"]

    def create_label(self, order: dict) -> ShippingLabel:
        # secrets.* keeps randomness cryptographically strong even though this
        # is only a mock — flagged by the security lint sweep.
        carrier = secrets.choice(self.CARRIERS)
        tracking = f"MOCK{uuid.uuid4().hex[:12].upper()}"
        label_url = f"/mock-shipping/label/{tracking}.pdf"
        est = (datetime.now(timezone.utc) + timedelta(days=2 + secrets.randbelow(4))).strftime("%A, %b %d")
        cost = float(order.get("shipping_fee", 0))
        return ShippingLabel(
            tracking_number=tracking, carrier=carrier, label_url=label_url,
            estimated_delivery=est, cost=cost, provider=self.name, dev_mock=True,
        )


class EasyPostShippingProvider(ShippingProvider):
    name = "easypost"
    def create_label(self, order: dict) -> ShippingLabel:
        raise NotImplementedError("EasyPost integration not configured. Set SHIPPING_PROVIDER=mock or provide EASYPOST_API_KEY.")


class ShippoShippingProvider(ShippingProvider):
    name = "shippo"
    def create_label(self, order: dict) -> ShippingLabel:
        raise NotImplementedError("Shippo integration not configured. Set SHIPPING_PROVIDER=mock or provide SHIPPO_API_KEY.")


def get_provider() -> ShippingProvider:
    name = os.environ.get("SHIPPING_PROVIDER", "mock").strip().lower()
    if name == "easypost":
        return EasyPostShippingProvider()
    if name == "shippo":
        return ShippoShippingProvider()
    return MockShippingProvider()


# ---- Progressive event timeline ---------------------------------------------
# Each stage has a minimum age (in seconds) that must be reached before it
# activates. In dev mode we use short values so buyers see status changes
# quickly. Adjust env to slow it down.

def _stage_seconds() -> dict:
    """Speeds up the mock timeline for dev demos."""
    fast = os.environ.get("SHIPPING_MOCK_FAST", "true").lower() != "false"
    if fast:
        # ~1 min per stage = full timeline in ~5 mins
        return {"picked_up": 60, "in_transit": 120, "out_for_delivery": 300, "delivered": 480}
    # Real-world approximation: ~2h, 24h, 72h, 96h
    return {"picked_up": 2 * 3600, "in_transit": 24 * 3600,
            "out_for_delivery": 72 * 3600, "delivered": 96 * 3600}


def next_stage_for_age(current_status: Optional[str], age_seconds: float) -> Optional[str]:
    """Return the NEXT stage the order should advance to, given its current status and age.
    Returns None if the order is already at the highest stage possible.
    """
    stages = ["label_created", "picked_up", "in_transit", "out_for_delivery", "delivered"]
    thresholds = _stage_seconds()
    cur_idx = stages.index(current_status) if current_status in stages else 0
    # Compute the max stage the age qualifies for.
    max_idx = 0
    if age_seconds >= thresholds["picked_up"]: max_idx = 1
    if age_seconds >= thresholds["in_transit"]: max_idx = 2
    if age_seconds >= thresholds["out_for_delivery"]: max_idx = 3
    if age_seconds >= thresholds["delivered"]: max_idx = 4
    if max_idx > cur_idx:
        return stages[cur_idx + 1]
    return None


def event_details(stage: str, carrier: str) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    details = {
        "label_created": ("Origin facility", "Shipping label created"),
        "picked_up": (f"{carrier} origin hub", "Package picked up by carrier"),
        "in_transit": ("Regional facility", "In transit"),
        "out_for_delivery": ("Local hub", "Out for delivery"),
        "delivered": ("Delivered", "Delivered to recipient"),
    }
    loc, desc = details.get(stage, ("Facility", stage))
    return {"status": stage, "at": now, "location": loc, "description": desc}
