"""Regression: Resend fallback kicks in when primary SMTP fails, and
the seller-application preview endpoint renders the exact template
the applicant will receive.

These lock two features shipped in Sep 2026:
  1. Resend fallback (`services.mailer._send_via_resend`) auto-triggers
     on ANY primary-SMTP failure so seller-approval / OTP / receipt
     emails keep flowing when Hostinger is blocked.
  2. GET /admin/seller-applications/{id}/preview-email returns the
     rendered subject/html/text an applicant will see, with admin notes
     inlined.
"""
import os
import uuid
import asyncio

import requests
from dotenv import load_dotenv
from pymongo import MongoClient

os.chdir("/app/backend")
load_dotenv()

BASE_URL = "http://localhost:8001"
API = f"{BASE_URL}/api"


def _admin_token():
    mongo = MongoClient(os.environ["MONGO_URL"])
    db = mongo[os.environ["DB_NAME"]]
    admin = db.users.find_one({"email": "admin@mercari.local", "role": "admin"})
    db.users.update_one({"_id": admin["_id"]}, {"$set": {"failed_login_attempts": 0, "locked_until": None}})
    email = admin["email"]
    mongo.close()
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": "admin123"}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _pick_seller_app_id():
    mongo = MongoClient(os.environ["MONGO_URL"])
    db = mongo[os.environ["DB_NAME"]]
    doc = db.seller_applications.find_one({})
    mongo.close()
    return doc["id"] if doc else None


def test_preview_email_renders_approved_template():
    app_id = _pick_seller_app_id()
    if not app_id:
        return  # no test data — skip silently
    tok = _admin_token()
    r = requests.get(
        f"{API}/admin/seller-applications/{app_id}/preview-email",
        params={"review_status": "approved"},
        headers={"Authorization": f"Bearer {tok}"},
        timeout=30,
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "approved"
    assert "approved" in d["subject"].lower() or "sell" in d["subject"].lower()
    assert len(d["html"]) > 500
    assert len(d["text"]) > 20


def test_preview_email_renders_rejected_template_with_notes():
    app_id = _pick_seller_app_id()
    if not app_id:
        return
    tok = _admin_token()
    r = requests.get(
        f"{API}/admin/seller-applications/{app_id}/preview-email",
        params={"review_status": "rejected", "admin_notes": "Need clearer ID photo"},
        headers={"Authorization": f"Bearer {tok}"},
        timeout=30,
    )
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "rejected"
    assert "Need clearer ID photo" in d["html"]  # admin notes surfaced


def test_preview_email_rejects_invalid_status():
    app_id = _pick_seller_app_id()
    if not app_id:
        return
    tok = _admin_token()
    r = requests.get(
        f"{API}/admin/seller-applications/{app_id}/preview-email",
        params={"review_status": "hacked"},
        headers={"Authorization": f"Bearer {tok}"},
        timeout=30,
    )
    assert r.status_code == 400


def test_resend_fallback_triggers_when_primary_smtp_fails():
    """Force the primary SMTP to fail by pointing at an invalid host,
    then confirm the mailer routes the message through Resend and
    returns provider=resend."""
    # Point primary SMTP at bogus host — every send will raise
    os.environ["SMTP_HOST"] = "intentionally.invalid.host"
    # Ensure Resend is enabled
    assert os.environ.get("RESEND_API_KEY", "").startswith("re_"), "RESEND_API_KEY missing"
    assert os.environ.get("RESEND_ENABLED", "").lower() in ("1", "true", "yes")

    # Reset circuit breaker so a previous test run's failures don't
    # short-circuit this one.
    from services import mailer
    mailer._SEND_HISTORY.clear()

    async def go():
        return await mailer.send_email(
            to="delivered@resend.dev",  # Resend's test recipient
            subject="BlueOcean pytest fallback probe",
            html="<p>If this reaches Resend the fallback works.</p>",
            text="Fallback probe",
            tags=[f"probe-{uuid.uuid4().hex[:6]}"],
        )

    result = asyncio.run(go())
    assert result["ok"] is True
    assert result["provider"] == "resend"
    assert result["to"] == "delivered@resend.dev"
