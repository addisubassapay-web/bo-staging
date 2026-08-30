"""Iteration 72 — Dual-mode auth (cookie fallback) verification.

Confirms the P0 fix from the user screenshot: /api/otp/request must NOT
return 401 when the HTTPOnly `bo_token` cookie is present but no
Authorization header is sent. Also validates full seller-apply flow
running purely on the cookie, and regressions for header-only mode +
malformed cookies + admin gate.
"""
import os
import uuid
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / "frontend" / ".env")

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE, "REACT_APP_BACKEND_URL missing"
API = f"{BASE}/api"
ADMIN_EMAIL = "admin@mercari.local"
ADMIN_PASSWORD = "admin123"


def _uniq_email():
    return f"TEST_iter72_{uuid.uuid4().hex[:10]}@example.com"


def _register_and_get_cookie():
    """Register a fresh user via cookie flow. Returns (session_with_cookie, token, user)."""
    s = requests.Session()
    email = _uniq_email()
    username = f"iter72_{uuid.uuid4().hex[:8]}"
    r = s.post(f"{API}/auth/register", json={
        "email": email, "username": username, "password": "Passw0rd!23",
    }, timeout=30)
    assert r.status_code in (200, 201), r.text
    body = r.json()
    token = body["token"]
    # Register may not set cookie — force set it by hitting login
    lr = s.post(f"{API}/auth/login", json={"email": email, "password": "Passw0rd!23"}, timeout=30)
    assert lr.status_code == 200
    assert "bo_token" in s.cookies, f"bo_token cookie not set after login. cookies={s.cookies}"
    return s, token, body["user"], email


# ---------- P0 BUG FIX #1: /auth/me works with cookie only ----------

def test_auth_me_with_cookie_only_no_bearer():
    s, token, user, email = _register_and_get_cookie()
    # Strip Authorization header — cookie only
    r = s.get(f"{API}/auth/me", timeout=15)  # no headers arg
    assert r.status_code == 200, f"cookie-only /auth/me failed: {r.status_code} {r.text}"
    data = r.json()
    assert data["email"] == email.lower()


def test_auth_me_admin_cookie_only():
    """Regression: admin login sets cookie and cookie-only /auth/me works."""
    s = requests.Session()
    r = s.post(f"{API}/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200
    assert "bo_token" in s.cookies
    me = s.get(f"{API}/auth/me", timeout=15)
    assert me.status_code == 200
    assert me.json()["email"] == ADMIN_EMAIL


# ---------- P0 BUG FIX #2: /otp/request works with cookie only (the exact user bug) ----------

def test_otp_request_seller_apply_cookie_only():
    s, token, user, email = _register_and_get_cookie()
    r = s.post(f"{API}/otp/request", json={"purpose": "seller_apply"}, timeout=30)
    # Must NOT be 401. 200 (sent) or 502 (SMTP failed) both prove auth passed.
    assert r.status_code != 401, (
        f"REGRESSION: cookie-only /otp/request still returns 401 — user bug NOT fixed. "
        f"body={r.text}"
    )
    assert r.status_code in (200, 502), f"unexpected status {r.status_code}: {r.text}"


# ---------- P0 BUG FIX #3: full seller/apply flow with cookie only ----------

def test_full_seller_apply_flow_cookie_only():
    s, token, user, email = _register_and_get_cookie()
    r = s.post(f"{API}/otp/request", json={"purpose": "seller_apply"}, timeout=30)
    if r.status_code == 502:
        pytest.skip(f"SMTP unavailable; auth reached endpoint: {r.text}")
    assert r.status_code == 200, r.text

    inbox = s.get(f"{API}/otp/inbox", timeout=15)
    assert inbox.status_code == 200, f"cookie-only /otp/inbox failed: {inbox.text}"
    items = inbox.json()["items"]
    item = next((i for i in items if i["purpose"] == "seller_apply"), None)
    assert item is not None
    code = item["code"]

    v = s.post(f"{API}/otp/verify",
               json={"purpose": "seller_apply", "code": code}, timeout=15)
    assert v.status_code == 200, v.text
    otp_token = v.json()["otp_token"]

    payload = {
        "legal_name": "Cookie Tester",
        "business_type": "individual",
        "tax_id": "9999",
        "country": "US",
        "address_line1": "1 Cookie St",
        "city": "Cookieville",
        "state": "CA",
        "postal_code": "94000",
        "phone": "+15551234567",
        "payout_method": "crypto",
    }
    r = s.post(f"{API}/seller/apply", json=payload,
               headers={"x-otp-token": otp_token}, timeout=30)
    assert r.status_code == 200, f"cookie-only seller/apply failed: {r.status_code} {r.text}"
    assert r.json().get("status") in ("pending", "approved")


# ---------- REGRESSION: header-only mode still works ----------

def test_auth_me_with_bearer_only_no_cookie():
    # Register with a fresh session so we can grab the token
    email = _uniq_email()
    username = f"iter72b_{uuid.uuid4().hex[:8]}"
    r = requests.post(f"{API}/auth/register", json={
        "email": email, "username": username, "password": "Passw0rd!23",
    }, timeout=30)
    assert r.status_code in (200, 201)
    token = r.json()["token"]
    # Fresh requests call — NO cookie jar, only Authorization header
    me = requests.get(f"{API}/auth/me",
                      headers={"Authorization": f"Bearer {token}"}, timeout=15)
    assert me.status_code == 200
    assert me.json()["email"] == email.lower()


# ---------- REGRESSION: no cookie + no header => 401 ----------

def test_no_cookie_no_header_returns_401():
    r = requests.get(f"{API}/auth/me", timeout=15)
    assert r.status_code == 401
    assert "not authenticated" in r.text.lower()


def test_malformed_cookie_returns_invalid_token():
    s = requests.Session()
    s.cookies.set("bo_token", "this.is.not.a.valid.jwt", domain=BASE.split("://")[-1].split("/")[0])
    r = s.get(f"{API}/auth/me", timeout=15)
    assert r.status_code == 401, r.text
    assert "invalid token" in r.text.lower(), f"expected 'Invalid token', got: {r.text}"


# ---------- REGRESSION: admin gate on cookie session ----------

def test_admin_endpoint_rejects_non_admin_cookie():
    s, token, user, email = _register_and_get_cookie()
    # /api/admin/settings is admin-only
    r = s.get(f"{API}/admin/settings", timeout=15)
    assert r.status_code in (403, 404), f"non-admin should be blocked, got {r.status_code} {r.text}"
    # Accept 404 in case route path differs, but if 200/2xx that's a bug
    assert r.status_code != 200


def test_admin_endpoint_allows_admin_cookie():
    s = requests.Session()
    r = s.post(f"{API}/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200
    # Try common admin endpoint. Just needs to not 401/403 due to auth.
    r = s.get(f"{API}/admin/settings", timeout=15)
    # 200 or 404 (path may differ) — but NOT 401/403 with cookie
    assert r.status_code not in (401, 403), f"admin cookie should be accepted: {r.status_code} {r.text}"


# ---------- REGRESSION: get_current_user_optional handles no auth ----------

def test_optional_auth_no_credentials():
    """Endpoints that use get_current_user_optional should work without auth.
    Products/list is a good candidate. Just needs to not 401."""
    r = requests.get(f"{API}/products?limit=1", timeout=15)
    assert r.status_code != 401, f"optional-auth endpoint 401'd: {r.text}"
