"""Phase 17: Seller Trust-Score Auto-Approval tests."""
import os
import time
import uuid
import pytest
import requests
from datetime import datetime, timezone, timedelta
from pymongo import MongoClient

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

_client = MongoClient(MONGO_URL)
_db = _client[DB_NAME]


def _run(x):
    # Backwards-compat shim (previously async). No-op passthrough for sync results.
    return x


def _admin_token():
    r = requests.post(f"{API}/auth/login", json={"email": "admin@merchari-global.local", "password": "admin123"})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _register(email, password="pass1234", username=None):
    username = username or f"u{uuid.uuid4().hex[:8]}"
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": password, "username": username})
    assert r.status_code in (200, 201), r.text
    data = r.json()
    return data["token"], data.get("user", {})


def _auth(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def db():
    yield _db


def _run(coro):
    return coro


# ---------- Trust score computation ----------
class TestTrustScore:
    def test_admin_trust_score_baseline(self):
        tok = _admin_token()
        r = requests.get(f"{API}/seller/trust-score", headers=_auth(tok))
        assert r.status_code == 200, r.text
        data = r.json()
        # keys
        for k in ["score", "max", "tier", "auto_approve_threshold", "auto_approve_eligible", "signals"]:
            assert k in data
        assert data["auto_approve_threshold"] == 80
        assert data["max"] == 100
        assert len(data["signals"]) == 6
        keys = {s["key"] for s in data["signals"]}
        assert keys == {"email_verified", "phone_verified", "account_age", "no_open_disputes", "has_referrals", "profile_complete"}
        # Per spec: admin (email verified, no phone/refs/bio, no disputes) → score=40, tier=new
        assert data["score"] == 40, data
        assert data["tier"] == "new"
        assert data["auto_approve_eligible"] is False

    def test_trust_score_requires_auth(self):
        r = requests.get(f"{API}/seller/trust-score")
        assert r.status_code in (401, 403)


# ---------- Fast-track auto-approval ----------
class TestFastTrackApproval:
    def test_high_trust_user_auto_approved(self, db):
        # register a fresh user
        email = f"TEST_ft_{uuid.uuid4().hex[:8]}@example.com"
        tok, user = _register(email)
        uid = user["id"]

        # Mutate user doc: fully verified, old account, profile complete
        _run(db.users.update_one(
            {"id": uid},
            {"$set": {
                "email_verified": True,
                "phone_verified": True,
                "phone": "+15550001234",
                "bio": "Vintage collector selling curated finds.",
                "avatar": "https://example.com/a.jpg",
                "created_at": datetime.now(timezone.utc) - timedelta(days=30),
            }},
        ))

        # trust score should be >=80
        r = requests.get(f"{API}/seller/trust-score", headers=_auth(tok))
        assert r.status_code == 200
        ts = r.json()
        print("HIGH TRUST ts:", ts)
        assert ts["score"] >= 80, ts
        assert ts["auto_approve_eligible"] is True
        assert ts["tier"] == "elite"

        # Apply
        form = {
            "legal_name": "Test Legal",
            "business_name": "",
            "business_type": "individual",
            "tax_id": "123-45-6789",
            "country": "US",
            "address_line1": "1 Test St",
            "address_line2": "",
            "city": "Testville",
            "state": "CA",
            "postal_code": "94000",
            "phone": "+15550001234",
            "payout_method": "stripe_connect",
            "id_document_note": "",
            "id_document_file_id": None,
        }
        r = requests.post(f"{API}/seller/apply", json=form, headers=_auth(tok))
        assert r.status_code == 200, r.text
        app = r.json()
        assert app["status"] == "approved", app
        assert app["admin_notes"].startswith("Auto-approved via Trust Score"), app["admin_notes"]
        assert app["reviewed_at"] is not None
        assert app["reviewed_by"] == "system:trust_score"

        # user doc updated
        u = _run(db.users.find_one({"id": uid}, {"_id": 0}))
        assert u["seller_status"] == "approved"

        # notification created
        notifs = list(db.notifications.find({"user_id": uid}).limit(20))
        titles = [n.get("title") for n in notifs]
        assert any("approved to sell" in (t or "").lower() for t in titles), titles


# ---------- Manual queue path ----------
class TestManualQueue:
    def test_low_trust_user_pending(self, db):
        email = f"TEST_low_{uuid.uuid4().hex[:8]}@example.com"
        tok, user = _register(email)
        uid = user["id"]
        # Only verify email + phone (fresh account, no bio/avatar, no referrals)
        _run(db.users.update_one(
            {"id": uid},
            {"$set": {"email_verified": True, "phone_verified": True, "phone": "+15550005555"}},
        ))
        r = requests.get(f"{API}/seller/trust-score", headers=_auth(tok))
        ts = r.json()
        assert ts["score"] < 80, ts
        assert ts["auto_approve_eligible"] is False

        form = {
            "legal_name": "Low Trust",
            "business_type": "individual",
            "country": "US",
            "address_line1": "1 Low St",
            "city": "Lowville",
            "state": "CA",
            "postal_code": "94001",
            "phone": "+15550005555",
            "payout_method": "stripe_connect",
        }
        r = requests.post(f"{API}/seller/apply", json=form, headers=_auth(tok))
        assert r.status_code == 200, r.text
        app = r.json()
        assert app["status"] == "pending"
        assert app["reviewed_at"] is None

        u = _run(db.users.find_one({"id": uid}, {"_id": 0}))
        assert u["seller_status"] == "pending"

        notifs = list(db.notifications.find({"user_id": uid}).limit(20))
        titles = [n.get("title") for n in notifs]
        assert any("submitted" in (t or "").lower() for t in titles), titles

        # Admin can approve via existing endpoint
        admin_tok = _admin_token()
        r = requests.put(
            f"{API}/admin/seller-applications/{app['id']}",
            json={"status": "approved", "admin_notes": "manual ok"},
            headers=_auth(admin_tok),
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "approved"


# ---------- Dispute vetoes fast-track ----------
class TestDisputeVeto:
    def test_open_dispute_blocks_auto_approve(self, db):
        email = f"TEST_disp_{uuid.uuid4().hex[:8]}@example.com"
        tok, user = _register(email)
        uid = user["id"]
        _run(db.users.update_one(
            {"id": uid},
            {"$set": {
                "email_verified": True, "phone_verified": True,
                "phone": "+15550009999",
                "bio": "bio", "avatar": "https://x/y.jpg",
                "created_at": datetime.now(timezone.utc) - timedelta(days=30),
            }},
        ))
        # Insert an open dispute
        _run(db.disputes.insert_one({
            "id": f"disp_{uuid.uuid4().hex[:8]}",
            "buyer_id": uid,
            "status": "open",
            "created_at": datetime.now(timezone.utc),
        }))
        r = requests.get(f"{API}/seller/trust-score", headers=_auth(tok))
        ts = r.json()
        sig = next(s for s in ts["signals"] if s["key"] == "no_open_disputes")
        assert sig["earned"] == 0
        assert ts["auto_approve_eligible"] is False


# ---------- Regression: verification gates ----------
class TestApplyGates:
    def test_apply_requires_email_verification(self):
        email = f"TEST_gate_{uuid.uuid4().hex[:8]}@example.com"
        tok, _ = _register(email)
        form = {
            "legal_name": "X", "business_type": "individual",
            "country": "US", "address_line1": "1 A", "city": "C", "state": "S", "postal_code": "94000",
            "phone": "+15550000000", "payout_method": "stripe_connect",
        }
        r = requests.post(f"{API}/seller/apply", json=form, headers=_auth(tok))
        assert r.status_code == 400
        assert "email" in r.text.lower()

    def test_duplicate_pending_rejected(self, db):
        email = f"TEST_dup_{uuid.uuid4().hex[:8]}@example.com"
        tok, user = _register(email)
        uid = user["id"]
        _run(db.users.update_one(
            {"id": uid},
            {"$set": {"email_verified": True, "phone_verified": True, "phone": "+15550001111"}},
        ))
        form = {
            "legal_name": "Dup", "business_type": "individual",
            "country": "US", "address_line1": "1 D", "city": "Dcity", "state": "S", "postal_code": "94000",
            "phone": "+15550001111", "payout_method": "stripe_connect",
        }
        r1 = requests.post(f"{API}/seller/apply", json=form, headers=_auth(tok))
        assert r1.status_code == 200
        assert r1.json()["status"] == "pending"
        r2 = requests.post(f"{API}/seller/apply", json=form, headers=_auth(tok))
        assert r2.status_code == 400
        assert "pending" in r2.text.lower()
