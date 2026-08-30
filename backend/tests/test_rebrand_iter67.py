"""Rebrand regression: admin login + categories endpoint still healthy."""
import os
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or \
    open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split()[0].rstrip("/")


def test_admin_login_still_works():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "admin@mercari.local", "password": "admin123"},
        timeout=30,
    )
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text[:200]}"
    data = r.json()
    # Token may be in body OR set as httpOnly cookie
    assert "token" in data or "access_token" in data or r.cookies, \
        f"No token or cookie found: {data}"


def test_categories_endpoint_healthy():
    r = requests.get(f"{BASE_URL}/api/categories", timeout=30)
    assert r.status_code == 200, f"Categories failed: {r.status_code}"
    body = r.json()
    assert isinstance(body, (list, dict))


def test_no_mercari_in_served_html():
    r = requests.get(f"{BASE_URL}/", timeout=30)
    assert r.status_code == 200
    # Only checking static HTML shell
    assert "Mercari" not in r.text, "Found 'Mercari' in served index.html"
    assert "Ocean" in r.text


def test_manifest_ocean_branded():
    r = requests.get(f"{BASE_URL}/manifest.json", timeout=30)
    assert r.status_code == 200
    data = r.json()
    assert data.get("short_name", "").startswith("Ocean")
    assert data.get("name", "").startswith("Ocean")
