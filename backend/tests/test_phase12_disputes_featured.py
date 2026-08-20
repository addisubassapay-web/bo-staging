"""
Phase 12 backend tests: Disputes flow (create, permissions, admin resolve refund/reject/review)
+ /api/stores-featured regression.
"""
import os
import time
import uuid
import requests
import pytest

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"

ADMIN_EMAIL = "admin@mercuri-global.local"
ADMIN_PASSWORD = "admin123"


# ---------- helpers ----------
def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["token"], r.json()["user"]


def _register(email, username, password="pass1234"):
    r = requests.post(f"{API}/auth/register",
                      json={"email": email, "username": username, "password": password}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["token"], r.json()["user"]


def _h(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _ensure_active_listing_not_owned_by(user_id):
    """Pick an active listing whose seller != user; if none, create one as sophia_style demo seller."""
    r = requests.get(f"{API}/listings", params={"limit": 60}, timeout=30)
    assert r.status_code == 200, r.text
    for lst in r.json():
        if lst.get("seller_id") != user_id and lst.get("status") == "active":
            return lst
    # Fallback: log in demo seller, create a fresh listing
    seller_tok, _ = _login("sophia_style@demo.local", "demo1234")
    # get a category
    cr = requests.get(f"{API}/categories", timeout=30)
    cats = cr.json()
    assert cats, "no categories"
    payload = {
        "title": f"TEST_disputable_{uuid.uuid4().hex[:6]}",
        "description": "Test item for dispute flow", "price": 9.99,
        "category_id": cats[0]["id"], "condition": "good",
        "images": ["data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="],
    }
    r = requests.post(f"{API}/listings", headers=_h(seller_tok), json=payload, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


def _wallet_balance(token):
    r = requests.get(f"{API}/wallet", headers=_h(token), timeout=30)
    assert r.status_code == 200, r.text
    return float(r.json().get("balance", 0.0))


# ---------- fixtures ----------
@pytest.fixture(scope="module")
def admin_token():
    tok, _ = _login(ADMIN_EMAIL, ADMIN_PASSWORD)
    return tok


@pytest.fixture(scope="module")
def buyer():
    ts = int(time.time())
    email = f"e2e_buyer_{ts}_{uuid.uuid4().hex[:6]}@example.com"
    tok, user = _register(email, f"buyer{ts}{uuid.uuid4().hex[:4]}")
    return {"token": tok, "user": user}


@pytest.fixture(scope="module")
def order_ctx(buyer):
    """Create an order for the buyer to enable a dispute."""
    listing = _ensure_active_listing_not_owned_by(buyer["user"]["id"])
    payload = {
        "listing_id": listing["id"],
        "shipping_address": {
            "name": "Test Buyer", "line1": "1 Main St", "city": "SF",
            "state": "CA", "postal_code": "94107", "country": "US",
        },
    }
    r = requests.post(f"{API}/orders", headers=_h(buyer["token"]), json=payload, timeout=30)
    assert r.status_code == 200, r.text
    order = r.json()
    return {"listing": listing, "order": order}


# ---------- Featured storefronts regression ----------
class TestFeaturedStores:
    def test_stores_featured_shape_and_sort(self):
        r = requests.get(f"{API}/stores-featured", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list)
        # all returned are active
        for s in data:
            assert s.get("is_active", True) is True
        # sorted asc by featured_rank when >1
        if len(data) > 1:
            ranks = [s.get("featured_rank", 0) for s in data]
            assert ranks == sorted(ranks), f"featured_rank not asc: {ranks}"


# ---------- Dispute create ----------
class TestDisputeCreate:
    def test_reject_empty_description(self, buyer, order_ctx):
        r = requests.post(f"{API}/disputes", headers=_h(buyer["token"]),
                          json={"order_id": order_ctx["order"]["id"],
                                "reason": "damaged", "description": "   ", "photos": []}, timeout=30)
        assert r.status_code == 400, r.text

    def test_only_buyer_can_open(self, admin_token, order_ctx):
        # admin isn't the buyer -> 403
        r = requests.post(f"{API}/disputes", headers=_h(admin_token),
                          json={"order_id": order_ctx["order"]["id"],
                                "reason": "damaged", "description": "bogus"}, timeout=30)
        assert r.status_code == 403, r.text

    def test_unknown_order_404(self, buyer):
        r = requests.post(f"{API}/disputes", headers=_h(buyer["token"]),
                          json={"order_id": "nope-" + uuid.uuid4().hex,
                                "reason": "damaged", "description": "x"}, timeout=30)
        assert r.status_code == 404, r.text

    def test_create_success_and_persist(self, buyer, order_ctx):
        payload = {
            "order_id": order_ctx["order"]["id"],
            "reason": "not_as_described",
            "description": "Item is not what was pictured — wrong color and size.",
            "photos": [],
        }
        r = requests.post(f"{API}/disputes", headers=_h(buyer["token"]), json=payload, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "open"
        assert d["order_id"] == order_ctx["order"]["id"]
        assert d["buyer_id"] == buyer["user"]["id"]
        assert d["reason"] == "not_as_described"
        assert abs(d["amount"] - float(order_ctx["order"]["amount"])) < 0.01
        # Persist via GET /disputes/mine
        r2 = requests.get(f"{API}/disputes/mine", headers=_h(buyer["token"]), timeout=30)
        assert r2.status_code == 200
        assert any(x["id"] == d["id"] for x in r2.json())
        # store on module
        order_ctx["dispute_id"] = d["id"]

    def test_duplicate_open_dispute_rejected(self, buyer, order_ctx):
        r = requests.post(f"{API}/disputes", headers=_h(buyer["token"]),
                          json={"order_id": order_ctx["order"]["id"],
                                "reason": "damaged", "description": "still broken"}, timeout=30)
        assert r.status_code == 400, r.text


# ---------- Dispute detail permissions ----------
class TestDisputeDetail:
    def test_buyer_can_get_detail(self, buyer, order_ctx):
        did = order_ctx["dispute_id"]
        r = requests.get(f"{API}/disputes/{did}", headers=_h(buyer["token"]), timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["id"] == did

    def test_unknown_dispute_404(self, buyer):
        r = requests.get(f"{API}/disputes/nope-{uuid.uuid4().hex}", headers=_h(buyer["token"]), timeout=30)
        assert r.status_code == 404

    def test_unrelated_user_403(self, order_ctx):
        # create a second buyer, they shouldn't access someone else's dispute
        ts = int(time.time())
        tok, _ = _register(f"e2e_other_{ts}_{uuid.uuid4().hex[:6]}@example.com",
                           f"other{ts}{uuid.uuid4().hex[:4]}")
        r = requests.get(f"{API}/disputes/{order_ctx['dispute_id']}", headers=_h(tok), timeout=30)
        assert r.status_code == 403, r.text

    def test_admin_can_get_detail(self, admin_token, order_ctx):
        r = requests.get(f"{API}/disputes/{order_ctx['dispute_id']}", headers=_h(admin_token), timeout=30)
        assert r.status_code == 200


# ---------- Admin listing / filters ----------
class TestAdminList:
    def test_non_admin_forbidden(self, buyer):
        r = requests.get(f"{API}/admin/disputes", headers=_h(buyer["token"]), timeout=30)
        assert r.status_code in (401, 403)

    def test_admin_list_all(self, admin_token, order_ctx):
        r = requests.get(f"{API}/admin/disputes", headers=_h(admin_token), timeout=30)
        assert r.status_code == 200
        ids = [d["id"] for d in r.json()]
        assert order_ctx["dispute_id"] in ids

    def test_admin_list_status_open(self, admin_token, order_ctx):
        r = requests.get(f"{API}/admin/disputes", headers=_h(admin_token),
                         params={"status": "open"}, timeout=30)
        assert r.status_code == 200
        for d in r.json():
            assert d["status"] == "open"
        assert any(d["id"] == order_ctx["dispute_id"] for d in r.json())

    def test_admin_list_status_rejected_excludes_open(self, admin_token, order_ctx):
        r = requests.get(f"{API}/admin/disputes", headers=_h(admin_token),
                         params={"status": "rejected"}, timeout=30)
        assert r.status_code == 200
        ids = [d["id"] for d in r.json()]
        assert order_ctx["dispute_id"] not in ids


# ---------- Admin resolve: review then refund + wallet delta ----------
class TestAdminResolve:
    def test_mark_reviewing(self, admin_token, order_ctx):
        r = requests.post(f"{API}/admin/disputes/{order_ctx['dispute_id']}/resolve",
                          headers=_h(admin_token),
                          json={"action": "review", "admin_notes": "looking into it",
                                "resolution": ""}, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "reviewing"

    def test_refund_credits_buyer_wallet_and_cancels_order(self, admin_token, buyer, order_ctx):
        pre_balance = _wallet_balance(buyer["token"])
        amount = float(order_ctx["order"]["amount"])
        r = requests.post(f"{API}/admin/disputes/{order_ctx['dispute_id']}/resolve",
                          headers=_h(admin_token),
                          json={"action": "refund",
                                "admin_notes": "approved",
                                "resolution": "Refunded to wallet"}, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "refunded"
        assert d.get("resolved_at")

        post_balance = _wallet_balance(buyer["token"])
        assert abs((post_balance - pre_balance) - amount) < 0.01, \
            f"expected +{amount}, got delta {post_balance - pre_balance}"

        # Order cancelled
        r2 = requests.get(f"{API}/orders", headers=_h(buyer["token"]), timeout=30)
        assert r2.status_code == 200
        row = next((o for o in r2.json() if o["id"] == order_ctx["order"]["id"]), None)
        assert row is not None
        assert row["status"] == "cancelled", row

    def test_cannot_resolve_already_refunded(self, admin_token, order_ctx):
        r = requests.post(f"{API}/admin/disputes/{order_ctx['dispute_id']}/resolve",
                          headers=_h(admin_token),
                          json={"action": "reject"}, timeout=30)
        assert r.status_code == 400, r.text


# ---------- Reject path on a separate dispute ----------
class TestRejectPath:
    def test_reject_flow(self, buyer, admin_token):
        # need a fresh order for this buyer
        listing = _ensure_active_listing_not_owned_by(buyer["user"]["id"])
        r = requests.post(f"{API}/orders", headers=_h(buyer["token"]),
                          json={"listing_id": listing["id"], "shipping_address": {}}, timeout=30)
        assert r.status_code == 200, r.text
        order = r.json()
        r = requests.post(f"{API}/disputes", headers=_h(buyer["token"]),
                          json={"order_id": order["id"],
                                "reason": "other", "description": "wrong shade"}, timeout=30)
        assert r.status_code == 200, r.text
        did = r.json()["id"]
        r = requests.post(f"{API}/admin/disputes/{did}/resolve",
                          headers=_h(admin_token),
                          json={"action": "reject",
                                "resolution": "Item matched description"}, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "rejected"
