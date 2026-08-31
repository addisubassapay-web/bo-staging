"""Iteration 76 — P0 fix verification for /auth/forgot-password.

Confirms:
  - Registered lowercase email → 200 + email_log row (provider=hostinger, mocked=False)
  - Unknown email → identical 200 body (no enumeration)
  - Missing email → 400
  - Reset URL uses FRONTEND_ORIGIN and token TTL 60 min, one-time consumption
  - /auth/reset-password consumes token, clears must_change_password, rejects reuse
  - Rate hammering doesn't crash; multiple tokens can coexist
"""
import os
import uuid
import time
from datetime import datetime, timezone, timedelta

import pytest
import httpx
from pymongo import MongoClient

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ.get("DB_NAME", "merchari_global")
FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN", "").rstrip("/")


@pytest.fixture(scope="module")
def db():
    client = MongoClient(MONGO_URL)
    yield client[DB_NAME]
    client.close()


@pytest.fixture(scope="module")
def cx():
    with httpx.Client(timeout=30) as c:
        yield c


@pytest.fixture(scope="module")
def registered_user(cx):
    email = f"fpfix_{uuid.uuid4().hex[:8]}@t.local"
    pw = "pass1234"
    r = cx.post(f"{API}/auth/register", json={
        "email": email, "username": f"fpfix{uuid.uuid4().hex[:6]}", "password": pw
    })
    assert r.status_code == 200, r.text
    return {"email": email, "password": pw, "user_id": r.json()["user"]["id"]}


# ---------- P0: fix verification ----------

def test_forgot_password_registered_returns_200(cx, registered_user):
    r = cx.post(f"{API}/auth/forgot-password", json={"email": registered_user["email"]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body == {"ok": True, "message": "If that email is registered, a reset link is on its way."}


def test_forgot_password_writes_email_log_hostinger(cx, db, registered_user):
    before = datetime.now(timezone.utc) - timedelta(seconds=5)
    r = cx.post(f"{API}/auth/forgot-password", json={"email": registered_user["email"]})
    assert r.status_code == 200
    # Wait briefly for the write
    time.sleep(1.5)
    row = db.email_log.find_one(
        {"kind": "password_reset", "to": registered_user["email"]},
        sort=[("sent_at", -1)],
    )
    assert row is not None, "email_log row missing"
    sent_at = row["sent_at"]
    if sent_at.tzinfo is None:
        sent_at = sent_at.replace(tzinfo=timezone.utc)
    assert sent_at >= before, f"email_log row too old: {sent_at} < {before}"
    assert row["provider"] == "hostinger", f"expected provider=hostinger, got {row['provider']}"
    assert row["url"].startswith(f"{FRONTEND_ORIGIN}/reset-password?token=")
    # Token portion should be 40+ chars
    token_part = row["url"].split("token=", 1)[1]
    assert len(token_part) >= 40, f"token too short: {len(token_part)}"


def test_forgot_password_unknown_email_same_body(cx):
    r = cx.post(f"{API}/auth/forgot-password", json={"email": f"nope_{uuid.uuid4().hex}@nowhere.local"})
    assert r.status_code == 200
    assert r.json() == {"ok": True, "message": "If that email is registered, a reset link is on its way."}


def test_forgot_password_missing_email_400(cx):
    r = cx.post(f"{API}/auth/forgot-password", json={})
    assert r.status_code == 400
    assert "email" in r.text.lower()


def test_password_resets_row_has_60min_ttl_and_not_used(cx, db, registered_user):
    r = cx.post(f"{API}/auth/forgot-password", json={"email": registered_user["email"]})
    assert r.status_code == 200
    time.sleep(1)
    row = db.password_resets.find_one(
        {"email": registered_user["email"], "used_at": None},
        sort=[("created_at", -1)],
    )
    assert row is not None
    created = row["created_at"]
    expires = row["expires_at"]
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    delta = (expires - created).total_seconds()
    assert 3500 <= delta <= 3700, f"TTL should be ~60 min, got {delta}s"


def test_reset_password_consumes_token_and_rejects_reuse(cx, db, registered_user):
    # Fresh token
    r = cx.post(f"{API}/auth/forgot-password", json={"email": registered_user["email"]})
    assert r.status_code == 200
    time.sleep(1)
    row = db.password_resets.find_one(
        {"email": registered_user["email"], "used_at": None},
        sort=[("created_at", -1)],
    )
    assert row is not None
    token = row["token"]

    new_pw = "brandnew1234"
    r1 = cx.post(f"{API}/auth/reset-password", json={"token": token, "new_password": new_pw})
    assert r1.status_code == 200, r1.text

    # used_at should be set + must_change_password cleared
    row2 = db.password_resets.find_one({"token": token})
    assert row2["used_at"] is not None
    user_row = db.users.find_one({"id": registered_user["user_id"]})
    assert user_row.get("must_change_password") in (False, None)

    # Reuse rejected
    r2 = cx.post(f"{API}/auth/reset-password", json={"token": token, "new_password": "another1234"})
    assert r2.status_code == 400

    # Login with new password works
    lg = cx.post(f"{API}/auth/login", json={"email": registered_user["email"], "password": new_pw})
    assert lg.status_code == 200


def test_rapid_forgot_password_does_not_crash(cx, registered_user):
    for _ in range(4):
        r = cx.post(f"{API}/auth/forgot-password", json={"email": registered_user["email"]})
        assert r.status_code == 200


# ---------- Dispatch log line verification (best-effort via log file) ----------

def test_backend_log_shows_dispatched_line(cx, registered_user):
    """After a forgot-password call, /var/log/supervisor/backend.*.log should
    contain the new dispatch log line."""
    r = cx.post(f"{API}/auth/forgot-password", json={"email": registered_user["email"]})
    assert r.status_code == 200
    time.sleep(2)
    import glob
    marker = f"password_reset dispatched to={registered_user['email']}"
    found = False
    for path in glob.glob("/var/log/supervisor/backend.*.log"):
        try:
            with open(path, "r", errors="ignore") as fh:
                # Read last 200KB
                fh.seek(0, 2)
                size = fh.tell()
                fh.seek(max(0, size - 200_000))
                if marker in fh.read():
                    found = True
                    break
        except Exception:
            continue
    assert found, f"Expected marker '{marker}' in backend log"
