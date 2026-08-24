"""
Phase 19 regression: seller gate, auto-store creation, wallet wholesale-debit,
Follow Feed, Storefront Push reward, Store Follow notifications.

Uses direct MongoDB writes to seed pending seller applications (the /seller/apply
endpoint requires email/phone verification, which is not the flow under test).

Run: pytest backend/tests/test_phase19_regression.py -v
"""
import os
import time
import uuid
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://mercari-global-clone-1.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")


# ---------- Shared session / helpers ----------
def _client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s

def _register(username: str, password: str = "pass1234"):
    email = f"{username}@example.com"
    r = _client().post(f"{API}/auth/register", json={"email": email, "username": username, "password": password})
    assert r.status_code == 200, f"register failed: {r.status_code} {r.text}"
    return r.json()  # {token, user}

def _login(email: str, password: str):
    r = _client().post(f"{API}/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json()

def _auth_session(token: str):
    s = _client()
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s


@pytest.fixture(scope="module")
def mongo():
    c = MongoClient(MONGO_URL)
    yield c[DB_NAME]
    c.close()


@pytest.fixture(scope="module")
def admin_token():
    r = _client().post(f"{API}/auth/login", json={"email": "admin@mercari-global.local", "password": "admin123"})
    if r.status_code != 200:
        pytest.skip("admin login failed")
    return r.json()["token"]


@pytest.fixture(scope="module")
def sophia():
    r = _client().post(f"{API}/auth/login", json={"email": "sophia_style@demo.local", "password": "demo1234"})
    if r.status_code != 200:
        pytest.skip("sophia login failed")
    return r.json()  # token + user


@pytest.fixture(scope="module")
def category_id():
    r = _client().get(f"{API}/categories")
    assert r.status_code == 200
    cats = r.json()
    assert cats, "no categories seeded"
    return cats[0]["id"]


def _fresh_username(prefix="e2e"):
    return f"{prefix}{int(time.time()*1000)}{uuid.uuid4().hex[:4]}"


# =========================================================
# TEST 1 — Seller Gate
# =========================================================
class TestSellerGate:
    def test_unapproved_cannot_create_listing(self, category_id):
        u = _register(_fresh_username("gate1"))
        s = _auth_session(u["token"])
        r = s.post(f"{API}/listings", json={
            "title": "TEST_GATE", "description": "x", "price": 10.0,
            "category_id": category_id, "condition": "good", "images": [],
        })
        assert r.status_code == 403, f"expected 403 got {r.status_code} {r.text}"
        assert "seller verification and approval" in r.text.lower()

    def test_unapproved_cannot_import_single(self):
        u = _register(_fresh_username("gate2"))
        s = _auth_session(u["token"])
        # any random source id — gate must fire before validation
        r = s.post(f"{API}/listings/import", json={"listing_id": "nonexistent", "markup_pct": 5.0})
        assert r.status_code == 403
        assert "seller verification and approval" in r.text.lower()

    def test_unapproved_cannot_import_bulk(self):
        u = _register(_fresh_username("gate3"))
        s = _auth_session(u["token"])
        r = s.post(f"{API}/listings/import/bulk", json={"items": [{"listing_id": "x", "markup_pct": 5.0}]})
        assert r.status_code == 403
        assert "seller verification and approval" in r.text.lower()

    def test_approved_seller_can_create_listing(self, sophia, category_id):
        s = _auth_session(sophia["token"])
        r = s.post(f"{API}/listings", json={
            "title": "TEST_SOPHIA_OK", "description": "seller-gate passes", "price": 12.0,
            "category_id": category_id, "condition": "good", "images": [],
        })
        assert r.status_code == 200, r.text


# =========================================================
# TEST 2 — Auto-store creation on approval
# =========================================================
class TestAutoStoreCreation:
    def _seed_pending_app(self, mongo, user):
        """Insert a pending seller_application directly (bypasses phone/email OTP)."""
        app_id = str(uuid.uuid4())
        mongo.seller_applications.insert_one({
            "id": app_id,
            "user_id": user["id"],
            "user_email": user["email"],
            "user_username": user["username"],
            "legal_name": "Test Seller",
            "business_name": "",
            "business_type": "individual",
            "tax_id": "",
            "country": "US",
            "address_line1": "1 Way",
            "address_line2": "",
            "city": "SF",
            "state": "CA",
            "postal_code": "94103",
            "phone": "+15555550000",
            "payout_method": "stripe_connect",
            "id_document_note": "",
            "id_document_file_id": None,
            "status": "pending",
            "admin_notes": "",
            "created_at": __import__("datetime").datetime.utcnow(),
            "reviewed_at": None,
            "reviewed_by": None,
        })
        mongo.users.update_one({"id": user["id"]}, {"$set": {"seller_status": "pending"}})
        return app_id

    def test_single_approval_creates_store(self, mongo, admin_token):
        auth = _register(_fresh_username("autostore"))
        user = auth["user"]
        app_id = self._seed_pending_app(mongo, user)

        s = _auth_session(admin_token)
        r = s.put(f"{API}/admin/seller-applications/{app_id}", json={"status": "approved"})
        assert r.status_code == 200, r.text

        # user updated
        u_after = mongo.users.find_one({"id": user["id"]}, {"_id": 0})
        assert u_after["seller_status"] == "approved"
        assert u_after.get("store_id"), "store_id missing after approval"

        # store exists with slug derived from username
        store = mongo.stores.find_one({"id": u_after["store_id"]}, {"_id": 0})
        assert store is not None
        assert store["owner_id"] == user["id"]
        # username may be lowercased & dash-safe
        assert user["username"].lower().startswith(store["slug"].split("-")[0][:6])

    def test_bulk_review_creates_stores(self, mongo, admin_token):
        ids = []
        users = []
        for i in range(2):
            auth = _register(_fresh_username(f"bulkstore{i}"))
            users.append(auth["user"])
            ids.append(self._seed_pending_app(mongo, auth["user"]))

        s = _auth_session(admin_token)
        r = s.post(f"{API}/admin/seller-applications/bulk-review",
                   json={"ids": ids, "status": "approved"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["processed"] == 2

        for u in users:
            u_after = mongo.users.find_one({"id": u["id"]}, {"_id": 0})
            assert u_after["seller_status"] == "approved"
            assert u_after.get("store_id"), f"no store_id for {u['username']}"
            store = mongo.stores.find_one({"id": u_after["store_id"]}, {"_id": 0})
            assert store and store["slug"]


# =========================================================
# Helper — make an approved seller with wallet balance + store
# =========================================================
def _make_approved_seller_with_wallet(mongo, wallet_balance: float = 500.0, prefix="seller"):
    auth = _register(_fresh_username(prefix))
    user = auth["user"]
    # Direct DB approval + wallet fund + store
    slug = f"{user['username'].lower()}-store"
    store_id = str(uuid.uuid4())
    mongo.stores.insert_one({
        "id": store_id,
        "owner_id": user["id"],
        "name": f"{user['username']}'s Store",
        "slug": slug,
        "tagline": "",
        "bio": "",
        "logo": "",
        "banner": "",
        "is_active": True,
        "followers_count": 0,
        "total_sales": 0,
        "created_at": __import__("datetime").datetime.utcnow(),
    })
    mongo.users.update_one(
        {"id": user["id"]},
        {"$set": {"seller_status": "approved", "store_id": store_id, "wallet_balance": wallet_balance,
                  "email_verified": True, "phone_verified": True}},
    )
    # Refresh token (user role/status changed, but JWT already valid — same id)
    return {"token": auth["token"], "user": user, "store_id": store_id, "slug": slug}


# =========================================================
# TEST 3 — Wallet wholesale-debit
# =========================================================
class TestWalletWholesaleDebit:
    def test_wholesale_debit_success(self, mongo, category_id):
        # 1) Source seller — creates the base listing
        source = _make_approved_seller_with_wallet(mongo, wallet_balance=0, prefix="src")
        src_s = _auth_session(source["token"])
        r = src_s.post(f"{API}/listings", json={
            "title": "TEST_SRC_LISTING", "description": "wholesale test", "price": 100.0,
            "category_id": category_id, "condition": "good", "images": [],
        })
        assert r.status_code == 200, r.text
        src_listing = r.json()

        # 2) Reseller — approved, well-funded
        reseller = _make_approved_seller_with_wallet(mongo, wallet_balance=500.0, prefix="res")
        res_s = _auth_session(reseller["token"])
        r = res_s.post(f"{API}/listings/import", json={"listing_id": src_listing["id"], "markup_pct": 20.0})
        assert r.status_code == 200, r.text
        imported = r.json()
        assert imported["base_price"] == 100.0
        assert imported["price"] == 120.0

        # 3) Buyer places order
        buyer = _register(_fresh_username("buyer"))
        buy_s = _auth_session(buyer["token"])
        r = buy_s.post(f"{API}/orders", json={"listing_id": imported["id"], "shipping_address": {}})
        assert r.status_code == 200, r.text
        order = r.json()

        assert order["reseller_paid_wholesale"] is True
        # New badge is "new" → 0% discount → wholesale_cost = 100.0
        assert order["reseller_wholesale_cost"] > 0
        assert order["reseller_wholesale_cost"] == pytest.approx(100.0, rel=0.01)

        # Reseller wallet decreased
        res_after = mongo.users.find_one({"id": reseller["user"]["id"]}, {"_id": 0})
        assert res_after["wallet_balance"] == pytest.approx(500.0 - order["reseller_wholesale_cost"], rel=0.01)

        # Source seller frozen balance +wholesale
        src_after = mongo.users.find_one({"id": source["user"]["id"]}, {"_id": 0})
        assert src_after["wallet_frozen_balance"] == pytest.approx(order["reseller_wholesale_cost"], rel=0.01)

    def test_wholesale_skipped_when_insufficient_balance(self, mongo, category_id):
        source = _make_approved_seller_with_wallet(mongo, wallet_balance=0, prefix="src2")
        src_s = _auth_session(source["token"])
        r = src_s.post(f"{API}/listings", json={
            "title": "TEST_SRC2", "description": "poor reseller", "price": 100.0,
            "category_id": category_id, "condition": "good", "images": [],
        })
        assert r.status_code == 200
        src_listing = r.json()

        reseller = _make_approved_seller_with_wallet(mongo, wallet_balance=5.0, prefix="res2")
        res_s = _auth_session(reseller["token"])
        r = res_s.post(f"{API}/listings/import", json={"listing_id": src_listing["id"], "markup_pct": 20.0})
        assert r.status_code == 200
        imported = r.json()

        buyer = _register(_fresh_username("buyer2"))
        buy_s = _auth_session(buyer["token"])
        r = buy_s.post(f"{API}/orders", json={"listing_id": imported["id"], "shipping_address": {}})
        assert r.status_code == 200, r.text
        order = r.json()

        assert order["reseller_paid_wholesale"] is False
        # source seller receives full retail as dropship earnings
        assert order["dropship_source_earnings"] == pytest.approx(100.0, rel=0.01)
        # reseller wallet unchanged
        res_after = mongo.users.find_one({"id": reseller["user"]["id"]}, {"_id": 0})
        assert res_after["wallet_balance"] == pytest.approx(5.0, rel=0.01)


# =========================================================
# TEST 4 — Store Follow Feed
# =========================================================
class TestFollowFeed:
    def test_unauth_401(self):
        r = _client().get(f"{API}/feed/following?limit=20")
        assert r.status_code == 401

    def test_feed_returns_followed_store_listings(self, mongo, category_id):
        # Seller with a fresh listing
        seller = _make_approved_seller_with_wallet(mongo, wallet_balance=0, prefix="feedslr")
        sess = _auth_session(seller["token"])
        r = sess.post(f"{API}/listings", json={
            "title": "TEST_FEED_ITEM", "description": "feed", "price": 30.0,
            "category_id": category_id, "condition": "good", "images": [],
        })
        assert r.status_code == 200
        listing = r.json()

        # Follower user
        follower_auth = _register(_fresh_username("follower"))
        fsess = _auth_session(follower_auth["token"])

        # Empty feed at first
        r = fsess.get(f"{API}/feed/following?limit=20")
        assert r.status_code == 200
        assert r.json() == []

        # Follow the store
        r = fsess.post(f"{API}/stores/{seller['slug']}/follow")
        assert r.status_code == 200
        assert r.json()["following"] is True

        # Feed now contains the seller's listing
        r = fsess.get(f"{API}/feed/following?limit=20")
        assert r.status_code == 200
        ids = [it["id"] for it in r.json()]
        assert listing["id"] in ids

        # And it excludes the follower's own listings (irrelevant here; ensure user's own not there)
        for it in r.json():
            assert it["seller_id"] != follower_auth["user"]["id"]


# =========================================================
# TEST 5 — Storefront Push Reward (only once ever)
# =========================================================
class TestPushReward:
    def test_first_push_sale_credits_bonus_second_does_not(self, mongo, category_id):
        # Fresh seller so no prior push bonus exists
        seller = _make_approved_seller_with_wallet(mongo, wallet_balance=0, prefix="pushslr")
        sess = _auth_session(seller["token"])
        # Listing #1
        r = sess.post(f"{API}/listings", json={
            "title": "TEST_PUSH_1", "description": "push1", "price": 40.0,
            "category_id": category_id, "condition": "good", "images": [],
        })
        assert r.status_code == 200, r.text
        listing1 = r.json()
        # Listing #2
        r = sess.post(f"{API}/listings", json={
            "title": "TEST_PUSH_2", "description": "push2", "price": 50.0,
            "category_id": category_id, "condition": "good", "images": [],
        })
        assert r.status_code == 200, r.text
        listing2 = r.json()

        # Read current push_reward_amount from admin settings
        # (default is 2.0; the API is admin-gated so we just trust the default here)
        expected_bonus = 2.0

        # Buyer #1 with share_ref="push"
        b1 = _register(_fresh_username("pbuyer1"))
        b1s = _auth_session(b1["token"])
        r = b1s.post(f"{API}/orders", json={"listing_id": listing1["id"], "shipping_address": {}, "share_ref": "push"})
        assert r.status_code == 200, r.text
        order1 = r.json()
        assert order1["push_reward_amount"] == pytest.approx(expected_bonus, rel=0.01)

        # 1 push bonus tx exists
        count = mongo.wallet_txs.count_documents({
            "user_id": seller["user"]["id"],
            "type": "bonus",
            "description": {"$regex": "^Storefront Push"},
        })
        assert count == 1

        # Buyer #2 with share_ref="push" — should NOT credit another bonus
        b2 = _register(_fresh_username("pbuyer2"))
        b2s = _auth_session(b2["token"])
        r = b2s.post(f"{API}/orders", json={"listing_id": listing2["id"], "shipping_address": {}, "share_ref": "push"})
        assert r.status_code == 200
        order2 = r.json()
        assert order2["push_reward_amount"] in (0, 0.0)

        count = mongo.wallet_txs.count_documents({
            "user_id": seller["user"]["id"],
            "type": "bonus",
            "description": {"$regex": "^Storefront Push"},
        })
        assert count == 1, "second push sale must NOT credit another bonus"


# =========================================================
# TEST 6 — Store Follow Notifications on new listing / import / bulk
# =========================================================
class TestFollowerNotifications:
    def _get_notif_titles(self, token):
        r = _auth_session(token).get(f"{API}/notifications")
        assert r.status_code == 200, r.text
        return [n.get("title", "") + " | " + n.get("body", "") for n in r.json()]

    def test_notify_on_new_listing(self, mongo, category_id):
        seller = _make_approved_seller_with_wallet(mongo, wallet_balance=0, prefix="nslr1")
        follower = _register(_fresh_username("nflw1"))
        fs = _auth_session(follower["token"])
        r = fs.post(f"{API}/stores/{seller['slug']}/follow")
        assert r.status_code == 200

        ss = _auth_session(seller["token"])
        r = ss.post(f"{API}/listings", json={
            "title": "TEST_NOTIFY_NEW", "description": "notify-me", "price": 21.0,
            "category_id": category_id, "condition": "good", "images": [],
        })
        assert r.status_code == 200
        listing = r.json()

        titles = self._get_notif_titles(follower["token"])
        assert any("TEST_NOTIFY_NEW" in t or listing["title"] in t for t in titles), titles

    def test_notify_on_import(self, mongo, category_id):
        # source seller + listing
        src = _make_approved_seller_with_wallet(mongo, wallet_balance=0, prefix="nsrc")
        sess = _auth_session(src["token"])
        r = sess.post(f"{API}/listings", json={
            "title": "TEST_NOTIFY_SRC", "description": "src", "price": 30.0,
            "category_id": category_id, "condition": "good", "images": [],
        })
        assert r.status_code == 200
        src_listing = r.json()

        # reseller with follower
        reseller = _make_approved_seller_with_wallet(mongo, wallet_balance=500.0, prefix="nres")
        follower = _register(_fresh_username("nflw2"))
        fs = _auth_session(follower["token"])
        r = fs.post(f"{API}/stores/{reseller['slug']}/follow")
        assert r.status_code == 200

        rs = _auth_session(reseller["token"])
        r = rs.post(f"{API}/listings/import", json={"listing_id": src_listing["id"], "markup_pct": 15.0})
        assert r.status_code == 200, r.text
        imported = r.json()

        titles = self._get_notif_titles(follower["token"])
        assert any(imported["title"] in t for t in titles), titles

    def test_notify_on_bulk_import(self, mongo, category_id):
        # source seller with two listings
        src = _make_approved_seller_with_wallet(mongo, wallet_balance=0, prefix="nsrcb")
        sess = _auth_session(src["token"])
        src_ids = []
        for i in range(2):
            r = sess.post(f"{API}/listings", json={
                "title": f"TEST_BULK_SRC_{i}", "description": "bulk src", "price": 20.0 + i,
                "category_id": category_id, "condition": "good", "images": [],
            })
            assert r.status_code == 200
            src_ids.append(r.json()["id"])

        reseller = _make_approved_seller_with_wallet(mongo, wallet_balance=0, prefix="nresb")
        follower = _register(_fresh_username("nflw3"))
        fs = _auth_session(follower["token"])
        r = fs.post(f"{API}/stores/{reseller['slug']}/follow")
        assert r.status_code == 200

        rs = _auth_session(reseller["token"])
        r = rs.post(f"{API}/listings/import/bulk", json={
            "items": [{"listing_id": lid, "markup_pct": 15.0} for lid in src_ids],
        })
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["published_count"] == 2

        titles = self._get_notif_titles(follower["token"])
        assert any("new items" in t.lower() or "added" in t.lower() for t in titles), titles

    def test_no_followers_does_not_break(self, mongo, category_id):
        seller = _make_approved_seller_with_wallet(mongo, wallet_balance=0, prefix="nofol")
        sess = _auth_session(seller["token"])
        r = sess.post(f"{API}/listings", json={
            "title": "TEST_NO_FOLLOWERS", "description": "silent", "price": 9.0,
            "category_id": category_id, "condition": "good", "images": [],
        })
        assert r.status_code == 200
