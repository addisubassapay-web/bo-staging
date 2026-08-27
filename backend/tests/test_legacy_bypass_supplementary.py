"""Supplementary iteration-65 checks for legacy bypass login.

Adds coverage that the existing test_legacy_bypass_login.py doesn't cover:
  1. auth_audit collection receives a `legacy_bypass_login` doc per bypass.
  2. is_active=False users CANNOT bypass (even with must_change_password=True).
  3. Whitespace-only password rejected (401) for legacy users.
  4. Admin login regression (admin@mercari.local / admin123) still works.
  5. Brute-force lockout still triggers for normal (non-bypass) users after 5 failed attempts.
  6. /api/orders (another random protected route) also blocked for legacy JWT.
"""
import os
import uuid
import asyncio
import bcrypt
import requests
import pytest
from motor.motor_asyncio import AsyncIOMotorClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")

MONGO_URL = None
DB_NAME = None
with open("/app/backend/.env") as f:
    for line in f:
        if line.startswith("MONGO_URL="):
            MONGO_URL = line.split("=", 1)[1].strip().strip('"').strip("'")
        if line.startswith("DB_NAME="):
            DB_NAME = line.split("=", 1)[1].strip().strip('"').strip("'")


def _insert_user(uid, email, active=True, must_change=True, pwd="RealPwd_2026!"):
    async def _do():
        client = AsyncIOMotorClient(MONGO_URL)
        db = client[DB_NAME]
        await db.users.insert_one({
            "id": uid,
            "email": email,
            "username": f"u_{uid[:6]}",
            "password_hash": bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode(),
            "role": "user",
            "is_active": active,
            "must_change_password": must_change,
            "referral_code": uid[:8].upper(),
        })
        client.close()
    asyncio.run(_do())


def _cleanup_user(uid):
    async def _do():
        client = AsyncIOMotorClient(MONGO_URL)
        db = client[DB_NAME]
        await db.users.delete_one({"id": uid})
        await db.auth_audit.delete_many({"user_id": uid})
        await db.login_throttle.delete_many({})
        client.close()
    asyncio.run(_do())


def _get_audit_docs(user_id):
    async def _do():
        client = AsyncIOMotorClient(MONGO_URL)
        db = client[DB_NAME]
        docs = await db.auth_audit.find({"user_id": user_id, "kind": "legacy_bypass_login"}, {"_id": 0}).to_list(50)
        client.close()
        return docs
    return asyncio.run(_do())


@pytest.fixture
def legacy_active():
    uid = uuid.uuid4().hex
    email = f"lb_active_{uid[:8]}@e2e.com"
    _insert_user(uid, email, active=True, must_change=True)
    yield {"id": uid, "email": email}
    _cleanup_user(uid)


@pytest.fixture
def legacy_inactive():
    uid = uuid.uuid4().hex
    email = f"lb_inactive_{uid[:8]}@e2e.com"
    _insert_user(uid, email, active=False, must_change=True)
    yield {"id": uid, "email": email}
    _cleanup_user(uid)


@pytest.fixture
def normal_user_for_lockout():
    uid = uuid.uuid4().hex
    email = f"lb_normal_{uid[:8]}@e2e.com"
    _insert_user(uid, email, active=True, must_change=False, pwd="RealPwd_2026!")
    yield {"id": uid, "email": email, "pwd": "RealPwd_2026!"}
    _cleanup_user(uid)


# 1. audit log entry created
def test_audit_log_written_on_bypass(legacy_active):
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": legacy_active["email"], "password": "anything-here"},
                      timeout=30)
    assert r.status_code == 200
    docs = _get_audit_docs(legacy_active["id"])
    assert len(docs) >= 1, "no legacy_bypass_login audit doc found"
    d = docs[0]
    assert d["email"] == legacy_active["email"]
    assert d["user_id"] == legacy_active["id"]
    assert "ip" in d


# 2. is_active=false blocked (with must_change_password=true)
def test_inactive_user_cannot_bypass(legacy_inactive):
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": legacy_inactive["email"], "password": "anything"},
                      timeout=30)
    # Account disabled → 403 (login endpoint checks is_active AFTER bypass path)
    assert r.status_code == 403, f"expected 403 got {r.status_code}: {r.text[:200]}"


# 3. Whitespace-only password rejected
def test_whitespace_password_rejected(legacy_active):
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": legacy_active["email"], "password": "   "},
                      timeout=30)
    assert r.status_code == 401


# 4. Admin regression
def test_admin_login_regression():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": "admin@mercari.local", "password": "admin123"},
                      timeout=30)
    assert r.status_code == 200, r.text[:200]
    body = r.json()
    assert body.get("token")
    # Admin was NOT touched by bulk-reset; must_change_password should be false
    assert body.get("password_change_required") is False


# 5. Brute-force lockout on normal user still triggers
def test_brute_force_lockout_normal_user(normal_user_for_lockout):
    email = normal_user_for_lockout["email"]
    last_status = None
    for _ in range(6):
        r = requests.post(f"{BASE_URL}/api/auth/login",
                          json={"email": email, "password": "wrong-pw"},
                          timeout=30)
        last_status = r.status_code
        if r.status_code == 423:
            break
    assert last_status == 423, f"expected lockout 423 got {last_status}"


# 6. Legacy JWT cannot hit /api/orders either (another random protected route)
def test_legacy_jwt_blocked_on_orders(legacy_active):
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": legacy_active["email"], "password": "anything"},
                      timeout=30)
    token = r.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(f"{BASE_URL}/api/orders", headers=headers, timeout=30)
    assert r.status_code == 403, f"expected 403 got {r.status_code}: {r.text[:200]}"
    detail = r.json().get("detail")
    if isinstance(detail, dict):
        assert detail.get("password_change_required") is True
