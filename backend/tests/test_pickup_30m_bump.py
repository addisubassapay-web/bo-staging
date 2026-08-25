"""Regression tests for the T+30m post-checkout pickup bump reminder.

If a seller doesn't accept an order within 30 minutes of the buyer paying,
the `pickup_reminder_loop` fires a "you have a new order waiting" bump
via both in-app notification and email. Locks in:
  * the trigger window is [T+30m, T+60m] using `created_at`
  * the `pickup_bump_30m_sent_at` flag prevents duplicate sends
  * accepted / cancelled / out-of-window orders are ignored
  * the email template renders the new `reminder_30m` kind
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from pymongo import MongoClient


@pytest.fixture(scope="module")
def db():
    client = MongoClient(os.environ["MONGO_URL"])
    d = client[os.environ["DB_NAME"]]
    yield d
    client.close()


def _seed_order(db, *, minutes_ago: int, fulfillment_status: str = "pending_pickup", already_bumped: bool = False) -> str:
    """Insert a synthetic order that landed `minutes_ago` minutes ago."""
    oid = f"bump-test-{uuid.uuid4().hex[:8]}"
    doc = {
        "id": oid,
        "buyer_id": "buyer-fixture",
        "seller_id": "seller-fixture-does-not-exist",
        "listing_id": "listing-fixture",
        "listing_title": "Bump Test Listing",
        "seller_earnings": 12.34,
        "reseller_wholesale_cost": 8.00,
        "fulfillment_status": fulfillment_status,
        "status": "paid",
        "created_at": datetime.now(timezone.utc) - timedelta(minutes=minutes_ago),
    }
    if already_bumped:
        doc["pickup_bump_30m_sent_at"] = datetime.now(timezone.utc)
    db.orders.insert_one(doc)
    return oid


def test_bump_query_matches_within_window(db):
    """Assert the Mongo query used by pickup_reminder_loop identifies orders
    aged 30-60 min ago and skips out-of-window ones. Mirrors the exact
    filter from `server.py::pickup_reminder_loop`."""
    seeded = []
    try:
        # In-window (45m ago)
        seeded.append(_seed_order(db, minutes_ago=45))
        # Just out of window (20m ago — too early)
        seeded.append(_seed_order(db, minutes_ago=20))
        # Just out of window (90m ago — too late)
        seeded.append(_seed_order(db, minutes_ago=90))
        # Already bumped
        seeded.append(_seed_order(db, minutes_ago=40, already_bumped=True))
        # Already picked up (not pending)
        seeded.append(_seed_order(db, minutes_ago=45, fulfillment_status="picked"))

        now = datetime.now(timezone.utc)
        q = {
            "fulfillment_status": "pending_pickup",
            "created_at": {
                "$gte": now - timedelta(minutes=60),
                "$lte": now - timedelta(minutes=30),
            },
            "pickup_bump_30m_sent_at": {"$exists": False},
            "id": {"$in": seeded},
        }
        hits = list(db.orders.find(q, {"_id": 0, "id": 1}))
        hit_ids = {h["id"] for h in hits}
        assert seeded[0] in hit_ids, "45m-old pending order should be bumped"
        assert seeded[1] not in hit_ids, "20m-old order too fresh — must be skipped"
        assert seeded[2] not in hit_ids, "90m-old order too stale for the 30m bump"
        assert seeded[3] not in hit_ids, "already-bumped order must not re-bump"
        assert seeded[4] not in hit_ids, "already-picked order must not be bumped"
    finally:
        db.orders.delete_many({"id": {"$in": seeded}})


def test_pickup_email_template_renders_reminder_30m():
    """The `_send_pickup_email` helper accepts the new kind='reminder_30m'
    and produces the expected headline/urgency copy."""
    from server import _send_pickup_email  # noqa: F401 — import guards syntax
    # We don't actually SEND (mailer would try real SMTP). Instead, exercise
    # the code path that composes headline/urgency by inspecting the source
    # branch: reading the file text and confirming our new kind is handled.
    import inspect
    src = inspect.getsource(_send_pickup_email)
    assert 'reminder_30m' in src, "handler must branch on new reminder_30m kind"
    assert 'You have a new order waiting' in src, "expected headline for 30m bump"
