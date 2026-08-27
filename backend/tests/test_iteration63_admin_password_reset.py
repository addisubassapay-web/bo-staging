"""Tests for admin password reset escape hatch (iteration 63).

Endpoint: POST /api/admin/users/{user_id}/reset-password
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL must be set"

ADMIN_EMAIL = "admin@mercari.local"
ADMIN_PASSWORD = "admin123"
SOPHIA_EMAIL = "sophia_style@demo.local"
SOPHIA_ORIG_PASSWORD = "demo1234"

BROKEN_HASH_EMAILS = [
    "hansenayda@gmail.com",
    "stmobilest2027@gmail.com",
    "maham89706@gmail.com",
]


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
def sophia_user(admin_token):
    r = requests.get(
        f"{BASE_URL}/api/admin/users",
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=20,
    )
    assert r.status_code == 200
    users = r.json()
    match = [u for u in users if u.get("email") == SOPHIA_EMAIL]
    assert match, "sophia_style@demo.local not found in /admin/users"
    return match[0]


@pytest.fixture(scope="module")
def non_admin_token():
    # urban_finds is a documented demo user; if its login also drifted, try tech_haven
    for u in ("urban_finds", "vintage_maven", "tech_haven", "cozy_home"):
        r = _login(f"{u}@demo.local", "demo1234")
        if r.status_code == 200:
            return r.json()["token"]
    pytest.skip("No non-admin demo user login working")


def _reset(admin_token, user_id, new_password):
    return requests.post(
        f"{BASE_URL}/api/admin/users/{user_id}/reset-password",
        json={"new_password": new_password},
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=20,
    )


# --- Positive path: reset then login ---
def test_reset_password_and_relogin(admin_token, sophia_user):
    new_pwd = "Welcome-2026"
    r = _reset(admin_token, sophia_user["id"], new_pwd)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["email"] == SOPHIA_EMAIL
    assert body.get("username")

    # Immediate login with new password
    l = _login(SOPHIA_EMAIL, new_pwd)
    assert l.status_code == 200, l.text
    assert "token" in l.json()

    # Old password must fail (single attempt only to avoid lock)
    old = _login(SOPHIA_EMAIL, SOPHIA_ORIG_PASSWORD)
    assert old.status_code == 401


def test_failed_attempts_cleared_after_reset(admin_token, sophia_user):
    # Do a fresh reset so we're checking state IMMEDIATELY after admin reset
    r = _reset(admin_token, sophia_user["id"], "FreshPwd-2026")
    assert r.status_code == 200
    # After reset, /admin/users record shows counters cleared
    r = requests.get(
        f"{BASE_URL}/api/admin/users",
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=20,
    )
    u = next(x for x in r.json() if x["id"] == sophia_user["id"])
    assert u.get("failed_login_attempts", 0) == 0
    assert not u.get("locked_until")


# --- Validation ---
def test_short_password_rejected(admin_token, sophia_user):
    r = _reset(admin_token, sophia_user["id"], "abc")
    assert r.status_code == 400


def test_unknown_user_404(admin_token):
    r = _reset(admin_token, "nonexistent-user-id-xyz", "Welcome-2026")
    assert r.status_code == 404


# --- Auth checks ---
def test_non_admin_forbidden(non_admin_token, sophia_user):
    r = requests.post(
        f"{BASE_URL}/api/admin/users/{sophia_user['id']}/reset-password",
        json={"new_password": "Welcome-2026"},
        headers={"Authorization": f"Bearer {non_admin_token}"},
        timeout=20,
    )
    assert r.status_code == 403


def test_missing_jwt_401(sophia_user):
    r = requests.post(
        f"{BASE_URL}/api/admin/users/{sophia_user['id']}/reset-password",
        json={"new_password": "Welcome-2026"},
        timeout=20,
    )
    assert r.status_code in (401, 403)


def test_invalid_jwt_401(sophia_user):
    r = requests.post(
        f"{BASE_URL}/api/admin/users/{sophia_user['id']}/reset-password",
        json={"new_password": "Welcome-2026"},
        headers={"Authorization": "Bearer garbage.token.here"},
        timeout=20,
    )
    assert r.status_code == 401


# --- Backwards compatibility (admin login still works) ---
def test_admin_login_still_works():
    r = _login(ADMIN_EMAIL, ADMIN_PASSWORD)
    assert r.status_code == 200


# --- Empty-hash users: 401 not 500 ---
def test_empty_hash_users_return_401():
    for email in BROKEN_HASH_EMAILS:
        r = _login(email, "any-password-here")
        assert r.status_code == 401, f"{email}: got {r.status_code} — must be 401, not 500. Body={r.text[:200]}"


def test_empty_hash_user_can_login_after_admin_reset(admin_token):
    # Reset first broken user, log in, then restore empty hash via a second reset
    # to something they don't know (we can't truly restore empty hash without DB access,
    # so we just verify the login works and note this in the report).
    r = requests.get(
        f"{BASE_URL}/api/admin/users",
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=20,
    )
    users = r.json()
    target = next((u for u in users if u.get("email") == BROKEN_HASH_EMAILS[0]), None)
    if not target:
        pytest.skip(f"{BROKEN_HASH_EMAILS[0]} not in DB")
    new_pwd = "TempReset-2026!"
    rr = _reset(admin_token, target["id"], new_pwd)
    assert rr.status_code == 200, rr.text
    l = _login(BROKEN_HASH_EMAILS[0], new_pwd)
    assert l.status_code == 200, l.text


# --- Restore sophia at end of module ---
def test_zzz_restore_sophia_password(admin_token, sophia_user):
    r = _reset(admin_token, sophia_user["id"], SOPHIA_ORIG_PASSWORD)
    assert r.status_code == 200
    l = _login(SOPHIA_EMAIL, SOPHIA_ORIG_PASSWORD)
    assert l.status_code == 200
