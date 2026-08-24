"""Phase 11 tests: Sortable Storefronts (admin drag-and-drop) + Weekly Recap in seller dashboard."""
import os
import pytest
import requests
from pathlib import Path


def _load_backend_url():
    env_val = os.environ.get("REACT_APP_BACKEND_URL")
    if env_val:
        return env_val.rstrip("/")
    env_path = Path("/app/frontend/.env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL not set")


BASE_URL = _load_backend_url()
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@mercari-global.local"
ADMIN_PASS = "admin123"
SELLER_EMAIL = "urban_finds@demo.local"
SELLER_PASS = "demo1234"


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"Login failed for {email}: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin_token():
    return _login(ADMIN_EMAIL, ADMIN_PASS)


@pytest.fixture(scope="module")
def seller_token():
    return _login(SELLER_EMAIL, SELLER_PASS)


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def seller_headers(seller_token):
    return {"Authorization": f"Bearer {seller_token}"}


# ============= Sortable Storefronts =============

class TestAdminStoresList:
    def test_admin_stores_requires_auth(self):
        r = requests.get(f"{API}/admin/stores", timeout=15)
        assert r.status_code in (401, 403)

    def test_admin_stores_non_admin_forbidden(self, seller_headers):
        r = requests.get(f"{API}/admin/stores", headers=seller_headers, timeout=15)
        assert r.status_code == 403

    def test_admin_stores_list_sorted(self, admin_headers):
        r = requests.get(f"{API}/admin/stores", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        stores = r.json()
        assert isinstance(stores, list)
        # if we have >= 2 stores, verify featured_rank ascending (None -> treated as large)
        ranks = [s.get("featured_rank") if s.get("featured_rank") is not None else 10**9 for s in stores]
        assert ranks == sorted(ranks), f"Not sorted by featured_rank asc: {ranks}"


class TestReorderStores:
    def test_reorder_forbidden_for_non_admin(self, seller_headers):
        r = requests.post(f"{API}/admin/stores/reorder", json={"ids": []}, headers=seller_headers, timeout=15)
        assert r.status_code == 403

    def test_reorder_requires_auth(self):
        r = requests.post(f"{API}/admin/stores/reorder", json={"ids": ["x"]}, timeout=15)
        assert r.status_code in (401, 403)

    def test_reorder_bad_payload(self, admin_headers):
        r = requests.post(f"{API}/admin/stores/reorder", json={"ids": []}, headers=admin_headers, timeout=15)
        assert r.status_code == 400

    def test_reorder_updates_persistence(self, admin_headers):
        # get current stores
        r = requests.get(f"{API}/admin/stores", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        stores = r.json()
        if len(stores) < 2:
            pytest.skip("Need at least 2 stores to test reordering")
        ids = [s["id"] for s in stores]
        original = list(ids)

        # reverse and reorder
        reversed_ids = list(reversed(ids))
        rr = requests.post(f"{API}/admin/stores/reorder", json={"ids": reversed_ids}, headers=admin_headers, timeout=15)
        assert rr.status_code == 200
        body = rr.json()
        assert body.get("ok") is True
        assert body.get("count") == len(reversed_ids)

        # verify GET reflects new order
        r2 = requests.get(f"{API}/admin/stores", headers=admin_headers, timeout=15)
        assert r2.status_code == 200
        new_stores = r2.json()
        new_ids = [s["id"] for s in new_stores if s["id"] in reversed_ids]
        assert new_ids == reversed_ids, f"Order not persisted. Expected {reversed_ids} got {new_ids}"

        # restore original order
        restore = requests.post(f"{API}/admin/stores/reorder", json={"ids": original}, headers=admin_headers, timeout=15)
        assert restore.status_code == 200


class TestPublicFeaturedStores:
    def test_public_no_auth_required(self):
        r = requests.get(f"{API}/stores-featured?limit=12", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) <= 12
        # only active stores
        for s in data:
            assert s.get("is_active") is True, f"Inactive store leaked: {s.get('id')}"
        # sorted asc by featured_rank
        ranks = [s.get("featured_rank") if s.get("featured_rank") is not None else 10**9 for s in data]
        assert ranks == sorted(ranks)

    def test_public_limit_clamp(self):
        r = requests.get(f"{API}/stores-featured?limit=3", timeout=15)
        assert r.status_code == 200
        assert len(r.json()) <= 3

    def test_deactivated_excluded(self, admin_headers):
        # find a store, deactivate, ensure it's excluded from public, then reactivate
        r = requests.get(f"{API}/admin/stores", headers=admin_headers, timeout=15)
        stores = r.json()
        if not stores:
            pytest.skip("No stores available")
        target = stores[0]
        sid = target["id"]
        original_active = target.get("is_active", True)
        try:
            u = requests.put(f"{API}/admin/stores/{sid}", json={"is_active": False}, headers=admin_headers, timeout=15)
            assert u.status_code == 200
            pub = requests.get(f"{API}/stores-featured?limit=50", timeout=15)
            assert pub.status_code == 200
            ids = [s["id"] for s in pub.json()]
            assert sid not in ids, "Deactivated store should not appear in /stores-featured"
        finally:
            requests.put(f"{API}/admin/stores/{sid}", json={"is_active": original_active}, headers=admin_headers, timeout=15)


class TestAdminStorePutRegression:
    def test_put_supports_multiple_fields(self, admin_headers):
        r = requests.get(f"{API}/admin/stores", headers=admin_headers, timeout=15)
        stores = r.json()
        if not stores:
            pytest.skip("No stores")
        sid = stores[0]["id"]
        original_tier = stores[0].get("verified_tier")
        original_tagline = stores[0].get("tagline")

        u = requests.put(
            f"{API}/admin/stores/{sid}",
            json={"verified_tier": "gold", "tagline": "TEST_tagline_phase11", "featured_rank": 0},
            headers=admin_headers, timeout=15,
        )
        assert u.status_code == 200
        body = u.json()
        assert body.get("verified_tier") == "gold"
        assert body.get("tagline") == "TEST_tagline_phase11"
        # restore
        requests.put(
            f"{API}/admin/stores/{sid}",
            json={"verified_tier": original_tier or "none", "tagline": original_tagline or ""},
            headers=admin_headers, timeout=15,
        )


# ============= Weekly Recap =============

class TestWeeklyRecap:
    def _get_dashboard(self, headers):
        r = requests.get(f"{API}/seller/dashboard", headers=headers, timeout=20)
        assert r.status_code == 200, f"{r.status_code} {r.text}"
        return r.json()

    def test_dashboard_has_weekly_recap_seller(self, seller_headers):
        data = self._get_dashboard(seller_headers)
        assert "weekly_recap" in data, f"No weekly_recap in payload keys={list(data.keys())}"
        wr = data["weekly_recap"]
        assert "week_start" in wr and isinstance(wr["week_start"], str)
        assert isinstance(wr["earnings"], (int, float))
        assert isinstance(wr["orders"], int)
        assert "top_product" in wr  # nullable
        if wr["top_product"] is not None:
            for k in ("id", "title", "price", "images"):
                assert k in wr["top_product"], f"top_product missing key {k}"
        assert isinstance(wr["delta_pct_vs_current"], (int, float))
        assert isinstance(wr["suggestion"], str) and len(wr["suggestion"]) > 0

    def test_dashboard_weekly_recap_admin(self, admin_headers):
        # admin likely has no orders → empty recap is fine
        r = requests.get(f"{API}/seller/dashboard", headers=admin_headers, timeout=20)
        # admin may or may not have seller dashboard access; if 200, validate shape
        if r.status_code == 200:
            wr = r.json().get("weekly_recap")
            assert wr is not None
            assert "week_start" in wr
            assert wr["orders"] >= 0
            assert wr["earnings"] >= 0
        else:
            # acceptable if admin gate returns 403
            assert r.status_code in (403, 404)
