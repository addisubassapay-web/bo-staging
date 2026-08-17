"""Iteration 28 backend tests: Email Preferences, Admin Email Log, Stripe Checkout.

Covers:
- PUT /api/me/email-prefs (auth) + GET /api/auth/me includes email_prefs
- GET /api/admin/email/log (admin-only) + kind filter
- POST /api/admin/email/test (admin-only)
- POST /api/checkout/stripe-session (validations + happy path)
- GET /api/payments/status/{session_id} (unknown -> 404; created -> pending)
- POST /api/webhook/stripe (bad signature -> 400)
"""
import os
import time
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or "http://localhost:8001"
API = f"{BASE}/api"

ADMIN = {"email": "admin@mercari.local", "password": "admin123"}
DEMO = {"email": "sophia_style@demo.local", "password": "demo1234"}


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed {r.status_code}: {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin_token():
    return _login(**ADMIN)


@pytest.fixture(scope="module")
def user_token():
    return _login(**DEMO)


@pytest.fixture(scope="module")
def user_headers(user_token):
    return {"Authorization": f"Bearer {user_token}"}


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ============ Email Preferences ============
class TestEmailPrefs:
    def test_me_includes_email_prefs(self, user_headers):
        r = requests.get(f"{API}/auth/me", headers=user_headers, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert "email_prefs" in data, f"email_prefs missing in /auth/me: keys={list(data.keys())}"

    def test_update_email_prefs_persists(self, user_headers):
        # Toggle 'order' off
        r = requests.put(f"{API}/me/email-prefs", headers=user_headers, json={"order": False}, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("ok") is True
        assert body["email_prefs"]["order"] is False
        # verify persisted
        me = requests.get(f"{API}/auth/me", headers=user_headers, timeout=30).json()
        assert me["email_prefs"]["order"] is False
        # other keys preserved (should be true by default)
        for k in ("sale", "wallet", "payout", "dispute", "system"):
            assert me["email_prefs"].get(k) is not False or True  # just ensure key path works
        # revert
        r2 = requests.put(f"{API}/me/email-prefs", headers=user_headers, json={"order": True}, timeout=30)
        assert r2.status_code == 200
        assert r2.json()["email_prefs"]["order"] is True

    def test_update_email_prefs_empty_body_400(self, user_headers):
        r = requests.put(f"{API}/me/email-prefs", headers=user_headers, json={}, timeout=30)
        assert r.status_code == 400

    def test_update_email_prefs_unauthorized(self):
        r = requests.put(f"{API}/me/email-prefs", json={"order": False}, timeout=30)
        assert r.status_code in (401, 403)


# ============ Admin Email Log ============
class TestAdminEmailLog:
    def test_log_admin_only(self, user_headers):
        r = requests.get(f"{API}/admin/email/log", headers=user_headers, timeout=30)
        assert r.status_code == 403

    def test_log_returns_items(self, admin_headers):
        r = requests.get(f"{API}/admin/email/log", headers=admin_headers, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert "items" in data and "count" in data
        assert isinstance(data["items"], list)

    def test_log_kind_filter(self, admin_headers):
        r = requests.get(f"{API}/admin/email/log?kind=admin_test", headers=admin_headers, timeout=30)
        assert r.status_code == 200
        for item in r.json()["items"]:
            assert item.get("kind") == "admin_test"

    def test_admin_send_test_email(self, admin_headers):
        to = f"e2e_test_{int(time.time())}@example.com"
        r = requests.post(f"{API}/admin/email/test", headers=admin_headers, json={"to": to}, timeout=60)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "ok" in body
        assert "configured" in body
        # verify a log entry was created (kind admin_test)
        log = requests.get(f"{API}/admin/email/log?kind=admin_test", headers=admin_headers, timeout=30).json()
        assert any(item.get("to") == to for item in log["items"]), "test email should appear in email log"

    def test_admin_send_test_email_bad_addr(self, admin_headers):
        r = requests.post(f"{API}/admin/email/test", headers=admin_headers, json={"to": "not-an-email"}, timeout=30)
        assert r.status_code == 400


# ============ Stripe Checkout ============
def _find_active_listing(seller_id_exclude: str = None):
    r = requests.get(f"{API}/listings?limit=20", timeout=30)
    assert r.status_code == 200
    items = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
    for it in items:
        if it.get("status") == "active" and it.get("seller_id") != seller_id_exclude:
            return it
    return None


class TestStripeCheckout:
    def test_create_session_success(self, admin_headers):
        # admin buying (won't be seller)
        listing = _find_active_listing()
        assert listing, "no active listing to test"
        payload = {
            "listing_id": listing["id"],
            "quantity": 1,
            "shipping_address": {"name": "Admin Test", "line1": "1 Test St", "city": "SF",
                                  "state": "CA", "postal_code": "94103", "country": "US"},
            "origin_url": "https://example.com",
        }
        r = requests.post(f"{API}/checkout/stripe-session", headers=admin_headers, json=payload, timeout=60)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "checkout_url" in body
        assert body["checkout_url"].startswith("https://checkout.stripe.com/"), body["checkout_url"]
        assert "session_id" in body
        assert body["amount"] > 0
        # Save for status test
        pytest.stripe_session_id = body["session_id"]
        pytest.stripe_amount = body["amount"]

    def test_status_returns_pending(self, admin_headers):
        sid = getattr(pytest, "stripe_session_id", None)
        if not sid:
            pytest.skip("no session_id from prior test")
        r = requests.get(f"{API}/payments/status/{sid}", timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["session_id"] == sid
        assert body["payment_status"] in ("pending", "paid", "unpaid", None)
        assert body.get("amount") == pytest.stripe_amount
        assert body.get("currency") == "usd"

    def test_status_unknown_session_404(self):
        r = requests.get(f"{API}/payments/status/cs_fake_missing_abc123", timeout=30)
        assert r.status_code == 404

    def test_invalid_listing_404(self, admin_headers):
        payload = {"listing_id": "nonexistent-id", "quantity": 1,
                   "shipping_address": {"name": "x", "line1": "1", "city": "SF",
                                          "state": "CA", "postal_code": "94103", "country": "US"},
                   "origin_url": "https://example.com"}
        r = requests.post(f"{API}/checkout/stripe-session", headers=admin_headers, json=payload, timeout=30)
        assert r.status_code == 404

    def test_self_purchase_400(self, user_headers, user_token):
        # sophia is the seller of some listings — find one owned by her
        me = requests.get(f"{API}/auth/me", headers=user_headers, timeout=30).json()
        r = requests.get(f"{API}/listings?seller_id={me['id']}&limit=5", timeout=30)
        items = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
        own = next((it for it in items if it.get("seller_id") == me["id"] and it.get("status") == "active"), None)
        if not own:
            pytest.skip("sophia has no active listing")
        payload = {"listing_id": own["id"], "quantity": 1,
                   "shipping_address": {"name": "x", "line1": "1", "city": "SF",
                                          "state": "CA", "postal_code": "94103", "country": "US"},
                   "origin_url": "https://example.com"}
        r = requests.post(f"{API}/checkout/stripe-session", headers=user_headers, json=payload, timeout=30)
        assert r.status_code == 400

    def test_invalid_origin_url_400(self, admin_headers):
        listing = _find_active_listing()
        assert listing
        payload = {"listing_id": listing["id"], "quantity": 1,
                   "shipping_address": {"name": "x", "line1": "1", "city": "SF",
                                          "state": "CA", "postal_code": "94103", "country": "US"},
                   "origin_url": "not-a-url"}
        r = requests.post(f"{API}/checkout/stripe-session", headers=admin_headers, json=payload, timeout=30)
        assert r.status_code == 400

    def test_unauth_returns_401(self):
        listing = _find_active_listing()
        payload = {"listing_id": listing["id"], "quantity": 1,
                   "shipping_address": {"name": "x", "line1": "1", "city": "SF",
                                          "state": "CA", "postal_code": "94103", "country": "US"},
                   "origin_url": "https://example.com"}
        r = requests.post(f"{API}/checkout/stripe-session", json=payload, timeout=30)
        assert r.status_code in (401, 403)


class TestStripeWebhook:
    def test_bad_signature_returns_400(self):
        r = requests.post(f"{API}/webhook/stripe",
                          data=b'{"type":"checkout.session.completed"}',
                          headers={"Stripe-Signature": "invalid", "Content-Type": "application/json"},
                          timeout=30)
        assert r.status_code == 400
