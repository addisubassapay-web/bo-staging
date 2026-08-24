"""Phase 14 tests: (1) Dispute auto-refund threshold rule; (2) PWA icons.

All API tests hit the public REACT_APP_BACKEND_URL. Threshold is reset to 0 in a
session-scoped teardown so unrelated suites are not affected.
"""
import os
import time
import uuid
import pytest
import requests

def _load_backend_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v.rstrip("/")
    # fallback: read from frontend/.env
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip().rstrip("/")
    except Exception:
        pass
    raise RuntimeError("REACT_APP_BACKEND_URL not set")


BASE_URL = _load_backend_url()
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@mercari-global.local", "password": "admin123"}
SEED_SELLER = {"email": "sophia_style@demo.local", "password": "demo1234"}


# ---------- helpers ----------

def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return r.json()["token"]


def _register():
    ts = int(time.time() * 1000)
    payload = {
        "email": f"e2e_p14_{ts}_{uuid.uuid4().hex[:6]}@example.com",
        "username": f"e2e_p14_{ts}_{uuid.uuid4().hex[:6]}",
        "password": "pass1234",
    }
    r = requests.post(f"{API}/auth/register", json=payload, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    return data["token"], data["user"]


def _auth_headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _set_threshold(admin_token, value):
    r = requests.put(
        f"{API}/admin/settings",
        json={"dispute_auto_refund_threshold": value},
        headers=_auth_headers(admin_token),
        timeout=30,
    )
    assert r.status_code == 200, r.text
    return r.json()


def _get_category(admin_token):
    r = requests.get(f"{API}/categories", timeout=30)
    assert r.status_code == 200
    cats = r.json()
    if cats:
        return cats[0]["id"]
    # create one
    r = requests.post(
        f"{API}/categories",
        json={"name": f"TEST_p14_cat_{uuid.uuid4().hex[:6]}", "icon": "shirt", "sort_order": 99},
        headers=_auth_headers(admin_token),
        timeout=30,
    )
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _create_listing(seller_token, category_id, price, title_suffix=""):
    payload = {
        "title": f"TEST_p14 listing {title_suffix or uuid.uuid4().hex[:6]}",
        "description": "phase 14 test listing",
        "price": price,
        "category_id": category_id,
        "condition": "good",
        "images": [],
        "shipping_paid_by": "seller",
    }
    r = requests.post(f"{API}/listings", json=payload, headers=_auth_headers(seller_token), timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


def _create_order(buyer_token, listing_id):
    r = requests.post(
        f"{API}/orders",
        json={"listing_id": listing_id, "shipping_address": {"line1": "1 test", "city": "SF", "zip": "94103"}},
        headers=_auth_headers(buyer_token),
        timeout=30,
    )
    assert r.status_code == 200, r.text
    return r.json()


def _get_me(token):
    r = requests.get(f"{API}/auth/me", headers=_auth_headers(token), timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


# ---------- fixtures ----------

@pytest.fixture(scope="module")
def admin_token():
    return _login(**ADMIN)


@pytest.fixture(scope="module")
def seller_token():
    return _login(**SEED_SELLER)


@pytest.fixture(scope="module")
def category_id(admin_token):
    return _get_category(admin_token)


@pytest.fixture(scope="module", autouse=True)
def _reset_threshold_after(admin_token):
    yield
    # Always reset to 0 after tests finish
    try:
        _set_threshold(admin_token, 0.0)
    except Exception as e:
        print(f"WARN: could not reset threshold: {e}")


# ---------- Settings API ----------

class TestSettings:
    def test_get_settings_exposes_field_as_number(self, admin_token):
        # Ensure threshold defaulted / merged even for pre-existing docs
        r = requests.get(f"{API}/admin/settings", headers=_auth_headers(admin_token), timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "dispute_auto_refund_threshold" in data
        v = data["dispute_auto_refund_threshold"]
        assert v is not None
        assert isinstance(v, (int, float))

    def test_put_settings_persists_and_get_returns_it(self, admin_token):
        _set_threshold(admin_token, 25.0)
        r = requests.get(f"{API}/admin/settings", headers=_auth_headers(admin_token), timeout=30)
        assert r.status_code == 200
        assert float(r.json()["dispute_auto_refund_threshold"]) == 25.0
        # reset
        _set_threshold(admin_token, 0.0)

    def test_non_admin_cannot_update(self):
        token, _ = _register()
        r = requests.put(
            f"{API}/admin/settings",
            json={"dispute_auto_refund_threshold": 5.0},
            headers=_auth_headers(token),
            timeout=30,
        )
        assert r.status_code == 403


# ---------- Auto-refund behaviour ----------

class TestAutoRefund:
    def test_auto_refund_when_amount_le_threshold(self, admin_token, seller_token, category_id):
        _set_threshold(admin_token, 25.0)
        listing = _create_listing(seller_token, category_id, 15.0, "auto")
        buyer_token, buyer = _register()
        before = _get_me(buyer_token)
        bal_before = float(before.get("wallet_balance", 0.0))

        order = _create_order(buyer_token, listing["id"])
        assert float(order["amount"]) == 15.0

        r = requests.post(
            f"{API}/disputes",
            json={"order_id": order["id"], "reason": "damaged", "description": "arrived broken"},
            headers=_auth_headers(buyer_token),
            timeout=30,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "refunded", d
        assert d["resolution"] and d["resolution"].startswith("Auto-refunded"), d["resolution"]
        assert d["resolved_at"], "resolved_at should be set"
        assert "Auto-refunded (threshold=$25.00)" in (d.get("admin_notes") or "")

        # Buyer wallet credited by amount
        after = _get_me(buyer_token)
        bal_after = float(after.get("wallet_balance", 0.0))
        assert round(bal_after - bal_before, 2) == 15.0, (bal_before, bal_after)

        # Order cancelled
        r = requests.get(f"{API}/orders", headers=_auth_headers(buyer_token), timeout=30)
        assert r.status_code == 200
        o = next((x for x in r.json() if x["id"] == order["id"]), None)
        assert o is not None
        assert o["status"] == "cancelled", o

        # Buyer notification present
        r = requests.get(f"{API}/notifications", headers=_auth_headers(buyer_token), timeout=30)
        assert r.status_code == 200, r.text
        titles = [n.get("title", "") for n in r.json()]
        assert any("Refund issued automatically" in t for t in titles), titles

        # Seller notification present
        r = requests.get(f"{API}/notifications", headers=_auth_headers(seller_token), timeout=30)
        assert r.status_code == 200
        seller_titles = [n.get("title", "") for n in r.json()]
        assert any("Dispute auto-refunded" in t for t in seller_titles), seller_titles[:20]

        _set_threshold(admin_token, 0.0)

    def test_no_auto_refund_when_amount_gt_threshold(self, admin_token, seller_token, category_id):
        _set_threshold(admin_token, 25.0)
        listing = _create_listing(seller_token, category_id, 40.0, "over")
        buyer_token, _ = _register()
        before = _get_me(buyer_token)
        bal_before = float(before.get("wallet_balance", 0.0))
        order = _create_order(buyer_token, listing["id"])

        r = requests.post(
            f"{API}/disputes",
            json={"order_id": order["id"], "reason": "not_as_described", "description": "wrong item"},
            headers=_auth_headers(buyer_token),
            timeout=30,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "open", d
        assert not d.get("resolved_at")

        # No wallet mutation
        after = _get_me(buyer_token)
        assert float(after.get("wallet_balance", 0.0)) == bal_before

        # Order NOT cancelled
        r = requests.get(f"{API}/orders", headers=_auth_headers(buyer_token), timeout=30)
        o = next(x for x in r.json() if x["id"] == order["id"])
        assert o["status"] != "cancelled"

        _set_threshold(admin_token, 0.0)

    def test_zero_amount_order_does_not_auto_refund(self, admin_token, seller_token, category_id):
        """Guard: amount > 0 — a $0 order must not auto-refund even under threshold."""
        _set_threshold(admin_token, 25.0)
        try:
            listing = _create_listing(seller_token, category_id, 0.0, "zeroamt")
        except AssertionError:
            pytest.skip("Backend rejects $0 listings — guard cannot be exercised via public API")
            return
        buyer_token, _ = _register()
        order = _create_order(buyer_token, listing["id"])
        assert float(order["amount"]) == 0.0
        r = requests.post(
            f"{API}/disputes",
            json={"order_id": order["id"], "reason": "damaged", "description": "zero amt guard"},
            headers=_auth_headers(buyer_token),
            timeout=30,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "open", d  # guard held
        _set_threshold(admin_token, 0.0)

    def test_threshold_zero_disables_rule(self, admin_token, seller_token, category_id):
        _set_threshold(admin_token, 0.0)
        listing = _create_listing(seller_token, category_id, 5.0, "zero")
        buyer_token, _ = _register()
        order = _create_order(buyer_token, listing["id"])
        r = requests.post(
            f"{API}/disputes",
            json={"order_id": order["id"], "reason": "damaged", "description": "cheap item damaged"},
            headers=_auth_headers(buyer_token),
            timeout=30,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "open", d


# ---------- PWA icons ----------

class TestPWA:
    def test_icon_192(self):
        # icons are served by frontend at root — test via public backend URL host root
        # REACT_APP_BACKEND_URL is the same host, so hit root path.
        r = requests.get(f"{BASE_URL}/icon-192.png", timeout=30)
        assert r.status_code == 200, r.status_code
        assert "image/png" in r.headers.get("content-type", "")
        assert len(r.content) > 500

    def test_icon_512(self):
        r = requests.get(f"{BASE_URL}/icon-512.png", timeout=30)
        assert r.status_code == 200
        assert "image/png" in r.headers.get("content-type", "")
        assert len(r.content) > 500

    def test_favicon(self):
        r = requests.get(f"{BASE_URL}/favicon.png", timeout=30)
        assert r.status_code == 200

    def test_manifest_lists_both_icons(self):
        r = requests.get(f"{BASE_URL}/manifest.json", timeout=30)
        assert r.status_code == 200
        m = r.json()
        sizes = {i["sizes"]: i for i in m.get("icons", [])}
        assert "192x192" in sizes and "512x512" in sizes, sizes
        for i in m["icons"]:
            assert i.get("purpose") == "any maskable"
            assert i.get("type") == "image/png"
