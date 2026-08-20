"""
Phase 3 backend tests:
- POST /orders/{id}/shipping-advance (one-stage, jump-to, validation errors, RBAC)
- Background shipping_progress_loop auto-advance (uses direct Mongo backdate)
- GET /listings?sort=trending ordering
- PUT /listings/{id} owner/admin/other permissions (regression check)
- Light regression: auth register/login/me, verify email/phone, seller apply w/ id doc,
  admin approve, upload/download, ai/listing-suggest, /users/{id}/public
"""
import base64
import io
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(Path(__file__).resolve().parents[2] / "frontend" / ".env")
load_dotenv(Path(__file__).resolve().parents[1] / ".env")
BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

ADMIN_EMAIL = "admin@mercuri-global.local"
ADMIN_PASSWORD = "admin123"


# ---------- helpers ----------
def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text}"
    return r.json()["token"]


def _register(email, username, password="pass1234"):
    r = requests.post(f"{API}/auth/register", json={
        "email": email, "username": username, "password": password
    }, timeout=30)
    assert r.status_code in (200, 201), r.text
    return r.json()


def _auth(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="session")
def mongo_db():
    client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)
    return client[DB_NAME]


@pytest.fixture(scope="session")
def admin_token():
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture(scope="session")
def alt_user():
    ts = int(time.time() * 1000)
    email = f"e2e_alt3_{ts}@example.com"
    _register(email, f"e2ealt3{ts}")
    tok = _login(email, "pass1234")
    me = requests.get(f"{API}/auth/me", headers=_auth(tok), timeout=15).json()
    return {"token": tok, "user": me}


@pytest.fixture(scope="session")
def buyer_user():
    ts = int(time.time() * 1000)
    email = f"e2e_buyer3_{ts}@example.com"
    _register(email, f"e2ebuyer3{ts}")
    tok = _login(email, "pass1234")
    me = requests.get(f"{API}/auth/me", headers=_auth(tok), timeout=15).json()
    return {"token": tok, "user": me}


def _create_admin_listing_and_order(admin_tok, buyer_tok, price=25.5):
    cats = requests.get(f"{API}/categories", timeout=15).json()
    cat = cats[0]
    r = requests.post(f"{API}/listings", headers=_auth(admin_tok), json={
        "title": f"TEST Phase3 {uuid.uuid4().hex[:6]}",
        "description": "phase3 shipping tests",
        "price": price,
        "category_id": cat["id"],
        "condition": "good",
        "images": ["https://picsum.photos/id/1080/400/400.jpg"],
        "shipping_paid_by": "buyer",
    }, timeout=30)
    assert r.status_code == 200, r.text
    listing = r.json()
    r = requests.post(f"{API}/orders", headers=_auth(buyer_tok), json={
        "listing_id": listing["id"],
        "shipping_address": {"name": "Buyer", "line1": "1 T St", "city": "Testville",
                             "state": "CA", "postal_code": "94000", "country": "US"},
    }, timeout=30)
    assert r.status_code == 200, r.text
    return listing, r.json()


def _create_label(admin_tok, oid):
    r = requests.post(f"{API}/orders/{oid}/shipping-label", headers=_auth(admin_tok), timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


# =========================================================
# Shipping label create — fresh order (regression + Phase3 fields)
# =========================================================
class TestShippingLabelFreshOrder:
    def test_label_persists_events_provider_and_created_at(self, admin_token, buyer_user):
        _, order = _create_admin_listing_and_order(admin_token, buyer_user["token"])
        oid = order["id"]
        label = _create_label(admin_token, oid)
        assert label["tracking_number"].startswith("MOCK")
        assert label["dev_mock"] is True

        # GET tracking
        r = requests.get(f"{API}/orders/{oid}/tracking", headers=_auth(admin_token), timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["has_label"] is True
        assert d["current_status"] == "label_created"
        assert d["provider"] == "mock"
        assert d["dev_mock"] is True
        assert isinstance(d["events"], list) and len(d["events"]) >= 1
        assert d["events"][0]["status"] == "label_created"


# =========================================================
# shipping-advance
# =========================================================
class TestShippingAdvance:
    def test_one_stage_advance_notifies_buyer(self, admin_token, buyer_user):
        _, order = _create_admin_listing_and_order(admin_token, buyer_user["token"])
        oid = order["id"]
        _create_label(admin_token, oid)

        r = requests.post(f"{API}/orders/{oid}/shipping-advance",
                          headers=_auth(admin_token), json={}, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["current_status"] == "picked_up"
        assert body["event"]["status"] == "picked_up"

        # tracking reflects
        r = requests.get(f"{API}/orders/{oid}/tracking", headers=_auth(admin_token), timeout=15)
        d = r.json()
        assert d["current_status"] == "picked_up"
        statuses = [e["status"] for e in d["events"]]
        assert "label_created" in statuses and "picked_up" in statuses

        # buyer received notification with type=order + title has "Shipping update"
        r = requests.get(f"{API}/notifications",
                         headers=_auth(buyer_user["token"]), timeout=15)
        assert r.status_code == 200
        notifs = r.json()
        matches = [n for n in notifs
                   if n["type"] == "order" and "Shipping update" in n["title"]]
        assert len(matches) >= 1, f"No shipping-update notification. Got: {[n['title'] for n in notifs][:10]}"

    def test_jump_to_delivered(self, admin_token, buyer_user):
        _, order = _create_admin_listing_and_order(admin_token, buyer_user["token"])
        oid = order["id"]
        _create_label(admin_token, oid)
        r = requests.post(f"{API}/orders/{oid}/shipping-advance",
                          headers=_auth(admin_token), json={"to_status": "delivered"}, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["current_status"] == "delivered"

        # Already delivered => 400
        r2 = requests.post(f"{API}/orders/{oid}/shipping-advance",
                           headers=_auth(admin_token), json={}, timeout=30)
        assert r2.status_code == 400

    def test_earlier_or_equal_target_rejected(self, admin_token, buyer_user):
        _, order = _create_admin_listing_and_order(admin_token, buyer_user["token"])
        oid = order["id"]
        _create_label(admin_token, oid)
        # equal to current (label_created)
        r = requests.post(f"{API}/orders/{oid}/shipping-advance",
                          headers=_auth(admin_token), json={"to_status": "label_created"}, timeout=30)
        assert r.status_code == 400

        # advance one, then attempt earlier
        requests.post(f"{API}/orders/{oid}/shipping-advance",
                      headers=_auth(admin_token), json={}, timeout=30)
        r = requests.post(f"{API}/orders/{oid}/shipping-advance",
                          headers=_auth(admin_token), json={"to_status": "label_created"}, timeout=30)
        assert r.status_code == 400

    def test_invalid_to_status_rejected(self, admin_token, buyer_user):
        _, order = _create_admin_listing_and_order(admin_token, buyer_user["token"])
        oid = order["id"]
        _create_label(admin_token, oid)
        r = requests.post(f"{API}/orders/{oid}/shipping-advance",
                          headers=_auth(admin_token), json={"to_status": "banana"}, timeout=30)
        assert r.status_code == 400

    def test_non_seller_non_admin_403(self, admin_token, buyer_user, alt_user):
        _, order = _create_admin_listing_and_order(admin_token, buyer_user["token"])
        oid = order["id"]
        _create_label(admin_token, oid)
        # buyer is not seller
        r = requests.post(f"{API}/orders/{oid}/shipping-advance",
                          headers=_auth(buyer_user["token"]), json={}, timeout=30)
        assert r.status_code == 403
        # unrelated user
        r = requests.post(f"{API}/orders/{oid}/shipping-advance",
                          headers=_auth(alt_user["token"]), json={}, timeout=30)
        assert r.status_code == 403


# =========================================================
# Background auto-advance loop
# =========================================================
class TestShippingAutoAdvance:
    def test_loop_advances_after_backdate(self, admin_token, buyer_user, mongo_db):
        _, order = _create_admin_listing_and_order(admin_token, buyer_user["token"])
        oid = order["id"]
        _create_label(admin_token, oid)

        # backdate label_created_at to 2 minutes ago so picked_up threshold (60s FAST) triggers
        past = datetime.now(timezone.utc) - timedelta(minutes=2)
        res = mongo_db.orders.update_one({"id": oid}, {"$set": {"label_created_at": past}})
        assert res.matched_count == 1

        # background loop iterates every 30s + initial 5s sleep. Poll up to 50s.
        advanced = False
        for _ in range(25):
            time.sleep(2)
            r = requests.get(f"{API}/orders/{oid}/tracking",
                             headers=_auth(admin_token), timeout=15)
            if r.status_code == 200 and r.json().get("current_status") != "label_created":
                advanced = True
                cur = r.json()["current_status"]
                break
        assert advanced, "Background loop did not auto-advance within ~50s"
        # picked_up is the expected next step for ~2 min age
        assert cur in ("picked_up", "in_transit", "out_for_delivery", "delivered")


# =========================================================
# Trending sort
# =========================================================
class TestTrendingSort:
    def test_trending_sort_orders_by_views_then_likes_then_created(self, admin_token, mongo_db):
        # seed 3 listings with controlled counters
        cats = requests.get(f"{API}/categories", timeout=15).json()
        cat_id = cats[0]["id"]
        ids = []
        for i in range(3):
            r = requests.post(f"{API}/listings", headers=_auth(admin_token), json={
                "title": f"TEST Trending {uuid.uuid4().hex[:6]}",
                "description": "trending sort test",
                "price": 10.0 + i,
                "category_id": cat_id,
                "condition": "good",
                "images": ["https://picsum.photos/id/1080/400/400.jpg"],
                "shipping_paid_by": "buyer",
            }, timeout=30)
            assert r.status_code == 200, r.text
            ids.append(r.json()["id"])

        # Assign distinct views/likes so we can find them in trending order
        # id0: views=99999, likes=1  (should rank first among the trio)
        # id1: views=99998, likes=5000 (second)
        # id2: views=1,     likes=99999 (last of trio)
        mongo_db.listings.update_one({"id": ids[0]}, {"$set": {"views_count": 99999, "likes_count": 1}})
        mongo_db.listings.update_one({"id": ids[1]}, {"$set": {"views_count": 99998, "likes_count": 5000}})
        mongo_db.listings.update_one({"id": ids[2]}, {"$set": {"views_count": 1, "likes_count": 99999}})

        r = requests.get(f"{API}/listings?sort=trending&limit=200", timeout=30)
        assert r.status_code == 200, r.text
        listings = r.json()
        pos = {}
        for idx, l in enumerate(listings):
            if l["id"] in ids:
                pos[l["id"]] = idx
        assert set(pos.keys()) == set(ids), f"Missing seeded listings: {pos}"
        # order id0 < id1 < id2 among our trio
        assert pos[ids[0]] < pos[ids[1]] < pos[ids[2]], f"trending order wrong: {pos}"


# =========================================================
# PUT /api/listings/{id} — owner/admin/other RBAC
# =========================================================
class TestListingUpdatePermissions:
    def test_owner_and_admin_can_update_other_cannot(self, admin_token, alt_user, buyer_user):
        # admin creates listing (admin is owner)
        cats = requests.get(f"{API}/categories", timeout=15).json()
        cat_id = cats[0]["id"]
        r = requests.post(f"{API}/listings", headers=_auth(admin_token), json={
            "title": f"TEST EditListing {uuid.uuid4().hex[:6]}",
            "description": "d",
            "price": 12.0,
            "category_id": cat_id,
            "condition": "good",
            "images": ["https://picsum.photos/id/1080/400/400.jpg"],
            "shipping_paid_by": "buyer",
        }, timeout=30)
        assert r.status_code == 200, r.text
        lid = r.json()["id"]

        # owner (admin) update - should work
        r = requests.put(f"{API}/listings/{lid}", headers=_auth(admin_token),
                         json={"title": "TEST EditListing UPDATED"}, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["title"] == "TEST EditListing UPDATED"

        # unrelated user - 403
        r = requests.put(f"{API}/listings/{lid}", headers=_auth(alt_user["token"]),
                         json={"title": "hack"}, timeout=30)
        assert r.status_code == 403

        r = requests.put(f"{API}/listings/{lid}", headers=_auth(buyer_user["token"]),
                         json={"title": "hack"}, timeout=30)
        assert r.status_code == 403


# =========================================================
# Light regression
# =========================================================
class TestRegression:
    def test_auth_me_carries_verification_flags(self, admin_token):
        r = requests.get(f"{API}/auth/me", headers=_auth(admin_token), timeout=15)
        assert r.status_code == 200
        me = r.json()
        for k in ("email_verified", "phone_verified", "seller_status"):
            assert k in me

    def test_register_login_me(self):
        ts = int(time.time() * 1000)
        email = f"e2e_reg3_{ts}@example.com"
        _register(email, f"e2ereg3{ts}")
        tok = _login(email, "pass1234")
        r = requests.get(f"{API}/auth/me", headers=_auth(tok), timeout=15)
        assert r.status_code == 200
        assert r.json()["email"] == email

    def test_public_user(self, admin_token):
        r = requests.get(f"{API}/auth/me", headers=_auth(admin_token), timeout=15)
        uid = r.json()["id"]
        r = requests.get(f"{API}/users/{uid}/public", timeout=15)
        assert r.status_code == 200
        assert "email" not in r.json()

    def test_verify_email_phone_flow(self):
        ts = int(time.time() * 1000)
        email = f"e2e_ver3_{ts}@example.com"
        _register(email, f"e2ever3{ts}")
        tok = _login(email, "pass1234")
        h = _auth(tok)
        r = requests.post(f"{API}/verify/email/send", headers=h, json={}, timeout=15)
        assert r.status_code == 200 and r.json().get("token")
        token = r.json()["token"]
        r = requests.post(f"{API}/verify/email/confirm", headers=h,
                         json={"token": token}, timeout=15)
        assert r.status_code == 200
        r = requests.post(f"{API}/verify/phone/send", headers=h,
                         json={"phone": "+15551230000"}, timeout=15)
        assert r.status_code == 200 and r.json().get("code")
        code = r.json()["code"]
        r = requests.post(f"{API}/verify/phone/confirm", headers=h,
                         json={"phone": "+15551230000", "code": code}, timeout=15)
        assert r.status_code == 200

    def test_seller_apply_with_doc_and_admin_approve(self, admin_token):
        ts = int(time.time() * 1000)
        email = f"e2e_sd3_{ts}@example.com"
        _register(email, f"e2esd3{ts}")
        tok = _login(email, "pass1234")
        h = _auth(tok)
        # verify email/phone
        r = requests.post(f"{API}/verify/email/send", headers=h, json={}, timeout=15)
        requests.post(f"{API}/verify/email/confirm", headers=h,
                      json={"token": r.json()["token"]}, timeout=15)
        r = requests.post(f"{API}/verify/phone/send", headers=h,
                         json={"phone": "+15559990000"}, timeout=15)
        requests.post(f"{API}/verify/phone/confirm", headers=h,
                     json={"phone": "+15559990000", "code": r.json()["code"]}, timeout=15)
        # upload id doc
        img = requests.get("https://picsum.photos/id/1080/300/300.jpg", timeout=30).content
        files = {"file": ("id.jpg", img, "image/jpeg")}
        r = requests.post(f"{API}/upload", headers=h, files=files, timeout=60)
        assert r.status_code == 200, r.text
        fid = r.json()["id"]
        # apply
        r = requests.post(f"{API}/seller/apply", headers=h, json={
            "legal_name": "Test Seller",
            "business_type": "individual",
            "country": "US",
            "payout_method": "bank_transfer",
            "id_document_file_id": fid,
        }, timeout=30)
        assert r.status_code == 200, r.text
        # admin approve
        r = requests.get(f"{API}/admin/seller-applications?status=pending",
                         headers=_auth(admin_token), timeout=30)
        assert r.status_code == 200
        pending = [a for a in r.json() if a.get("user_email") == email or a.get("legal_name") == "Test Seller"]
        assert pending, "our pending seller app not found"
        app_id = pending[0]["id"]
        r = requests.put(f"{API}/admin/seller-applications/{app_id}",
                          headers=_auth(admin_token), json={"status": "approved"}, timeout=30)
        assert r.status_code == 200, r.text

    def test_ai_listing_suggest_with_image(self, admin_token):
        img = requests.get("https://picsum.photos/id/1080/400/400.jpg", timeout=30).content
        b64 = base64.b64encode(img).decode()
        r = requests.post(f"{API}/ai/listing-suggest", headers=_auth(admin_token),
                          json={"image_base64": b64}, timeout=120)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("title", "description", "category_slug", "category_id",
                  "category_name", "condition", "suggested_price_usd"):
            assert k in d, f"missing {k} in AI response"
