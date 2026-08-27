"""Iteration 66: Admin auth-audit endpoint + legacy_bypass_enabled toggle."""
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

ADMIN_EMAIL = "admin@mercari.local"
ADMIN_PWD = "admin123"


def _insert_user(uid, email, active=True, must_change=True, pwd="RealPwd_2026!", role="user"):
    async def _do():
        client = AsyncIOMotorClient(MONGO_URL)
        db = client[DB_NAME]
        await db.users.insert_one({
            "id": uid, "email": email, "username": f"u_{uid[:6]}",
            "password_hash": bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode(),
            "role": role, "is_active": active, "must_change_password": must_change,
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


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PWD}, timeout=30)
    assert r.status_code == 200, r.text[:200]
    return r.json()["token"]


@pytest.fixture(scope="module")
def normal_token():
    uid = uuid.uuid4().hex
    email = f"norm_i66_{uid[:8]}@e2e.com"
    pwd = "MyPass_2026!"
    _insert_user(uid, email, active=True, must_change=False, pwd=pwd)
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": email, "password": pwd}, timeout=30)
    assert r.status_code == 200, r.text[:200]
    tok = r.json()["token"]
    yield tok
    _cleanup_user(uid)


@pytest.fixture
def legacy_user():
    uid = uuid.uuid4().hex
    email = f"lb_i66_{uid[:8]}@e2e.com"
    _insert_user(uid, email, active=True, must_change=True)
    yield {"id": uid, "email": email}
    _cleanup_user(uid)


@pytest.fixture(autouse=True, scope="module")
def restore_bypass(admin_token):
    yield
    # Restore state per user request
    requests.put(f"{BASE_URL}/api/admin/settings",
                 headers={"Authorization": f"Bearer {admin_token}"},
                 json={"legacy_bypass_enabled": True}, timeout=30)


# ---------- GET /api/admin/settings ----------
def test_admin_settings_has_legacy_bypass_field(admin_token):
    r = requests.get(f"{BASE_URL}/api/admin/settings",
                     headers={"Authorization": f"Bearer {admin_token}"}, timeout=30)
    assert r.status_code == 200
    # Ensure toggle exists (may not be present until first PUT — accept either)
    body = r.json()
    # Force it on to guarantee presence
    requests.put(f"{BASE_URL}/api/admin/settings",
                 headers={"Authorization": f"Bearer {admin_token}"},
                 json={"legacy_bypass_enabled": True}, timeout=30)
    r2 = requests.get(f"{BASE_URL}/api/admin/settings",
                      headers={"Authorization": f"Bearer {admin_token}"}, timeout=30)
    assert r2.json().get("legacy_bypass_enabled") is True


# ---------- GET /api/admin/auth-audit auth checks ----------
def test_auth_audit_requires_auth():
    r = requests.get(f"{BASE_URL}/api/admin/auth-audit", timeout=30)
    assert r.status_code in (401, 403)


def test_auth_audit_forbidden_for_non_admin(normal_token):
    r = requests.get(f"{BASE_URL}/api/admin/auth-audit",
                     headers={"Authorization": f"Bearer {normal_token}"}, timeout=30)
    assert r.status_code == 403


def test_auth_audit_returns_shape(admin_token):
    r = requests.get(f"{BASE_URL}/api/admin/auth-audit",
                     headers={"Authorization": f"Bearer {admin_token}"}, timeout=30)
    assert r.status_code == 200
    body = r.json()
    assert "items" in body and isinstance(body["items"], list)
    assert "total_bypass" in body and isinstance(body["total_bypass"], int)


def test_auth_audit_filters(admin_token, legacy_user):
    # Trigger a bypass to guarantee at least one row
    requests.post(f"{BASE_URL}/api/auth/login",
                  json={"email": legacy_user["email"], "password": "junk"}, timeout=30)
    r = requests.get(f"{BASE_URL}/api/admin/auth-audit?kind=legacy_bypass_login",
                     headers={"Authorization": f"Bearer {admin_token}"}, timeout=30)
    assert r.status_code == 200
    for it in r.json()["items"]:
        assert it.get("kind") == "legacy_bypass_login"

    # Filter by email substring
    substr = legacy_user["email"].split("@")[0]
    r2 = requests.get(f"{BASE_URL}/api/admin/auth-audit?q={substr}",
                      headers={"Authorization": f"Bearer {admin_token}"}, timeout=30)
    assert r2.status_code == 200
    items = r2.json()["items"]
    assert len(items) >= 1
    assert any(legacy_user["email"] in (it.get("email") or "") for it in items)


# ---------- PUT /api/admin/settings toggle & bypass short-circuit ----------
def test_non_admin_cannot_toggle(normal_token):
    r = requests.put(f"{BASE_URL}/api/admin/settings",
                     headers={"Authorization": f"Bearer {normal_token}"},
                     json={"legacy_bypass_enabled": False}, timeout=30)
    assert r.status_code == 403


def test_disable_bypass_blocks_wrong_password(admin_token, legacy_user):
    # Disable
    r = requests.put(f"{BASE_URL}/api/admin/settings",
                     headers={"Authorization": f"Bearer {admin_token}"},
                     json={"legacy_bypass_enabled": False}, timeout=30)
    assert r.status_code == 200
    assert r.json().get("legacy_bypass_enabled") is False

    # Verify persistence
    g = requests.get(f"{BASE_URL}/api/admin/settings",
                     headers={"Authorization": f"Bearer {admin_token}"}, timeout=30)
    assert g.json().get("legacy_bypass_enabled") is False

    # Wrong password → 401 (bypass gone)
    r2 = requests.post(f"{BASE_URL}/api/auth/login",
                       json={"email": legacy_user["email"], "password": "totally-wrong"},
                       timeout=30)
    assert r2.status_code == 401, f"expected 401 got {r2.status_code}: {r2.text[:200]}"


def test_reenable_bypass_restores_behavior(admin_token, legacy_user):
    # Disable first
    requests.put(f"{BASE_URL}/api/admin/settings",
                 headers={"Authorization": f"Bearer {admin_token}"},
                 json={"legacy_bypass_enabled": False}, timeout=30)
    # Re-enable
    r = requests.put(f"{BASE_URL}/api/admin/settings",
                     headers={"Authorization": f"Bearer {admin_token}"},
                     json={"legacy_bypass_enabled": True}, timeout=30)
    assert r.status_code == 200
    assert r.json().get("legacy_bypass_enabled") is True

    # Wrong password now succeeds with password_change_required=true
    r2 = requests.post(f"{BASE_URL}/api/auth/login",
                       json={"email": legacy_user["email"], "password": "any-wrong-pw"},
                       timeout=30)
    assert r2.status_code == 200, r2.text[:200]
    body = r2.json()
    assert body.get("password_change_required") is True
    assert body.get("token")

    # Audit doc written
    async def _fetch():
        client = AsyncIOMotorClient(MONGO_URL)
        db = client[DB_NAME]
        docs = await db.auth_audit.find(
            {"user_id": legacy_user["id"], "kind": "legacy_bypass_login"}, {"_id": 0}
        ).to_list(10)
        client.close()
        return docs
    docs = asyncio.run(_fetch())
    assert len(docs) >= 1
