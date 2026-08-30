"""Iteration 51 — Verify Email OTP rate-limit fix.

Previous iteration (50) found request_otp deleted prior unused OTPs BEFORE
counting → 5/hour limit never tripped. Fix: count first, then mark superseded
via update_many({used_at: now, superseded: True}) instead of delete_many.
This module verifies the fix end-to-end against the live backend.
"""
import hashlib
import json
import os
import time
import uuid
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://ocean-marketplace.preview.emergentagent.com").rstrip("/")


def _load_env():
    p = "/app/backend/.env"
    if os.path.exists(p):
        for line in open(p):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k, v.strip().strip('"').strip("'"))


_load_env()
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

SOPHIA = {"email": "sophia_style@demo.local", "password": "demo1234"}


# ------------ fixtures ------------
@pytest.fixture(scope="module")
def db():
    client = MongoClient(MONGO_URL)
    yield client[DB_NAME]
    client.close()


@pytest.fixture(scope="module")
def sophia_ctx(db):
    """Login sophia; wipe her withdrawal + seller_apply OTP buckets so quota is clean."""
    r = requests.post(f"{BASE_URL}/api/auth/login", json=SOPHIA, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    data = r.json()
    uid = data["user"]["id"]
    hdr = {"Authorization": f"Bearer {data['token']}"}
    # Clean baseline quota for tested purposes
    db.email_otps.delete_many({"user_id": uid, "purpose": {"$in": ["withdrawal", "seller_apply"]}})
    yield {"uid": uid, "hdr": hdr, "email": SOPHIA["email"]}
    # Cleanup afterwards
    db.email_otps.delete_many({"user_id": uid, "purpose": {"$in": ["withdrawal", "seller_apply"]}})


@pytest.fixture(scope="module")
def fresh_user(db):
    """Register a fresh user with unique email so their quota bucket is empty."""
    ts = int(time.time())
    email = f"e2e_otp_{ts}_{uuid.uuid4().hex[:6]}@example.com"
    payload = {"email": email, "password": "pass1234", "username": f"e2eotp{ts}"}
    r = requests.post(f"{BASE_URL}/api/auth/register", json=payload, timeout=30)
    assert r.status_code in (200, 201), f"register failed: {r.status_code} {r.text}"
    data = r.json()
    tok = data.get("token") or data.get("access_token")
    uid = data.get("user", {}).get("id") or data.get("id")
    assert tok and uid, f"unexpected register response: {data}"
    hdr = {"Authorization": f"Bearer {tok}"}
    yield {"uid": uid, "hdr": hdr, "email": email}
    db.email_otps.delete_many({"user_id": uid})


# ------------ 1. Rate limit ENFORCED on withdrawal ------------
def test_rate_limit_withdrawal_5_then_429(sophia_ctx, db):
    uid = sophia_ctx["uid"]
    hdr = sophia_ctx["hdr"]
    # baseline clean
    db.email_otps.delete_many({"user_id": uid, "purpose": "withdrawal"})

    statuses = []
    bodies = []
    for i in range(6):
        r = requests.post(
            f"{BASE_URL}/api/otp/request", json={"purpose": "withdrawal"}, headers=hdr, timeout=30
        )
        statuses.append(r.status_code)
        bodies.append(r.text)

    assert statuses[:5] == [200, 200, 200, 200, 200], f"first 5 must succeed, got {statuses} bodies={bodies}"
    assert statuses[5] == 400, f"6th must be 400, got {statuses[5]} body={bodies[5]}"

    # Message check
    detail = json.loads(bodies[5]).get("detail", "")
    assert "Too many OTP requests" in detail, f"unexpected detail: {detail}"
    assert "hour" in detail.lower(), f"unexpected detail: {detail}"

    # Verify response payload of first success
    ok = json.loads(bodies[0])
    assert ok["ok"] is True
    assert ok["purpose"] == "withdrawal"
    assert ok["expires_in_seconds"] == 600
    assert ok["sent_to_email"] == sophia_ctx["email"]


# ------------ 2. DB: exactly 5 rows, only ONE non-superseded ------------
def test_db_state_after_5_requests(sophia_ctx, db):
    uid = sophia_ctx["uid"]
    total = db.email_otps.count_documents({"user_id": uid, "purpose": "withdrawal"})
    assert total == 5, f"Expected exactly 5 rows in email_otps after 5 successful + 1 rejected request. got {total}"

    active = list(db.email_otps.find({
        "user_id": uid, "purpose": "withdrawal",
        "used_at": None,
    }))
    assert len(active) == 1, f"Expected exactly 1 active (used_at=None) row after supersede fix, got {len(active)}"

    superseded = list(db.email_otps.find({
        "user_id": uid, "purpose": "withdrawal", "superseded": True,
    }))
    assert len(superseded) == 4, f"Expected 4 superseded rows, got {len(superseded)}"

    # Latest active row is the newest
    latest = db.email_otps.find_one(
        {"user_id": uid, "purpose": "withdrawal"},
        sort=[("created_at", -1)],
    )
    assert latest is not None
    assert latest["used_at"] is None, "The newest row should be the active/non-superseded one"
    assert latest.get("superseded") is not True


# ------------ 3. verify_otp path: fresh user + fresh purpose ------------
def _brute_code(target_hash: str) -> str:
    for i in range(1_000_000):
        c = f"{i:06d}"
        if hashlib.sha256(c.encode()).hexdigest() == target_hash:
            return c
    raise RuntimeError("brute force failed")


def test_verify_otp_works_after_supersede_fix(fresh_user, db):
    """Ensure the update_many superseded marker doesn't break verify_otp for the
    active row: request once with seller_apply → verify should succeed."""
    uid = fresh_user["uid"]
    hdr = fresh_user["hdr"]

    r = requests.post(
        f"{BASE_URL}/api/otp/request", json={"purpose": "seller_apply"}, headers=hdr, timeout=30
    )
    assert r.status_code == 200, r.text

    # Grab the active (non-superseded) row
    otp = db.email_otps.find_one({
        "user_id": uid, "purpose": "seller_apply", "used_at": None,
    })
    assert otp is not None, "No active seller_apply OTP found — supersede marker may be wrong"
    assert otp.get("superseded") is not True

    code = _brute_code(otp["code_hash"])
    vr = requests.post(
        f"{BASE_URL}/api/otp/verify",
        json={"purpose": "seller_apply", "code": code},
        headers=hdr, timeout=30,
    )
    assert vr.status_code == 200, vr.text
    data = vr.json()
    assert data["ok"] is True
    assert data["otp_token"].startswith("otp_")
    assert data["purpose"] == "seller_apply"
    assert data["expires_in_seconds"] == 300


# ------------ 4. Independent quotas per purpose ------------
def test_independent_quota_per_purpose(fresh_user, db):
    """After 5x withdrawal (full quota), 1x seller_apply must still succeed."""
    uid = fresh_user["uid"]
    hdr = fresh_user["hdr"]

    # Baseline: clear withdrawal for the fresh user
    db.email_otps.delete_many({"user_id": uid, "purpose": "withdrawal"})

    for i in range(5):
        r = requests.post(
            f"{BASE_URL}/api/otp/request", json={"purpose": "withdrawal"}, headers=hdr, timeout=30
        )
        assert r.status_code == 200, f"req {i} failed: {r.status_code} {r.text}"

    # 6th withdrawal must be blocked
    blocked = requests.post(
        f"{BASE_URL}/api/otp/request", json={"purpose": "withdrawal"}, headers=hdr, timeout=30
    )
    assert blocked.status_code == 400, blocked.text

    # But seller_apply on the SAME user: seller_apply may already have 1 from previous test.
    # Count first — if under 5, one more request should still succeed.
    seller_recent = db.email_otps.count_documents({"user_id": uid, "purpose": "seller_apply"})
    if seller_recent < 5:
        sr = requests.post(
            f"{BASE_URL}/api/otp/request", json={"purpose": "seller_apply"}, headers=hdr, timeout=30
        )
        assert sr.status_code == 200, f"seller_apply on user with maxed withdrawal quota must succeed: {sr.text}"


# ------------ 5. Invalid purpose ------------
def test_invalid_purpose_returns_400(fresh_user):
    hdr = fresh_user["hdr"]
    r = requests.post(
        f"{BASE_URL}/api/otp/request", json={"purpose": "garbage"}, headers=hdr, timeout=30
    )
    assert r.status_code == 400, r.text
    detail = r.json().get("detail", "")
    assert "Unknown purpose" in detail or "purpose" in detail.lower()


# ------------ 6. Auth guard on /api/otp/request ------------
def test_otp_request_requires_auth():
    r = requests.post(f"{BASE_URL}/api/otp/request", json={"purpose": "withdrawal"}, timeout=30)
    assert r.status_code in (401, 403), f"expected 401/403 without auth, got {r.status_code} {r.text}"
