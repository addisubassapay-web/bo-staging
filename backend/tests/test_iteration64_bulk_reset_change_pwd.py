"""Iteration 64: bulk password reset + force-change-password flow.

Covers:
- Legacy 3 users can now log in with Welcome-2026 (post live migration)
- Login returns password_change_required flag
- POST /auth/change-password with & without must_change_password
- POST /admin/users/bulk-password-reset validation + auth guards
- Sophia restore at the end
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL

ADMIN = ("admin@mercari.local", "admin123")
LEGACY_EMAILS = [
    "hansenayda@gmail.com",
    "stmobilest2027@gmail.com",
    "maham89706@gmail.com",
]
LIVE_TEMP = "Welcome-2026"
SOPHIA = "sophia_style@demo.local"


def _login(email, password):
    return requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
        timeout=20,
    )


@pytest.fixture(scope="module")
def admin_token():
    r = _login(*ADMIN)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("password_change_required") is False, "admin should NOT be flagged"
    return body["token"]


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# --- 1. Legacy users login with live temp ---
@pytest.mark.parametrize("email", LEGACY_EMAILS)
def test_legacy_user_login_with_welcome_2026(email):
    r = _login(email, LIVE_TEMP)
    assert r.status_code == 200, f"{email}: {r.status_code} {r.text[:200]}"
    body = r.json()
    assert body.get("token")
    assert body.get("password_change_required") is True, (
        f"{email}: password_change_required must be True, got {body}"
    )


# --- 2. Sophia login post-migration ---
def test_sophia_login_with_welcome_2026():
    r = _login(SOPHIA, LIVE_TEMP)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["password_change_required"] is True


def test_sophia_original_demo1234_rejected():
    r = _login(SOPHIA, "demo1234")
    assert r.status_code == 401, f"Expected 401 for stale demo1234, got {r.status_code}"


# --- 3. Admin login untouched ---
def test_admin_login_no_change_required():
    r = _login(*ADMIN)
    assert r.status_code == 200
    assert r.json().get("password_change_required") is False


# --- 4. /auth/me exposes must_change_password ---
def test_me_exposes_must_change_password_flag():
    r = _login(LEGACY_EMAILS[0], LIVE_TEMP)
    assert r.status_code == 200
    tok = r.json()["token"]
    m = requests.get(
        f"{BASE_URL}/api/auth/me",
        headers={"Authorization": f"Bearer {tok}"},
        timeout=20,
    )
    assert m.status_code == 200
    body = m.json()
    # Could be user payload directly or nested; accept either.
    payload = body.get("user") if isinstance(body, dict) and "user" in body else body
    assert payload.get("must_change_password") is True, f"me payload: {body}"


# --- 5. change-password flow for must_change=True user ---
def test_change_password_with_flag_no_old_password_required():
    # Use legacy #2 to avoid interfering with #0 in another test
    email = LEGACY_EMAILS[1]
    r = _login(email, LIVE_TEMP)
    assert r.status_code == 200
    tok = r.json()["token"]
    new_pwd = "MyNewPass123"

    cp = requests.post(
        f"{BASE_URL}/api/auth/change-password",
        json={"new_password": new_pwd},
        headers={"Authorization": f"Bearer {tok}"},
        timeout=20,
    )
    assert cp.status_code == 200, cp.text
    assert cp.json().get("ok") is True

    # Flag cleared: relogin returns password_change_required=False
    r2 = _login(email, new_pwd)
    assert r2.status_code == 200, r2.text
    assert r2.json().get("password_change_required") is False

    # Restore this user to LIVE_TEMP via new self change-password (flag now False, needs old)
    tok2 = r2.json()["token"]
    restore = requests.post(
        f"{BASE_URL}/api/auth/change-password",
        json={"old_password": new_pwd, "new_password": LIVE_TEMP},
        headers={"Authorization": f"Bearer {tok2}"},
        timeout=20,
    )
    assert restore.status_code == 200, restore.text


def test_change_password_requires_jwt():
    r = requests.post(
        f"{BASE_URL}/api/auth/change-password",
        json={"new_password": "Whatever123"},
        timeout=20,
    )
    assert r.status_code in (401, 403)


def test_change_password_short_pwd_400(admin_token):
    r = requests.post(
        f"{BASE_URL}/api/auth/change-password",
        json={"new_password": "abc"},
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=20,
    )
    assert r.status_code == 400


def test_change_password_admin_requires_old(admin_token):
    # Admin does NOT have must_change_password=True, so old_password required.
    # Omitting old_password -> 401
    r = requests.post(
        f"{BASE_URL}/api/auth/change-password",
        json={"new_password": "NewAdmin-2026"},
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=20,
    )
    assert r.status_code == 401, r.text

    # Wrong old_password -> 401
    r2 = requests.post(
        f"{BASE_URL}/api/auth/change-password",
        json={"old_password": "wrong", "new_password": "NewAdmin-2026"},
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=20,
    )
    assert r2.status_code == 401

    # Correct old_password -> 200 then rotate back
    ok = requests.post(
        f"{BASE_URL}/api/auth/change-password",
        json={"old_password": "admin123", "new_password": "admin-rotate-2026"},
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=20,
    )
    assert ok.status_code == 200, ok.text
    # Login with new works
    l = _login(ADMIN[0], "admin-rotate-2026")
    assert l.status_code == 200
    new_tok = l.json()["token"]
    # rotate back to admin123
    back = requests.post(
        f"{BASE_URL}/api/auth/change-password",
        json={"old_password": "admin-rotate-2026", "new_password": "admin123"},
        headers={"Authorization": f"Bearer {new_tok}"},
        timeout=20,
    )
    assert back.status_code == 200
    # Confirm admin123 restored
    assert _login(*ADMIN).status_code == 200


# --- 6. bulk-password-reset validation & auth ---
def test_bulk_reset_non_admin_403():
    # Get a fresh non-admin token — use legacy user (still Welcome-2026 for #0 & #2)
    r = _login(LEGACY_EMAILS[2], LIVE_TEMP)
    assert r.status_code == 200
    tok = r.json()["token"]
    b = requests.post(
        f"{BASE_URL}/api/admin/users/bulk-password-reset",
        json={"mode": "temp", "all_non_admin": True, "temp_password": "abcdef"},
        headers={"Authorization": f"Bearer {tok}"},
        timeout=30,
    )
    assert b.status_code == 403, f"expected 403, got {b.status_code} {b.text[:200]}"


def test_bulk_reset_unknown_mode_400(admin_headers):
    b = requests.post(
        f"{BASE_URL}/api/admin/users/bulk-password-reset",
        json={"mode": "banana", "all_non_admin": True, "temp_password": "abcdef"},
        headers=admin_headers,
        timeout=30,
    )
    assert b.status_code == 400


def test_bulk_reset_only_missing_hash(admin_headers):
    # After live migration, users with empty hash may be very few (system sellers).
    # Endpoint should still succeed, affected>=0.
    b = requests.post(
        f"{BASE_URL}/api/admin/users/bulk-password-reset",
        json={"mode": "temp", "only_missing_hash": True, "temp_password": "X-2026-Legacy"},
        headers=admin_headers,
        timeout=30,
    )
    assert b.status_code == 200, b.text
    body = b.json()
    assert body["ok"] is True
    assert body["mode"] == "temp"
    # Not making a strong lower-bound assertion — migration already touched
    # these users. Just record.
    print(f"only_missing_hash affected: {body.get('affected')}")


def test_bulk_reset_all_non_admin_and_sophia_can_login(admin_headers):
    rotate = "Rotate-2026"
    b = requests.post(
        f"{BASE_URL}/api/admin/users/bulk-password-reset",
        json={"mode": "temp", "all_non_admin": True, "temp_password": rotate},
        headers=admin_headers,
        timeout=60,
    )
    assert b.status_code == 200, b.text
    body = b.json()
    assert body["ok"] is True
    assert body["affected"] > 900, f"expected >900 affected, got {body.get('affected')}"
    assert body["temp_password"] == rotate

    # Login sophia with new temp
    time.sleep(0.5)
    l = _login(SOPHIA, rotate)
    assert l.status_code == 200, l.text
    assert l.json()["password_change_required"] is True

    # Admin still unaffected
    a = _login(*ADMIN)
    assert a.status_code == 200
    assert a.json()["password_change_required"] is False


# --- Restore live state: bulk-reset everyone back to Welcome-2026 ---
def test_zzz_restore_live_temp(admin_headers):
    b = requests.post(
        f"{BASE_URL}/api/admin/users/bulk-password-reset",
        json={"mode": "temp", "all_non_admin": True, "temp_password": LIVE_TEMP},
        headers=admin_headers,
        timeout=60,
    )
    assert b.status_code == 200, b.text
    # Verify sophia is on Welcome-2026 again
    l = _login(SOPHIA, LIVE_TEMP)
    assert l.status_code == 200
