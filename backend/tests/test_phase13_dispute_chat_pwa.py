"""Phase 13 backend tests: Dispute chat + PWA static endpoints.

Covers:
- GET /api/disputes/{id}/messages -> 404 unknown, 403 non-participant, 200 sorted for buyer/seller/admin
- POST /api/disputes/{id}/messages -> auth required, buyer/seller/admin can post, empty body+photos=400, closed=400
- Notification cross-post: buyer msg -> seller notified, seller msg -> buyer notified, admin msg -> both
- PWA: /manifest.json (HEAD 200, contents) and /service-worker.js (200 with install+fetch listeners)
"""
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@merchari-global.local"
ADMIN_PASSWORD = "admin123"
SELLER_EMAIL = "sophia_style@demo.local"
SELLER_PASSWORD = "demo1234"


# ---------- helpers ----------
def _register(prefix="e2e_buyer"):
    ts = int(time.time() * 1000)
    email = f"{prefix}_{ts}_{uuid.uuid4().hex[:6]}@example.com"
    username = f"{prefix}{ts}{uuid.uuid4().hex[:4]}"
    r = requests.post(f"{API}/auth/register", json={
        "email": email, "username": username, "password": "pass1234"
    })
    assert r.status_code == 200, r.text
    j = r.json()
    return j.get("token") or j.get("access_token"), j["user"]


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    j = r.json()
    return j.get("token") or j.get("access_token"), j["user"]


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def admin_token():
    tok, _ = _login(ADMIN_EMAIL, ADMIN_PASSWORD)
    return tok


@pytest.fixture(scope="module")
def seller():
    tok, u = _login(SELLER_EMAIL, SELLER_PASSWORD)
    return tok, u


@pytest.fixture(scope="module")
def buyer():
    return _register("e2e_buyer_p13")


@pytest.fixture(scope="module")
def dispute(seller, buyer):
    seller_tok, seller_user = seller
    buyer_tok, buyer_user = buyer

    # Find an active listing owned by seller
    r = requests.get(f"{API}/listings?limit=50")
    assert r.status_code == 200
    listings = r.json()
    listing = None
    for L in listings:
        if L.get("seller_id") == seller_user["id"] and L.get("status") == "active":
            listing = L
            break
    if listing is None:
        # Create a fresh sophia listing with a valid category_id
        cats = requests.get(f"{API}/categories").json()
        cat_id = cats[0]["id"]
        r = requests.post(f"{API}/listings", headers=_h(seller_tok), json={
            "title": "TEST_p13_disputable_item",
            "description": "Item for dispute chat test",
            "price": 5.5,
            "category_id": cat_id,
            "condition": "new",
            "images": [],
        })
        assert r.status_code == 200, r.text
        listing = r.json()
    actual_seller_id = listing["seller_id"]

    # Buyer places order
    r = requests.post(f"{API}/orders", headers=_h(buyer_tok), json={
        "listing_id": listing["id"],
        "shipping_address": {
            "name": "Test Buyer",
            "line1": "123 Test St", "city": "Testville",
            "state": "CA", "postal_code": "94000", "country": "US",
        },
    })
    assert r.status_code == 200, f"order failed: {r.text}"
    order = r.json()

    # Open dispute
    r = requests.post(f"{API}/disputes", headers=_h(buyer_tok), json={
        "order_id": order["id"],
        "reason": "not_as_described",
        "description": "TEST_p13 dispute chat",
    })
    assert r.status_code == 200, f"dispute failed: {r.text}"
    return r.json()


# ---------- GET messages ----------
class TestListMessages:
    def test_404_unknown_id(self, buyer):
        tok, _ = buyer
        r = requests.get(f"{API}/disputes/does-not-exist/messages", headers=_h(tok))
        assert r.status_code == 404

    def test_403_non_participant(self, dispute):
        # Register a stranger
        stranger_tok, _ = _register("e2e_stranger_p13")
        r = requests.get(f"{API}/disputes/{dispute['id']}/messages", headers=_h(stranger_tok))
        assert r.status_code == 403

    def test_200_buyer_seller_admin_see_sorted(self, dispute, buyer, seller, admin_token):
        for tok in (buyer[0], seller[0], admin_token):
            r = requests.get(f"{API}/disputes/{dispute['id']}/messages", headers=_h(tok))
            assert r.status_code == 200, r.text
            data = r.json()
            assert isinstance(data, list)


# ---------- POST messages ----------
class TestPostMessages:
    def test_auth_required(self, dispute):
        r = requests.post(f"{API}/disputes/{dispute['id']}/messages", json={"body": "hi"})
        assert r.status_code in (401, 403)

    def test_empty_body_and_photos_400(self, dispute, buyer):
        r = requests.post(f"{API}/disputes/{dispute['id']}/messages",
                          headers=_h(buyer[0]), json={"body": "", "photos": []})
        assert r.status_code == 400

    def test_buyer_can_post_and_seller_notified(self, dispute, buyer, seller):
        # Count seller notifications before
        r0 = requests.get(f"{API}/notifications", headers=_h(seller[0]))
        assert r0.status_code == 200
        before = len([n for n in r0.json() if n.get("type") == "dispute"])

        body = f"buyer-msg-{uuid.uuid4().hex[:6]}"
        r = requests.post(f"{API}/disputes/{dispute['id']}/messages",
                          headers=_h(buyer[0]), json={"body": body})
        assert r.status_code == 200, r.text
        m = r.json()
        assert m["body"] == body
        assert m["sender_role"] == "buyer"
        assert m["sender_id"] == buyer[1]["id"]

        r1 = requests.get(f"{API}/notifications", headers=_h(seller[0]))
        after = len([n for n in r1.json() if n.get("type") == "dispute"])
        assert after > before, "Seller should have received a dispute notification"

    def test_seller_can_post_and_buyer_notified(self, dispute, buyer, seller):
        r0 = requests.get(f"{API}/notifications", headers=_h(buyer[0]))
        before = len([n for n in r0.json() if n.get("type") == "dispute"])
        body = f"seller-msg-{uuid.uuid4().hex[:6]}"
        r = requests.post(f"{API}/disputes/{dispute['id']}/messages",
                          headers=_h(seller[0]), json={"body": body})
        assert r.status_code == 200, r.text
        assert r.json()["sender_role"] == "seller"
        r1 = requests.get(f"{API}/notifications", headers=_h(buyer[0]))
        after = len([n for n in r1.json() if n.get("type") == "dispute"])
        assert after > before

    def test_admin_can_post_and_both_notified(self, dispute, buyer, seller, admin_token):
        r0b = requests.get(f"{API}/notifications", headers=_h(buyer[0])).json()
        r0s = requests.get(f"{API}/notifications", headers=_h(seller[0])).json()
        before_b = len([n for n in r0b if n.get("type") == "dispute"])
        before_s = len([n for n in r0s if n.get("type") == "dispute"])

        body = f"admin-msg-{uuid.uuid4().hex[:6]}"
        r = requests.post(f"{API}/disputes/{dispute['id']}/messages",
                          headers=_h(admin_token), json={"body": body})
        assert r.status_code == 200, r.text
        assert r.json()["sender_role"] == "admin"

        r1b = requests.get(f"{API}/notifications", headers=_h(buyer[0])).json()
        r1s = requests.get(f"{API}/notifications", headers=_h(seller[0])).json()
        after_b = len([n for n in r1b if n.get("type") == "dispute"])
        after_s = len([n for n in r1s if n.get("type") == "dispute"])
        assert after_b > before_b, "Buyer should be notified on admin post"
        assert after_s > before_s, "Seller should be notified on admin post"

    def test_messages_sorted_asc(self, dispute, buyer):
        r = requests.get(f"{API}/disputes/{dispute['id']}/messages", headers=_h(buyer[0]))
        assert r.status_code == 200
        msgs = r.json()
        assert len(msgs) >= 3
        times = [m["created_at"] for m in msgs]
        assert times == sorted(times), "Messages must be sorted asc by created_at"

    def test_closed_dispute_rejects_post(self, dispute, buyer, admin_token):
        # Reject the dispute (closes it)
        r = requests.post(f"{API}/admin/disputes/{dispute['id']}/resolve",
                          headers=_h(admin_token),
                          json={"action": "reject", "admin_notes": "closing for test",
                                "resolution": "test"})
        assert r.status_code == 200, r.text
        # Now buyer cannot post
        r2 = requests.post(f"{API}/disputes/{dispute['id']}/messages",
                           headers=_h(buyer[0]), json={"body": "should fail"})
        assert r2.status_code == 400


# ---------- PWA static ----------
class TestPWA:
    def test_manifest_ok(self):
        r = requests.get(f"{BASE_URL}/manifest.json")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("theme_color") == "#FF211F"
        assert data.get("display") == "standalone"
        assert "Merchari-global" in (data.get("name") or "")

    def test_service_worker_ok(self):
        r = requests.get(f"{BASE_URL}/service-worker.js")
        assert r.status_code == 200
        body = r.text
        assert "install" in body
        assert "fetch" in body
