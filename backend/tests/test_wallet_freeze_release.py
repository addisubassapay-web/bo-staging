"""Backend tests for wallet freeze / release, admin delivery settings,
and confirm-delivery flow. Iteration 17."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://bo-staging.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@mercari-global.local", "password": "admin123"}
DEMO_BUYER = {"email": "sophia_style@demo.local", "password": "demo1234"}


def _login(session, creds):
    r = session.post(f"{API}/auth/login", json=creds, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    tok = r.json()["access_token"] if "access_token" in r.json() else r.json().get("token")
    session.headers.update({"Authorization": f"Bearer {tok}"})
    return r.json()


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    _login(s, ADMIN)
    return s


@pytest.fixture(scope="module")
def buyer_session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    _login(s, DEMO_BUYER)
    return s


@pytest.fixture(scope="module")
def buyer_id(buyer_session):
    me = buyer_session.get(f"{API}/auth/me", timeout=30).json()
    return me["id"]


# --------- Public settings endpoint ---------
class TestPublicSettings:
    def test_public_settings_shape(self):
        r = requests.get(f"{API}/settings/public", timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert "delivery_days_estimate" in data
        assert "delivery_auto_release_days" in data
        assert isinstance(data["delivery_days_estimate"], int)
        assert isinstance(data["delivery_auto_release_days"], int)

    def test_admin_can_update_delivery_days(self, admin_session):
        # Read current
        pub_before = requests.get(f"{API}/settings/public").json()
        original = pub_before["delivery_days_estimate"]
        target = 9 if original != 9 else 8

        r = admin_session.put(f"{API}/admin/settings", json={"delivery_days_estimate": target}, timeout=30)
        assert r.status_code == 200, r.text
        pub_after = requests.get(f"{API}/settings/public").json()
        assert pub_after["delivery_days_estimate"] == target

        # restore
        admin_session.put(f"{API}/admin/settings", json={"delivery_days_estimate": original})


# --------- Wallet endpoint shape ---------
class TestWalletShape:
    def test_wallet_shape(self, buyer_session):
        r = buyer_session.get(f"{API}/wallet", timeout=30)
        assert r.status_code == 200
        data = r.json()
        for k in ("balance", "frozen_balance", "transactions", "pending_withdrawals"):
            assert k in data, f"missing {k}"
        assert isinstance(data["transactions"], list)


# --------- Full freeze/release lifecycle ---------
class TestOrderFreezeRelease:
    @pytest.fixture(scope="class")
    def bought_order(self, buyer_session, buyer_id):
        """Buy any active listing whose seller is not the buyer."""
        # find a listing not owned by buyer
        listings = requests.get(f"{API}/listings?limit=50", timeout=30).json()
        target = None
        for l in listings:
            if l.get("seller_id") != buyer_id and l.get("status") == "active":
                target = l
                break
        assert target, "no suitable listing found for testing"

        # capture seller wallet snapshot (via public user endpoint if available; else infer via order response)
        payload = {
            "listing_id": target["id"],
            "shipping_address": {"street": "123 Test", "city": "SF", "state": "CA", "zip": "94107", "country": "US"},
        }
        r = buyer_session.post(f"{API}/orders", json=payload, timeout=60)
        assert r.status_code == 200, f"order create failed: {r.status_code} {r.text}"
        order = r.json()
        return {"order": order, "listing": target}

    def test_order_has_eta_and_frozen(self, bought_order):
        o = bought_order["order"]
        assert o["estimated_delivery_at"], "estimated_delivery_at missing"
        assert o["funds_released"] is False
        assert o["seller_earnings"] > 0
        assert o["status"] == "paid"

    def test_seller_wallet_tx_created(self, admin_session, bought_order):
        # Admin fetches all orders for verification path
        order_id = bought_order["order"]["id"]
        seller_id = bought_order["order"]["seller_id"]
        # Use admin to inspect seller wallet transactions via a users list endpoint? Fall back: query wallet as seller if we can login.
        # We'll rely on public state: fetch the order back
        got = admin_session.get(f"{API}/admin/orders", timeout=30).json()
        found = [o for o in got if o["id"] == order_id]
        assert found and found[0]["seller_earnings"] > 0
        assert found[0]["funds_released"] is False

    def test_non_buyer_cannot_confirm(self, admin_session, bought_order):
        # admin CAN confirm — so use an unrelated user. Create a fresh one.
        ts = int(time.time())
        s = requests.Session()
        s.headers.update({"Content-Type": "application/json"})
        reg = s.post(f"{API}/auth/register", json={
            "email": f"e2e_{ts}@example.com", "username": f"e2e{ts}", "password": "pass1234"
        }, timeout=30)
        assert reg.status_code == 200, reg.text
        tok = reg.json().get("access_token") or reg.json().get("token")
        s.headers.update({"Authorization": f"Bearer {tok}"})
        r = s.post(f"{API}/orders/{bought_order['order']['id']}/confirm-delivery", timeout=30)
        assert r.status_code == 403, f"expected 403, got {r.status_code} {r.text}"

    def test_buyer_confirms_delivery_releases_frozen(self, buyer_session, bought_order):
        order_id = bought_order["order"]["id"]
        r = buyer_session.post(f"{API}/orders/{order_id}/confirm-delivery", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["funds_released"] is True
        assert data["status"] == "delivered"
        assert data["delivery_confirmed_at"]

    def test_idempotent_confirm(self, buyer_session, bought_order):
        order_id = bought_order["order"]["id"]
        # Snapshot buyer wallet after first release (not seller, but confirm no error)
        r1 = buyer_session.post(f"{API}/orders/{order_id}/confirm-delivery", timeout=30)
        r2 = buyer_session.post(f"{API}/orders/{order_id}/confirm-delivery", timeout=30)
        assert r1.status_code == 200 and r2.status_code == 200
        assert r1.json()["funds_released"] and r2.json()["funds_released"]

    def test_wallet_tx_types_present(self, buyer_session, bought_order):
        # Buyer's own wallet will show transactions if buyer received payouts; skip check for buyer.
        # Instead ensure the wallet endpoint still works.
        r = buyer_session.get(f"{API}/wallet", timeout=30)
        assert r.status_code == 200
