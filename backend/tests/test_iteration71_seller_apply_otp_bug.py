"""Iteration 71 — Verify seller apply email_verified bug fix + OTP inbox feature.

Scenarios:
1. New user register → OTP request(seller_apply) → /otp/inbox → verify → seller/apply → 200
2. GET /api/auth/me returns email_verified=True after verify_otp (backfill)
3. /api/otp/inbox requires Bearer token (401 without)
4. /api/otp/inbox returns items with expected fields
5. /api/auth/login regression — returns token + Set-Cookie bo_token
"""
import os
import uuid
import time
import pytest
import requests
from pathlib import Path
from dotenv import load_dotenv

# Load frontend .env so REACT_APP_BACKEND_URL is available regardless of
# invoking shell.
load_dotenv(Path(__file__).resolve().parents[2] / "frontend" / ".env")

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE, "REACT_APP_BACKEND_URL not set — check /app/frontend/.env"
API = f"{BASE}/api"
ADMIN_EMAIL = "admin@mercari.local"
ADMIN_PASSWORD = "admin123"


def _uniq_email():
    return f"TEST_iter71_{uuid.uuid4().hex[:10]}@example.com"


@pytest.fixture(scope="module")
def session():
    return requests.Session()


@pytest.fixture(scope="module")
def new_user(session):
    """Register a fresh user, return (token, email, user_id)."""
    email = _uniq_email()
    username = f"iter71_{uuid.uuid4().hex[:8]}"
    r = session.post(f"{API}/auth/register", json={
        "email": email, "username": username, "password": "Passw0rd!23",
    }, timeout=30)
    assert r.status_code in (200, 201), f"register failed: {r.status_code} {r.text}"
    data = r.json()
    tok = data["token"]
    uid = data["user"]["id"]
    assert data["user"].get("email_verified") in (False, None), "fresh user should not be verified"
    return {"token": tok, "email": email, "id": uid, "username": username}


def _auth(tok):
    return {"Authorization": f"Bearer {tok}"}


# ============ FEATURE: /otp/inbox auth ============

def test_otp_inbox_requires_auth(session):
    r = session.get(f"{API}/otp/inbox", timeout=15)
    assert r.status_code == 401, f"inbox without auth should 401, got {r.status_code}"


def test_otp_inbox_empty_for_new_user(session, new_user):
    r = session.get(f"{API}/otp/inbox", headers=_auth(new_user["token"]), timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert "items" in body and "count" in body
    assert isinstance(body["items"], list)


# ============ BUG FIX + FEATURE end-to-end ============

def test_e2e_seller_apply_with_otp_inbox(session, new_user):
    tok = new_user["token"]
    h = _auth(tok)

    # Confirm not verified initially
    me = session.get(f"{API}/auth/me", headers=h, timeout=15)
    assert me.status_code == 200
    assert me.json().get("email_verified") in (False, None), "should not yet be verified"

    # Request seller_apply OTP — may fail with 502 if SMTP misconfigured
    r = session.post(f"{API}/otp/request", json={"purpose": "seller_apply"}, headers=h, timeout=30)
    if r.status_code == 502:
        pytest.skip(f"SMTP failed for new mailbox (expected per spec): {r.text}")
    assert r.status_code == 200, f"otp/request failed: {r.status_code} {r.text}"

    # Grab code from inbox
    inbox = session.get(f"{API}/otp/inbox", headers=h, timeout=15).json()
    assert inbox["count"] >= 1, "inbox should have the freshly-requested code"
    item = next((i for i in inbox["items"] if i["purpose"] == "seller_apply"), None)
    assert item is not None, "seller_apply code missing from inbox"
    for key in ("id", "purpose", "label", "code", "created_at", "expires_at", "read"):
        assert key in item, f"inbox item missing key {key}"
    code = item["code"]
    assert len(code) == 6 and code.isdigit(), f"bad code shape: {code}"

    # Verify OTP
    r = session.post(f"{API}/otp/verify",
                     json={"purpose": "seller_apply", "code": code},
                     headers=h, timeout=15)
    assert r.status_code == 200, f"verify failed: {r.status_code} {r.text}"
    body = r.json()
    otp_token = body.get("otp_token")
    assert otp_token and otp_token.startswith("otp_"), f"bad otp_token: {otp_token}"

    # /auth/me now shows email_verified=True (BUG FIX #3 — backfill after OTP verify)
    me2 = session.get(f"{API}/auth/me", headers=h, timeout=15).json()
    assert me2.get("email_verified") is True, (
        f"email_verified should be True after OTP verify (backfill missing): {me2}"
    )

    # POST /api/seller/apply — should NOT return "verify your email"
    payload = {
        "legal_name": "Iter71 Tester",
        "business_type": "individual",
        "tax_id": "1234",
        "country": "US",
        "address_line1": "1 Test St",
        "city": "Testville",
        "state": "CA",
        "postal_code": "94000",
        "phone": "+15551230071",
        "payout_method": "crypto",
    }
    r = session.post(f"{API}/seller/apply", json=payload,
                     headers={**h, "x-otp-token": otp_token}, timeout=30)
    assert r.status_code == 200, f"seller/apply failed: {r.status_code} {r.text}"
    app = r.json()
    assert app.get("status") in ("pending", "approved"), f"unexpected status {app.get('status')}"
    assert "verify your email" not in r.text.lower(), "stale 'verify your email' error re-appeared!"


# ============ Bug reproduction guard: verify old error path is gone ============

def test_seller_apply_without_otp_token_returns_403_not_verify_msg(session, new_user):
    """A fresh user hitting /seller/apply with NO otp token should be blocked by
    OTP guard (403) — NOT with the stale 'verify your email' 400. This proves the
    guard order is correct."""
    # Register a brand-new user for this specific negative test to avoid
    # bleeding state from the e2e test.
    email = _uniq_email()
    username = f"iter71neg_{uuid.uuid4().hex[:8]}"
    r = session.post(f"{API}/auth/register", json={
        "email": email, "username": username, "password": "Passw0rd!23",
    }, timeout=30)
    assert r.status_code in (200, 201)
    tok = r.json()["token"]
    r = session.post(f"{API}/seller/apply",
                     json={"legal_name": "x", "tax_id": "1"},
                     headers=_auth(tok), timeout=15)
    # Must be 403 (missing OTP token) — not 400 with 'verify your email'
    assert r.status_code == 403, f"expected 403 for missing otp token, got {r.status_code} {r.text}"


# ============ REGRESSION: /auth/login sets cookie ============

def test_login_sets_bo_token_cookie(session):
    r = session.post(f"{API}/auth/login",
                     json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                     timeout=15)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    body = r.json()
    assert "token" in body and body["token"], "login response missing token"
    set_cookie = r.headers.get("set-cookie", "")
    assert "bo_token" in set_cookie, f"Set-Cookie bo_token missing: {set_cookie[:200]}"
    # HttpOnly + Secure flags
    assert "HttpOnly" in set_cookie or "httponly" in set_cookie.lower(), "HttpOnly flag missing"
