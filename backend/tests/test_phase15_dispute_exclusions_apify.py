"""Phase 15 tests:
(1) Dispute reason exclusions from auto-refund rule.
(2) Apify sync status endpoints (public + admin) & trigger endpoint.

Threshold + exclusions reset at end so unrelated suites remain unaffected.
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
ADMIN = {"email": "admin@merchari-global.local", "password": "admin123"}
SEED_SELLER = {"email": "sophia_style@demo.local", "password": "demo1234"}


# ---------- helpers ----------
def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json()["token"]


def _register():
    ts = int(time.time() * 1000)
    payload = {
        "email": f"e2e_p15_{ts}_{uuid.uuid4().hex[:6]}@example.com",
        "username": f"e2e_p15_{ts}_{uuid.uuid4().hex[:6]}",
        "password": "pass1234",
    }
    r = requests.post(f"{API}/auth/register", json=payload, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    return d["token"], d["user"]


def _hdr(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _put_settings(admin_token, body):
    r = requests.put(f"{API}/admin/settings", json=body, headers=_hdr(admin_token), timeout=30)
    return r


def _get_category(admin_token):
    r = requests.get(f"{API}/categories", timeout=30)
    assert r.status_code == 200
    cats = r.json()
    if cats:
        return cats[0]["id"]
    r = requests.post(
        f"{API}/categories",
        json={"name": f"TEST_p15_{uuid.uuid4().hex[:6]}", "icon": "shirt", "sort_order": 99},
        headers=_hdr(admin_token), timeout=30,
    )
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _create_listing(seller_token, category_id, price):
    payload = {
        "title": f"TEST_p15 {uuid.uuid4().hex[:6]}",
        "description": "phase 15 test",
        "price": price,
        "category_id": category_id,
        "condition": "good",
        "images": [],
        "shipping_paid_by": "seller",
    }
    r = requests.post(f"{API}/listings", json=payload, headers=_hdr(seller_token), timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


def _create_order(buyer_token, listing_id):
    r = requests.post(
        f"{API}/orders",
        json={"listing_id": listing_id, "shipping_address": {"line1": "1 test", "city": "SF", "zip": "94103"}},
        headers=_hdr(buyer_token), timeout=30,
    )
    assert r.status_code == 200, r.text
    return r.json()


def _create_dispute(buyer_token, order_id, reason, desc="test dispute"):
    r = requests.post(
        f"{API}/disputes",
        json={"order_id": order_id, "reason": reason, "description": desc},
        headers=_hdr(buyer_token), timeout=30,
    )
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
def _reset(admin_token):
    yield
    try:
        _put_settings(admin_token, {
            "dispute_auto_refund_threshold": 0.0,
            "dispute_auto_refund_excluded_reasons": ["counterfeit"],
        })
    except Exception as e:
        print(f"WARN: reset failed: {e}")


# ---------- Settings field ----------
class TestExclusionsSettings:
    def test_get_settings_exposes_default(self, admin_token):
        # Reset to default first
        _put_settings(admin_token, {"dispute_auto_refund_excluded_reasons": ["counterfeit"]})
        r = requests.get(f"{API}/admin/settings", headers=_hdr(admin_token), timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert "dispute_auto_refund_excluded_reasons" in data
        v = data["dispute_auto_refund_excluded_reasons"]
        assert isinstance(v, list)
        assert "counterfeit" in v

    def test_put_persists_valid_list(self, admin_token):
        r = _put_settings(admin_token, {"dispute_auto_refund_excluded_reasons": ["counterfeit", "other"]})
        assert r.status_code == 200, r.text
        data = r.json()
        assert set(data["dispute_auto_refund_excluded_reasons"]) == {"counterfeit", "other"}
        # persistence check
        r2 = requests.get(f"{API}/admin/settings", headers=_hdr(admin_token), timeout=30)
        assert set(r2.json()["dispute_auto_refund_excluded_reasons"]) == {"counterfeit", "other"}

    def test_unknown_reasons_filtered(self, admin_token):
        r = _put_settings(admin_token, {"dispute_auto_refund_excluded_reasons": ["counterfeit", "bogus", "damaged"]})
        assert r.status_code == 200, r.text
        v = r.json()["dispute_auto_refund_excluded_reasons"]
        assert "bogus" not in v
        assert set(v) == {"counterfeit", "damaged"}

    def test_non_list_rejected_400(self, admin_token):
        r = _put_settings(admin_token, {"dispute_auto_refund_excluded_reasons": "counterfeit"})
        assert r.status_code == 400
        # message check
        try:
            body = r.json()
            msg = body.get("detail") if isinstance(body, dict) else str(body)
        except Exception:
            msg = r.text
        assert "must be a list" in str(msg), msg

    def test_empty_list_allowed(self, admin_token):
        r = _put_settings(admin_token, {"dispute_auto_refund_excluded_reasons": []})
        assert r.status_code == 200
        assert r.json()["dispute_auto_refund_excluded_reasons"] == []


# ---------- Auto-refund gating by reason ----------
class TestAutoRefundGating:
    def test_excluded_counterfeit_stays_open(self, admin_token, seller_token, category_id):
        _put_settings(admin_token, {
            "dispute_auto_refund_threshold": 100.0,
            "dispute_auto_refund_excluded_reasons": ["counterfeit", "other"],
        })
        listing = _create_listing(seller_token, category_id, 15.0)
        buyer_token, _ = _register()

        # snapshot buyer wallet
        me_before = requests.get(f"{API}/auth/me", headers=_hdr(buyer_token), timeout=30).json()
        bal_before = float(me_before.get("wallet_balance", 0.0))

        order = _create_order(buyer_token, listing["id"])
        d = _create_dispute(buyer_token, order["id"], "counterfeit", "fake product")
        assert d["status"] == "open", d
        assert not d.get("resolved_at")

        # wallet unchanged
        me_after = requests.get(f"{API}/auth/me", headers=_hdr(buyer_token), timeout=30).json()
        assert float(me_after.get("wallet_balance", 0.0)) == bal_before

        # order not cancelled
        r = requests.get(f"{API}/orders", headers=_hdr(buyer_token), timeout=30)
        o = next(x for x in r.json() if x["id"] == order["id"])
        assert o["status"] != "cancelled"

    def test_non_excluded_damaged_auto_refunds(self, admin_token, seller_token, category_id):
        _put_settings(admin_token, {
            "dispute_auto_refund_threshold": 100.0,
            "dispute_auto_refund_excluded_reasons": ["counterfeit", "other"],
        })
        listing = _create_listing(seller_token, category_id, 15.0)
        buyer_token, _ = _register()
        order = _create_order(buyer_token, listing["id"])
        d = _create_dispute(buyer_token, order["id"], "damaged", "broken")
        assert d["status"] == "refunded", d
        assert d.get("resolved_at")

    def test_excluded_other_stays_open(self, admin_token, seller_token, category_id):
        _put_settings(admin_token, {
            "dispute_auto_refund_threshold": 100.0,
            "dispute_auto_refund_excluded_reasons": ["counterfeit", "other"],
        })
        listing = _create_listing(seller_token, category_id, 15.0)
        buyer_token, _ = _register()
        order = _create_order(buyer_token, listing["id"])
        d = _create_dispute(buyer_token, order["id"], "other", "reason other")
        assert d["status"] == "open", d

    def test_over_threshold_stays_open_even_if_not_excluded(self, admin_token, seller_token, category_id):
        _put_settings(admin_token, {
            "dispute_auto_refund_threshold": 100.0,
            "dispute_auto_refund_excluded_reasons": ["counterfeit", "other"],
        })
        listing = _create_listing(seller_token, category_id, 200.0)
        buyer_token, _ = _register()
        order = _create_order(buyer_token, listing["id"])
        d = _create_dispute(buyer_token, order["id"], "not_received", "never came")
        assert d["status"] == "open", d


# ---------- Apify sync status ----------
class TestApifySync:
    def test_admin_status_shape(self, admin_token):
        r = requests.get(f"{API}/admin/sync/status", headers=_hdr(admin_token), timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("source") == "junglee/amazon-crawler", d
        assert isinstance(d.get("total_listings"), int)
        assert d.get("last_sync_at") or d.get("started_at"), d

    def test_public_status_matches_shape(self):
        r = requests.get(f"{API}/sync/status", timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("source") == "junglee/amazon-crawler"
        assert isinstance(d.get("total_listings"), int)

    def test_trigger_apify_sync(self, admin_token):
        r = requests.post(
            f"{API}/admin/sync/apify",
            json={"target_count": 500, "replace_existing": False},
            headers=_hdr(admin_token), timeout=60,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("ok") is True, d
        assert d.get("started") is True or d.get("already_running") is True, d
