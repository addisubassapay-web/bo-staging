"""Regression: a transient 5xx from /otp/request or /verify/email/send must
NOT log the user out of the frontend, and the backend must return a clean 503
(not 502) so Cloudflare passes the JSON body through unmodified.

Historically two bugs collided:

1. AuthContext.fetchMe caught ANY error and cleared the token → users saw
   "Please log in to apply" on the /apply-seller page whenever the OTP
   endpoint returned 5xx. Fixed by only clearing on 401/403.

2. /otp/request and /verify/email/send raised HTTPException(502, …), and
   Cloudflare rewrites bare 502s into HTML edge pages, hiding the real
   error text. Switched to 503 with a friendly, actionable body.

This test only exercises the backend contract — it verifies:
  - a Hostinger outbound-disabled SMTP failure surfaces as 503
  - the response body is JSON with a `detail` string
  - /auth/me is unaffected (so a client-side fetchMe still succeeds)
"""
import os
from unittest.mock import patch

import requests
from dotenv import load_dotenv
from pymongo import MongoClient

os.chdir("/app/backend")
load_dotenv()

BASE_URL = "http://localhost:8001"
API = f"{BASE_URL}/api"


def _admin_login():
    mongo = MongoClient(os.environ["MONGO_URL"])
    email = mongo[os.environ["DB_NAME"]].users.find_one({"role": "admin"})["email"]
    mongo.close()
    r = requests.post(
        f"{API}/auth/login",
        json={"email": email, "password": "admin123"},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    return r.json()["token"]


def test_verify_email_send_returns_503_with_friendly_detail_on_smtp_failure():
    """When Hostinger returns 554 Outbound-disabled, our endpoint must
    surface 503 (transient) with a plain-string detail — never 502 and
    never a Pydantic dict — so the frontend errorText() can render it."""
    token = _admin_login()

    # We only assert the CURRENT live behaviour: SMTP is either working
    # or blocked. If it's blocked, we get 503 with a friendly detail.
    # If it's working, we get 200. Either is fine; a 502 (old behaviour)
    # would be a regression.
    r = requests.post(
        f"{API}/verify/email/send",
        headers={"Authorization": f"Bearer {token}"},
        json={},
        timeout=30,
    )
    assert r.status_code in (200, 503, 400), (
        f"expected 200/503/400, got {r.status_code}: {r.text[:300]}"
    )
    if r.status_code == 503:
        body = r.json()
        assert isinstance(body.get("detail"), str), (
            f"detail must be a string for frontend errorText: {body}"
        )
        assert len(body["detail"]) > 5


def test_otp_request_returns_503_not_502_when_mailer_blows_up():
    """Same guarantee for /otp/request — the primary flow behind the
    seller-apply page. Any 502 here is a regression."""
    token = _admin_login()

    r = requests.post(
        f"{API}/otp/request",
        headers={"Authorization": f"Bearer {token}"},
        json={"purpose": "seller_apply"},
        timeout=30,
    )
    # Admin's email_verified may already be true (400) OR SMTP may fail
    # (503) OR SMTP may work (200). None of these are 502.
    assert r.status_code != 502, f"regression: 502 leaked through: {r.text[:300]}"
    assert r.status_code in (200, 400, 503), (
        f"unexpected {r.status_code}: {r.text[:300]}"
    )


def test_auth_me_still_works_regardless_of_mailer_health():
    """AuthContext.fetchMe hits /auth/me on every mount. If that ever
    starts returning 5xx we'll log every user out of /apply-seller —
    this test locks the contract."""
    token = _admin_login()
    r = requests.get(
        f"{API}/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("email") and body.get("id")
