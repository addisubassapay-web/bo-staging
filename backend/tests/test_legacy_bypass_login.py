"""Legacy bypass login regression tests.

Verifies that:
1. A user flagged `must_change_password=True` can log in with ANY non-empty password.
2. That JWT can hit /auth/me and /auth/change-password but NOT any other protected route (403 password_change_required).
3. After /auth/change-password succeeds, the flag clears and the wrong password no longer works.
4. Empty password still fails.
5. Users NOT flagged still require correct password (bypass is scoped).
"""
import os
import uuid
import requests
import pytest
from motor.motor_asyncio import AsyncIOMotorClient
import asyncio
import bcrypt

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


@pytest.fixture(scope="module")
def legacy_user():
    """Create a test user with must_change_password=True. Cleans up after."""
    email = f"legacy_bypass_test_{uuid.uuid4().hex[:8]}@e2e.com"
    uid = uuid.uuid4().hex
    real_password = "CorrectHorseBatteryStaple!"
    pwd_hash = bcrypt.hashpw(real_password.encode(), bcrypt.gensalt()).decode()

    async def _setup():
        client = AsyncIOMotorClient(MONGO_URL)
        db = client[DB_NAME]
        await db.users.insert_one({
            "id": uid,
            "email": email,
            "username": f"legacy_{uid[:6]}",
            "password_hash": pwd_hash,
            "role": "user",
            "is_active": True,
            "must_change_password": True,
            "referral_code": uid[:8].upper(),
        })
        client.close()

    async def _teardown():
        client = AsyncIOMotorClient(MONGO_URL)
        db = client[DB_NAME]
        await db.users.delete_one({"id": uid})
        await db.auth_audit.delete_many({"user_id": uid})
        client.close()

    asyncio.run(_setup())
    yield {"email": email, "id": uid, "real_password": real_password}
    asyncio.run(_teardown())


@pytest.fixture(scope="module")
def normal_user():
    email = f"normal_test_{uuid.uuid4().hex[:8]}@e2e.com"
    uid = uuid.uuid4().hex
    real_password = "MySecurePwd_2026"
    pwd_hash = bcrypt.hashpw(real_password.encode(), bcrypt.gensalt()).decode()

    async def _setup():
        client = AsyncIOMotorClient(MONGO_URL)
        db = client[DB_NAME]
        await db.users.insert_one({
            "id": uid,
            "email": email,
            "username": f"norm_{uid[:6]}",
            "password_hash": pwd_hash,
            "role": "user",
            "is_active": True,
            "must_change_password": False,
            "referral_code": uid[:8].upper(),
        })
        client.close()

    async def _teardown():
        client = AsyncIOMotorClient(MONGO_URL)
        db = client[DB_NAME]
        await db.users.delete_one({"id": uid})
        client.close()

    asyncio.run(_setup())
    yield {"email": email, "id": uid, "real_password": real_password}
    asyncio.run(_teardown())


def test_legacy_user_can_login_with_any_password(legacy_user):
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": legacy_user["email"], "password": "totally-wrong-nonsense-" + uuid.uuid4().hex},
        timeout=30,
    )
    assert r.status_code == 200, f"legacy bypass failed: {r.status_code} {r.text[:200]}"
    body = r.json()
    assert body.get("token"), "no token issued"
    assert body.get("password_change_required") is True, "flag not returned"


def test_legacy_user_empty_password_rejected(legacy_user):
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": legacy_user["email"], "password": ""},
        timeout=30,
    )
    assert r.status_code == 401


def test_legacy_jwt_gated_to_change_password_only(legacy_user):
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": legacy_user["email"], "password": "anything"},
        timeout=30,
    )
    token = r.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # /auth/me is allowed
    r = requests.get(f"{BASE_URL}/api/auth/me", headers=headers, timeout=30)
    assert r.status_code == 200

    # A random protected endpoint must be blocked
    r = requests.get(f"{BASE_URL}/api/wallet", headers=headers, timeout=30)
    assert r.status_code == 403, f"expected 403 got {r.status_code}: {r.text[:200]}"
    detail = r.json().get("detail")
    if isinstance(detail, dict):
        assert detail.get("password_change_required") is True


def test_legacy_user_change_password_clears_flag_and_stops_bypass(legacy_user):
    # Login with junk password
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": legacy_user["email"], "password": "junk"},
        timeout=30,
    )
    token = r.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    new_pwd = "BrandNewSecret_2026!"
    r = requests.post(
        f"{BASE_URL}/api/auth/change-password",
        headers=headers,
        json={"new_password": new_pwd},
        timeout=30,
    )
    assert r.status_code == 200, r.text[:200]

    # Now junk password must fail (bypass gone)
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": legacy_user["email"], "password": "junk-nope"},
        timeout=30,
    )
    assert r.status_code == 401

    # And new_pwd works
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": legacy_user["email"], "password": new_pwd},
        timeout=30,
    )
    assert r.status_code == 200
    assert r.json().get("password_change_required") is False


def test_normal_user_still_requires_correct_password(normal_user):
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": normal_user["email"], "password": "wrong-password"},
        timeout=30,
    )
    assert r.status_code == 401

    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": normal_user["email"], "password": normal_user["real_password"]},
        timeout=30,
    )
    assert r.status_code == 200
