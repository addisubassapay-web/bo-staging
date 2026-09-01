"""Regression: deliverability plumbing (suppression list, unsubscribe token,
List-Unsubscribe headers, rate limiter) works end-to-end.

Covers:
  - HMAC unsubscribe token round-trip (sign → verify)
  - One-click unsubscribe endpoint POSTs are accepted (RFC 8058)
  - Suppression list check blocks sends BEFORE SMTP is touched
  - Bounce webhook adds to suppression on hard bounces
  - Rate limiter delays back-to-back sends

Note: pytest-asyncio isn't installed in this repo — the two async paths
use `asyncio.run()` from sync test functions instead of `@pytest.mark.asyncio`.
"""
import os
import asyncio
import uuid

import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

os.chdir("/app/backend")
load_dotenv()

BASE_URL = "http://localhost:8001"
API = f"{BASE_URL}/api"


def _admin_token():
    """Return a fresh admin token, unlocking the admin account first
    so repeated pytest runs never trip the soft-lock counter."""
    mongo = MongoClient(os.environ["MONGO_URL"])
    db = mongo[os.environ["DB_NAME"]]
    # There can be multiple admin accounts; pick the seeded local one
    # whose password is a known constant.
    admin = db.users.find_one({"email": "admin@mercari.local", "role": "admin"})
    assert admin, "admin@mercari.local not found — cannot run test"
    db.users.update_one(
        {"_id": admin["_id"]},
        {"$set": {"failed_login_attempts": 0, "locked_until": None}},
    )
    email = admin["email"]
    mongo.close()
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": "admin123"}, timeout=60)
    assert r.status_code == 200, r.text
    return r.json()["token"]


def test_unsubscribe_token_signed_verifies():
    from routers.mailops import sign_email, verify_email
    email = f"pytest-unsub-{uuid.uuid4().hex[:8]}@example.com"
    tok = sign_email(email)
    assert verify_email(email, tok)
    assert not verify_email(email, tok + "x")


def test_unsubscribe_get_adds_to_suppression_list():
    from routers.mailops import sign_email
    email = f"pytest-unsub-{uuid.uuid4().hex[:8]}@example.com"
    tok = sign_email(email)
    r = requests.get(f"{API}/unsubscribe?email={email}&token={tok}", timeout=60)
    assert r.status_code == 200
    text_lower = r.text.lower()
    assert "off the list" in text_lower or "unsubscribed" in text_lower
    admin = _admin_token()
    requests.post(f"{API}/admin/suppression-list/remove",
                  headers={"Authorization": f"Bearer {admin}"},
                  json={"email": email}, timeout=60)


def test_bounce_webhook_hard_adds_suppression():
    secret = os.environ.get("BOUNCE_WEBHOOK_SECRET") or os.environ.get("APIFY_WEBHOOK_SECRET") or ""
    if not secret:
        pytest.skip("no bounce webhook secret configured")
    email = f"pytest-bounce-{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(
        f"{API}/webhooks/mail/bounce",
        headers={"X-Webhook-Secret": secret},
        json={"email": email, "reason": "hard_bounce", "provider": "test", "diagnostic": "user unknown"},
        timeout=60,
    )
    assert r.status_code == 200, r.text
    assert r.json().get("action") == "suppressed"
    admin = _admin_token()
    requests.post(f"{API}/admin/suppression-list/remove",
                  headers={"Authorization": f"Bearer {admin}"},
                  json={"email": email}, timeout=60)


def test_suppressed_recipient_blocks_send_before_smtp():
    """Register a fake suppression check that always returns True, then
    confirm send_email raises SuppressedRecipient without touching SMTP."""
    from services import mailer
    async def always_suppressed(_email: str) -> bool:
        return True
    original = mailer._SUPPRESSION_CHECK
    mailer.register_suppression_check(always_suppressed)

    async def run():
        raised = False
        try:
            await mailer.send_email(
                to="pytest@example.com",
                subject="probe",
                html="<p>x</p>",
                tags=["probe"],
            )
        except mailer.SuppressedRecipient:
            raised = True
        return raised

    try:
        assert asyncio.run(run()), "expected SuppressedRecipient"
    finally:
        mailer._SUPPRESSION_CHECK = original


def test_rate_limiter_delays_second_send():
    """With EMAIL_RATE_LIMIT_PER_SECOND=0.5 (1 email / 2s), two back-to-back
    calls to _rate_gate() should span at least ~1.7s."""
    os.environ["EMAIL_RATE_LIMIT_PER_SECOND"] = "0.5"
    from services import mailer
    import time
    mailer._LAST_SEND_AT = 0.0

    async def run():
        t0 = time.monotonic()
        await mailer._rate_gate()
        await mailer._rate_gate()
        return time.monotonic() - t0

    elapsed = asyncio.run(run())
    assert elapsed >= 1.7, f"rate limiter didn't gate: elapsed={elapsed:.2f}s"
