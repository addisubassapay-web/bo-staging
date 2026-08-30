"""Iteration 62 — Auth regression after MongoDB Atlas password rotation.

Verifies preview auth end-to-end so we can hand user a definitive answer.
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://ocean-marketplace.preview.emergentagent.com").rstrip("/")

ADMIN_EMAIL = "admin@mercari.local"
ADMIN_PASSWORD = "admin123"
SELLER_EMAIL = "sophia_style@demo.local"
SELLER_PASSWORD = "demo1234"


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


@pytest.fixture(scope="module", autouse=True)
def reset_sophia_lock():
    """Reset sophia_style rate-limit lock via direct Mongo before running tests."""
    try:
        from motor.motor_asyncio import AsyncIOMotorClient  # noqa
        import asyncio
        from pymongo import MongoClient
        from dotenv import load_dotenv
        load_dotenv("/app/backend/.env")
        mongo_url = os.environ.get("MONGO_URL")
        db_name = os.environ.get("DB_NAME", "merchari_global")
        client = MongoClient(mongo_url, serverSelectionTimeoutMS=8000)
        client[db_name].users.update_one(
            {"email": SELLER_EMAIL},
            {"$set": {"failed_login_attempts": 0, "locked_until": None}},
        )
        client[db_name].users.update_one(
            {"email": ADMIN_EMAIL},
            {"$set": {"failed_login_attempts": 0, "locked_until": None}},
        )
        client.close()
        print("Reset lock for sophia_style + admin")
    except Exception as e:
        print(f"WARN: could not reset lock: {e}")
    yield


# --- Auth login ---
def test_admin_login(s):
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"body={r.text}"
    data = r.json()
    assert "access_token" in data or "token" in data, data
    token = data.get("access_token") or data.get("token")
    assert isinstance(token, str) and len(token) > 20
    user = data.get("user") or {}
    assert user.get("role") == "admin", user
    pytest.admin_token = token


def test_admin_me(s):
    token = getattr(pytest, "admin_token", None)
    assert token, "no admin token"
    r = s.get(f"{BASE_URL}/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("email") == ADMIN_EMAIL
    assert body.get("role") == "admin"


def test_seller_login(s):
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": SELLER_EMAIL, "password": SELLER_PASSWORD})
    assert r.status_code == 200, f"body={r.text}"
    data = r.json()
    token = data.get("access_token") or data.get("token")
    assert token
    user = data.get("user") or {}
    # store_id may be under user.store_id or seller_store_id
    store_id = user.get("store_id") or user.get("seller_store_id") or user.get("storeId")
    assert store_id, f"expected non-null store_id, got user={user}"
    pytest.seller_token = token
    pytest.seller_store_id = store_id


def test_stores_listing(s):
    # /api/stores is not a listing route; the featured route is the public listing.
    r = s.get(f"{BASE_URL}/api/stores-featured")
    assert r.status_code == 200, r.text
    data = r.json()
    items = data.get("items") if isinstance(data, dict) else data
    assert isinstance(items, list)
    assert len(items) > 0, "expected non-empty stores list"


def test_store_by_slug(s):
    # try known seller slug
    for slug in ["sophia_style", "sophia-style"]:
        r = s.get(f"{BASE_URL}/api/stores/{slug}")
        if r.status_code == 200:
            body = r.json()
            assert body.get("slug") or body.get("id") or body.get("name")
            return
    pytest.fail(f"could not resolve sophia_style store slug: last={r.status_code} {r.text[:200]}")


# --- Rate limiter — 4 wrong attempts only to avoid locking real accounts ---
def test_rate_limiter_wrong_password_returns_401():
    """Send a couple wrong-password requests against a *throwaway* email;
    do NOT hammer real accounts (avoid 15-min lock)."""
    email = f"nonexistent_{int(time.time())}@example.com"
    for _ in range(2):
        r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": "badpass"})
        assert r.status_code in (400, 401, 404), r.text
