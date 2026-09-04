"""Verify /api/admin/seller-applications no longer returns 502."""
import os
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://bo-staging.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "admin@mercari.local"
ADMIN_PASSWORD = "admin123"


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:300]}"
    data = r.json()
    token = data.get("access_token") or data.get("token")
    assert token, f"no token in login response: {data}"
    return token


@pytest.fixture(scope="module")
def headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


def _is_real_user_row(row):
    # Look for email field in any nested user object
    email = (row.get("email") or
             (row.get("user") or {}).get("email") or
             row.get("applicant_email") or "")
    email = (email or "").lower()
    if not email:
        return False
    if email.startswith(("test_iter", "case_", "e2e_", "test_", "seed_")):
        return False
    return True


def test_seller_applications_10_consecutive(headers):
    """10 back-to-back calls should all return 200."""
    statuses = []
    for i in range(10):
        r = requests.get(f"{BASE_URL}/api/admin/seller-applications", headers=headers, timeout=30)
        statuses.append(r.status_code)
    assert all(s == 200 for s in statuses), f"Non-200 responses: {statuses}"


def test_seller_applications_returns_list(headers):
    r = requests.get(f"{BASE_URL}/api/admin/seller-applications", headers=headers, timeout=30)
    assert r.status_code == 200
    data = r.json()
    # Could be either list or {items:[]}
    items = data if isinstance(data, list) else data.get("items") or data.get("applications") or []
    assert isinstance(items, list), f"Expected list, got {type(data)}: {str(data)[:200]}"


@pytest.mark.parametrize("status", ["pending", "approved", "rejected"])
def test_seller_applications_status_filter(headers, status):
    r = requests.get(f"{BASE_URL}/api/admin/seller-applications",
                     params={"status_filter": status}, headers=headers, timeout=30)
    assert r.status_code == 200, f"status={status} -> {r.status_code}: {r.text[:200]}"
    data = r.json()
    items = data if isinstance(data, list) else data.get("items") or data.get("applications") or []
    assert isinstance(items, list)


def test_seller_applications_real_users_first(headers):
    r = requests.get(f"{BASE_URL}/api/admin/seller-applications", headers=headers, timeout=30)
    assert r.status_code == 200
    data = r.json()
    items = data if isinstance(data, list) else data.get("items") or data.get("applications") or []
    if len(items) < 2:
        pytest.skip("not enough rows to verify ordering")

    # find index of first real user and first fixture user
    first_real = None
    first_fixture = None
    for i, row in enumerate(items):
        if _is_real_user_row(row) and first_real is None:
            first_real = i
        elif not _is_real_user_row(row) and first_fixture is None:
            first_fixture = i
    print(f"real users total: {sum(1 for r in items if _is_real_user_row(r))}/{len(items)}; first_real={first_real}, first_fixture={first_fixture}")
    if first_real is not None and first_fixture is not None:
        assert first_real < first_fixture, "real users should be sorted before fixture rows"


# Regression: other admin endpoints still 200
@pytest.mark.parametrize("path", [
    "/api/admin/users",
    "/api/admin/users?real_only=1",
    "/api/admin/stores",
    "/api/admin/stores?real_only=1",
    "/api/admin/orders",
    "/api/admin/orders?real_only=1",
])
def test_admin_regression_endpoints(headers, path):
    r = requests.get(f"{BASE_URL}{path}", headers=headers, timeout=30)
    assert r.status_code == 200, f"{path} -> {r.status_code}: {r.text[:200]}"
