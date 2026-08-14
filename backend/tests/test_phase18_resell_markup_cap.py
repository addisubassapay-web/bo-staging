"""Phase 18: Resell markup enforcement + admin per-user override.

RUN SERIALLY (state is mutated across tests):
  pytest backend/tests/test_phase18_resell_markup_cap.py -o addopts="" -v


Covers:
- GET /api/seller/resell-info (badge/max_markup_pct/applied)
- POST /api/listings/import cap enforcement
- PUT /api/admin/users/{id} resell_markup_override roundtrip + validation
- Non-admin 403 on admin endpoint
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@mercari.local"
ADMIN_PW = "admin123"
SELLER_EMAIL = "sophia_style@demo.local"
SELLER_PW = "demo1234"


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin_token():
    return _login(ADMIN_EMAIL, ADMIN_PW)


@pytest.fixture(scope="module")
def seller_token():
    return _login(SELLER_EMAIL, SELLER_PW)


@pytest.fixture(scope="module")
def seller_info(seller_token):
    r = requests.get(f"{API}/seller/resell-info", headers={"Authorization": f"Bearer {seller_token}"}, timeout=10)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module")
def seller_user_id(admin_token):
    r = requests.get(f"{API}/admin/users", headers={"Authorization": f"Bearer {admin_token}"}, timeout=15)
    assert r.status_code == 200
    for u in r.json():
        if u.get("email") == SELLER_EMAIL:
            return u["id"]
    pytest.skip("sophia_style user not found")


# ---------- resell-info ----------

class TestResellInfo:
    def test_silver_tier_for_sophia(self, seller_info):
        assert seller_info["badge"] == "silver"
        assert seller_info["max_markup_pct"] == 80.0
        assert seller_info["applied"] == "silver"
        assert seller_info["override_active"] is False
        assert seller_info["sales_count"] >= 46
        assert float(seller_info["rating"]) >= 4.5
        assert "resell_markup_caps" in seller_info
        assert seller_info["resell_markup_caps"]["silver"] == 80.0


# ---------- import cap enforcement ----------

def _pick_import_source(seller_token, seller_email):
    """Find an active listing NOT owned by seller and not already imported."""
    r = requests.get(f"{API}/listings", timeout=15)
    assert r.status_code == 200
    for l in r.json():
        if l.get("seller_name") == seller_email.split("@")[0]:
            continue
        if l.get("imported_from_id"):
            continue
        if l.get("status") and l["status"] != "active":
            continue
        return l
    pytest.skip("No importable listing available")


class TestImportEnforcement:
    def test_over_cap_import_rejected(self, seller_token):
        src = _pick_import_source(seller_token, SELLER_EMAIL)
        r = requests.post(
            f"{API}/listings/import",
            json={"listing_id": src["id"], "markup_pct": 90.0},
            headers={"Authorization": f"Bearer {seller_token}"},
            timeout=15,
        )
        assert r.status_code == 400, r.text
        detail = r.json().get("detail", "")
        assert "80" in detail or "cap" in detail.lower() or "tier" in detail.lower() or "markup" in detail.lower()

    def test_under_cap_import_succeeds(self, seller_token):
        src = _pick_import_source(seller_token, SELLER_EMAIL)
        r = requests.post(
            f"{API}/listings/import",
            json={"listing_id": src["id"], "markup_pct": 20.0},
            headers={"Authorization": f"Bearer {seller_token}"},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("imported_from_id") == src["id"]
        # verify persistence via GET
        g = requests.get(f"{API}/listings/{data['id']}", timeout=10)
        assert g.status_code == 200
        assert g.json().get("imported_from_id") == src["id"]


# ---------- admin override roundtrip ----------

class TestAdminOverride:
    def test_set_override_to_10(self, admin_token, seller_token, seller_user_id):
        r = requests.put(
            f"{API}/admin/users/{seller_user_id}",
            json={"resell_markup_override": 10},
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=15,
        )
        assert r.status_code == 200, r.text

        info = requests.get(
            f"{API}/seller/resell-info",
            headers={"Authorization": f"Bearer {seller_token}"},
            timeout=10,
        ).json()
        assert info["max_markup_pct"] == 10.0
        assert info["applied"] == "override"
        assert info["override_active"] is True

    def test_import_at_20_fails_with_override(self, seller_token):
        src = _pick_import_source(seller_token, SELLER_EMAIL)
        r = requests.post(
            f"{API}/listings/import",
            json={"listing_id": src["id"], "markup_pct": 20.0},
            headers={"Authorization": f"Bearer {seller_token}"},
            timeout=15,
        )
        assert r.status_code == 400, r.text

    def test_import_at_8_succeeds_with_override(self, seller_token):
        src = _pick_import_source(seller_token, SELLER_EMAIL)
        r = requests.post(
            f"{API}/listings/import",
            json={"listing_id": src["id"], "markup_pct": 8.0},
            headers={"Authorization": f"Bearer {seller_token}"},
            timeout=15,
        )
        assert r.status_code == 200, r.text

    def test_clear_override(self, admin_token, seller_token, seller_user_id):
        r = requests.put(
            f"{API}/admin/users/{seller_user_id}",
            json={"resell_markup_override": None},
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        info = requests.get(
            f"{API}/seller/resell-info",
            headers={"Authorization": f"Bearer {seller_token}"},
            timeout=10,
        ).json()
        assert info["max_markup_pct"] == 80.0
        assert info["applied"] == "silver"
        assert info["override_active"] is False

    def test_override_out_of_range_rejected(self, admin_token, seller_user_id):
        r = requests.put(
            f"{API}/admin/users/{seller_user_id}",
            json={"resell_markup_override": 999},
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=15,
        )
        assert r.status_code == 400, r.text

    def test_override_non_numeric_rejected(self, admin_token, seller_user_id):
        r = requests.put(
            f"{API}/admin/users/{seller_user_id}",
            json={"resell_markup_override": "abc"},
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=15,
        )
        assert r.status_code == 400, r.text


# ---------- non-admin auth guard ----------

class TestAdminAuthGuard:
    def test_non_admin_forbidden(self, seller_token, seller_user_id):
        r = requests.put(
            f"{API}/admin/users/{seller_user_id}",
            json={"resell_markup_override": 5},
            headers={"Authorization": f"Bearer {seller_token}"},
            timeout=15,
        )
        assert r.status_code == 403, r.text
