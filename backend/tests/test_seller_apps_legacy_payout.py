"""Regression: /admin/seller-applications must not 500 on legacy payout_method.

Historically the SellerApplication response model dropped `stripe_connect` from
its payout_method Literal when the payout options were consolidated. 12 legacy
rows in Mongo still carried `payout_method="stripe_connect"`, which made the
whole list endpoint blow up with a Pydantic ValidationError and 500 — the
admin panel then rendered zero applications.

Fix: (1) widen the response-model Literal to accept the legacy value,
(2) skip-and-log malformed docs instead of failing the whole list.

This test uses direct Mongo writes + the live backend (matches the pattern
of the other tests in /app/backend/tests/).
"""
import os
import uuid
from datetime import datetime, timezone

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
    assert admin, "admin@mercari.local not found — cannot run test"
    db.users.update_one(
        {"_id": admin["_id"]},
        {"$set": {"failed_login_attempts": 0, "locked_until": None}},
    )
    email = admin["email"]
    mongo.close()
    r = requests.post(
        f"{API}/auth/login",
        json={"email": email, "password": "admin123"},
        timeout=60,
    )
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text[:400]}"
    return r.json()["token"]


def test_seller_applications_lists_legacy_payout_methods():
    mongo = MongoClient(os.environ["MONGO_URL"])
    db = mongo[os.environ["DB_NAME"]]

    marker = f"__pytest_seller_app_{uuid.uuid4().hex[:8]}"
    payouts = ["crypto", "bank_transfer", "card", "paypal", "crypto_alt", "stripe_connect"]
    seeded_emails = []
    for pm in payouts:
        email = f"{marker}_{pm}@t.local"
        doc = {
            "id": str(uuid.uuid4()),
            "user_id": f"u_{uuid.uuid4().hex[:8]}",
            "user_email": email,
            "user_username": f"{marker}_{pm}",
            "legal_name": "T",
            "business_name": "",
            "business_type": "individual",
            "tax_id": "",
            "country": "US",
            "address_line1": "",
            "address_line2": "",
            "city": "",
            "state": "",
            "postal_code": "",
            "phone": "",
            "payout_method": pm,
            "id_document_note": "",
            "status": "pending",
            "admin_notes": "",
            "created_at": datetime.now(timezone.utc),
        }
        db.seller_applications.insert_one(doc)
        seeded_emails.append(email)

    # One truly-broken row — must be skipped, not blow up the list
    broken_email = f"{marker}_broken@t.local"
    db.seller_applications.insert_one({
        "id": str(uuid.uuid4()),
        "user_id": "u_broken",
        "user_email": broken_email,
        "user_username": f"{marker}_broken",
        "legal_name": "T",
        "business_type": "individual",
        "payout_method": "totally_not_a_real_method",
        "status": "pending",
        "created_at": datetime.now(timezone.utc),
    })

    try:
        token = _admin_token()
        r = requests.get(
            f"{API}/admin/seller-applications",
            headers={"Authorization": f"Bearer {token}"},
            timeout=60,
        )
        assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text[:400]}"
        emails = {row["user_email"] for row in r.json()}
        for email in seeded_emails:
            assert email in emails, f"missing seeded row: {email}"
        assert broken_email not in emails, "broken row should have been skipped"

        r2 = requests.get(
            f"{API}/admin/seller-applications?status_filter=pending",
            headers={"Authorization": f"Bearer {token}"},
            timeout=60,
        )
        assert r2.status_code == 200
        pending_emails = {row["user_email"] for row in r2.json()}
        for email in seeded_emails:
            assert email in pending_emails
    finally:
        db.seller_applications.delete_many({"user_email": {"$regex": f"^{marker}_"}})
        mongo.close()
