"""Tests for force_degraded health simulator endpoints.

Covers:
- GET /api/health?force_degraded=1 (single-shot query param)
- GET /api/health (baseline)
- POST /api/admin/health/force-degraded (admin flip global timer)
- GET /api/admin/health/force-degraded (state read)
- 0-duration clear + cap at 3600s
- Auth (401/403 for non-admin)
- Regression on admin listing endpoints
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL must be set"

ADMIN_EMAIL = "admin@mercari.local"
ADMIN_PASSWORD = "admin123"


def _login(email, password):
    return requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
        timeout=20,
    )


@pytest.fixture(scope="module")
def admin_token():
    r = _login(ADMIN_EMAIL, ADMIN_PASSWORD)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(autouse=True)
def _cleanup_state(admin_headers):
    """Always clear force-degraded state before AND after every test to avoid
    leaving the pod paging Slack after the run finishes."""
    requests.post(
        f"{BASE_URL}/api/admin/health/force-degraded",
        headers=admin_headers,
        json={"duration_sec": 0},
        timeout=20,
    )
    yield
    requests.post(
        f"{BASE_URL}/api/admin/health/force-degraded",
        headers=admin_headers,
        json={"duration_sec": 0},
        timeout=20,
    )


# --- Baseline ---------------------------------------------------------------

def test_health_baseline_ok():
    r = requests.get(f"{BASE_URL}/api/health", timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "ok", f"expected ok, got {data}"
    assert data["uptime"] > 0
    assert data["db"]["ok"] is True
    assert isinstance(data["mailer"]["breaker_open"], bool)
    assert "simulated_degraded" not in data


# --- Query-param single-shot ------------------------------------------------

def test_health_force_degraded_query_param_single_shot():
    r = requests.get(f"{BASE_URL}/api/health?force_degraded=1", timeout=20)
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "degraded"
    assert data["db"]["ok"] is True  # real DB should still succeed
    assert data["mailer"]["breaker_open"] is False
    assert data.get("simulated_degraded", {}).get("active") is True
    assert "force_degraded" in data["simulated_degraded"]["reason"].lower() or \
           "query" in data["simulated_degraded"]["reason"].lower()

    # Next unqualified call must be ok — no persistence
    r2 = requests.get(f"{BASE_URL}/api/health", timeout=20)
    assert r2.status_code == 200
    data2 = r2.json()
    assert data2["status"] == "ok", f"query-param leaked state: {data2}"
    assert "simulated_degraded" not in data2


# --- Admin endpoint: auth ---------------------------------------------------

def test_admin_force_degraded_requires_auth():
    r = requests.post(
        f"{BASE_URL}/api/admin/health/force-degraded",
        json={"duration_sec": 60, "reason": "unauth-test"},
        timeout=20,
    )
    assert r.status_code in (401, 403), f"unauth request should be rejected, got {r.status_code}"


def test_admin_force_degraded_state_requires_auth():
    r = requests.get(
        f"{BASE_URL}/api/admin/health/force-degraded",
        timeout=20,
    )
    assert r.status_code in (401, 403)


# --- Admin flip: sets state, health reflects it, then clear -----------------

def test_admin_force_degraded_flow(admin_headers):
    # Flip on
    r = requests.post(
        f"{BASE_URL}/api/admin/health/force-degraded",
        headers=admin_headers,
        json={"duration_sec": 60, "reason": "test"},
        timeout=20,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["seconds_left"] == 60
    assert body["reason"] == "test"

    # Health reflects degraded
    hr = requests.get(f"{BASE_URL}/api/health", timeout=20)
    assert hr.status_code == 200
    hdata = hr.json()
    assert hdata["status"] == "degraded"
    sim = hdata.get("simulated_degraded", {})
    assert sim.get("active") is True
    assert sim.get("seconds_left", 0) > 0

    # State endpoint reflects it
    sr = requests.get(
        f"{BASE_URL}/api/admin/health/force-degraded",
        headers=admin_headers,
        timeout=20,
    )
    assert sr.status_code == 200
    sdata = sr.json()
    assert sdata["active"] is True
    assert sdata["seconds_left"] > 0
    assert sdata["reason"] == "test"

    # Clear with duration 0
    cr = requests.post(
        f"{BASE_URL}/api/admin/health/force-degraded",
        headers=admin_headers,
        json={"duration_sec": 0},
        timeout=20,
    )
    assert cr.status_code == 200
    cbody = cr.json()
    assert cbody["ok"] is True
    assert cbody.get("cleared") is True

    # Health back to ok
    hr2 = requests.get(f"{BASE_URL}/api/health", timeout=20)
    hdata2 = hr2.json()
    assert hdata2["status"] == "ok"
    assert "simulated_degraded" not in hdata2


# --- Cap at 3600s -----------------------------------------------------------

def test_admin_force_degraded_caps_at_3600(admin_headers):
    r = requests.post(
        f"{BASE_URL}/api/admin/health/force-degraded",
        headers=admin_headers,
        json={"duration_sec": 999999, "reason": "cap-test"},
        timeout=20,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["seconds_left"] <= 3600, f"cap not applied: {body}"
    assert body["seconds_left"] == 3600


# --- Regression: other admin endpoints still 200 ----------------------------

@pytest.mark.parametrize("path", [
    "/api/admin/users",
    "/api/admin/stores",
    "/api/admin/orders",
    "/api/admin/seller-applications",
])
def test_admin_endpoints_regression(admin_headers, path):
    r = requests.get(f"{BASE_URL}{path}", headers=admin_headers, timeout=30)
    assert r.status_code == 200, f"{path} -> {r.status_code} {r.text[:200]}"
