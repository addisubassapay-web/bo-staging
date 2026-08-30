"""Iteration 73 — Verify the /api/verify/email/send P0 fix.

Previously the endpoint only logged `[MOCK] Sent email verification ...`
and returned the token/verify_link in JSON — no real email was sent.
The fix wires it to services.mailer.send_email (Hostinger SMTP).

Success criteria (per review request):
- Response has NO `dev_mock`, `token`, or `verify_link` keys.
- Response includes ok:true and sent_to_email OR already_verified=true.
- 200 (mailer OK) or 502 (mailer failed) — both prove the mock stub is gone.
- 401 without any auth.
- Admin (already verified) short-circuits with already_verified=true and does
  not hit the mailer.
- /verify/email/send works with cookie only (dual-mode auth).
- /verify/email/confirm still consumes token issued by send and flips
  email_verified=true on the user.
- Backend logs do NOT contain the string "[MOCK] Sent email verification".
"""
import os
import re
import time
import uuid
import subprocess
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
    return f"TEST_iter73_{uuid.uuid4().hex[:10]}@example.com"


def _register():
    s = requests.Session()
    email = _uniq_email()
    r = s.post(f"{API}/auth/register", json={
        "email": email,
        "username": f"iter73_{uuid.uuid4().hex[:8]}",
        "password": "Passw0rd!23",
    }, timeout=30)
    assert r.status_code in (200, 201), r.text
    body = r.json()
    return s, body["token"], body["user"], email


# ---------- P0: response shape has no leaky fields ----------

def test_verify_email_send_response_has_no_mock_fields():
    s, token, user, email = _register()
    r = s.post(f"{API}/verify/email/send", json={"email": email},
               headers={"Authorization": f"Bearer {token}"}, timeout=30)
    # Either 200 (mailer succeeded) or 502 (mailer failed) — both prove
    # the mock stub is gone.
    assert r.status_code in (200, 502), f"unexpected status {r.status_code}: {r.text}"
    if r.status_code == 200:
        body = r.json()
        # These fields must NOT be present anymore
        assert "dev_mock" not in body, f"dev_mock leaked: {body}"
        assert "token" not in body, f"token leaked in response: {body}"
        assert "verify_link" not in body, f"verify_link leaked: {body}"
        assert body.get("ok") is True
        assert body.get("sent_to_email") == email
    else:
        # 502 body should contain a real mailer error string
        assert "verification email" in r.text.lower() or "mail" in r.text.lower(), r.text


# ---------- P0: verify no [MOCK] log line was produced ----------

def test_no_mock_log_line_after_fresh_send():
    """Record log sizes, trigger a send, then confirm no NEW [MOCK] line was written."""
    log_paths = [
        "/var/log/supervisor/backend.err.log",
        "/var/log/supervisor/backend.out.log",
    ]
    sizes_before = {}
    for p in log_paths:
        try:
            sizes_before[p] = os.path.getsize(p)
        except FileNotFoundError:
            sizes_before[p] = 0

    s, token, user, email = _register()
    s.post(f"{API}/verify/email/send", json={"email": email},
           headers={"Authorization": f"Bearer {token}"}, timeout=30)
    time.sleep(1.5)

    new_content = ""
    for p, before in sizes_before.items():
        try:
            with open(p, "rb") as f:
                f.seek(before)
                new_content += f.read().decode(errors="ignore")
        except FileNotFoundError:
            pass
    assert "[MOCK] Sent email verification" not in new_content, (
        f"OLD MOCK path still active — new backend log contains '[MOCK] Sent email verification':\n{new_content[-1000:]}"
    )
    # Positive assertion: the new logger line SHOULD be present
    assert "issued email token" in new_content or "[verification]" in new_content, (
        f"expected '[verification] issued email token' log line not found. tail:\n{new_content[-1000:]}"
    )


# ---------- REGRESSION: 401 without auth ----------

def test_verify_email_send_requires_auth():
    r = requests.post(f"{API}/verify/email/send", json={}, timeout=15)
    assert r.status_code == 401, f"expected 401, got {r.status_code}: {r.text}"


# ---------- REGRESSION: admin (already verified) short-circuits ----------

def test_admin_already_verified_short_circuit():
    s = requests.Session()
    lr = s.post(f"{API}/auth/login",
                json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert lr.status_code == 200, lr.text
    tok = lr.json()["token"]
    r = s.post(f"{API}/verify/email/send", json={},
               headers={"Authorization": f"Bearer {tok}"}, timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("already_verified") is True, f"admin should short-circuit: {body}"
    # No mailer fields should be present
    assert "token" not in body and "verify_link" not in body and "dev_mock" not in body


# ---------- REGRESSION: cookie-only auth still works (iter 72 fix) ----------

def test_verify_email_send_cookie_only():
    s, token, user, email = _register()
    lr = s.post(f"{API}/auth/login",
                json={"email": email, "password": "Passw0rd!23"}, timeout=15)
    assert lr.status_code == 200
    assert "bo_token" in s.cookies
    # Cookie-only request — no Authorization header
    r = s.post(f"{API}/verify/email/send", json={"email": email}, timeout=30)
    assert r.status_code != 401, f"cookie-only auth failed: {r.text}"
    assert r.status_code in (200, 502), f"unexpected {r.status_code}: {r.text}"


# ---------- REGRESSION: confirm consumes the token issued by send ----------

def test_verify_email_confirm_flips_email_verified():
    """We need the raw token — which is no longer returned by send.
    So we fetch it directly from the DB via the backend's mongo. Use a
    small shell helper via python since we have MONGO_URL in backend/.env.
    """
    s, token, user, email = _register()
    r = s.post(f"{API}/verify/email/send", json={"email": email},
               headers={"Authorization": f"Bearer {token}"}, timeout=30)
    if r.status_code == 502:
        pytest.skip(f"mailer unavailable — cannot exercise confirm path: {r.text}")
    assert r.status_code == 200, r.text
    # Fetch token from mongo
    from pymongo import MongoClient
    load_dotenv(Path(__file__).resolve().parents[2] / "backend" / ".env")
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    assert mongo_url and db_name, "MONGO_URL/DB_NAME must be set"
    client = MongoClient(mongo_url)
    doc = client[db_name].verification_tokens.find_one(
        {"user_id": user["id"], "kind": "email", "used": False},
        sort=[("created_at", -1)],
    )
    assert doc, "no verification_tokens row found for the send call"
    raw_token = doc["token"]

    # Confirm
    r = s.post(f"{API}/verify/email/confirm", json={"token": raw_token},
               headers={"Authorization": f"Bearer {token}"}, timeout=15)
    assert r.status_code == 200, f"confirm failed: {r.status_code} {r.text}"

    # /auth/me should show email_verified=True
    me = s.get(f"{API}/auth/me",
               headers={"Authorization": f"Bearer {token}"}, timeout=15).json()
    assert me.get("email_verified") is True, f"email_verified not flipped: {me}"


# ---------- REGRESSION: seller_apply OTP path uses real mailer (from iter71) ----------

def test_seller_apply_otp_still_uses_real_mailer():
    """POST /otp/request purpose=seller_apply must be a real send. Returns
    200 (sent) or 502 (mailer failed) — never 401 for authed user."""
    s, token, user, email = _register()
    r = s.post(f"{API}/otp/request", json={"purpose": "seller_apply"},
               headers={"Authorization": f"Bearer {token}"}, timeout=30)
    assert r.status_code in (200, 502), f"unexpected {r.status_code}: {r.text}"
    if r.status_code == 200:
        inbox = s.get(f"{API}/otp/inbox",
                      headers={"Authorization": f"Bearer {token}"}, timeout=15).json()
        item = next((i for i in inbox["items"] if i["purpose"] == "seller_apply"), None)
        assert item and item["code"].isdigit() and len(item["code"]) == 6
