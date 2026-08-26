"""Iteration 61 regression tests:
- Rebrand (Mercari-Global -> Mercarie-Global)
- MongoDB Atlas password rotation (admin login still works)
- New seller_country field on products + listings
- New categories/subcategories (Computer > Laptop)
- New admin apify import endpoint /api/admin/apify/runs/{run_id}/import
"""
import os
import re
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://marketplace-dropship.preview.emergentagent.com").rstrip("/")

# Read from frontend .env if os env not set
if "preview.emergentagent" not in BASE_URL:
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
    except Exception:
        pass

ADMIN_EMAIL = "admin@mercari.local"
ADMIN_PASSWORD = "admin123"


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text[:200]}"
    tok = r.json().get("access_token") or r.json().get("token")
    assert tok, f"no token in response: {r.json()}"
    return tok


@pytest.fixture(scope="module")
def demo_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": "sophia_style@demo.local", "password": "demo1234"}, timeout=30)
    if r.status_code != 200:
        pytest.skip(f"demo login unavailable: {r.status_code}")
    return r.json().get("access_token") or r.json().get("token")


# --- Rebrand ---
def test_rebrand_index_html():
    r = requests.get(f"{BASE_URL}/", timeout=30)
    assert r.status_code == 200
    html = r.text
    # <title> should include Mercarie-Global and NOT Mercari-Global (with hyphen but no "e")
    m = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    assert m, "no <title> tag"
    title = m.group(1)
    assert "Mercarie-Global" in title, f"Expected 'Mercarie-Global' in title: {title!r}"
    # ensure the old brand hyphenated form isn't there
    assert "Mercari-Global" not in title.replace("Mercarie-Global", ""), f"Old brand still in title: {title!r}"


def test_rebrand_manifest():
    r = requests.get(f"{BASE_URL}/manifest.json", timeout=30)
    assert r.status_code == 200
    body = r.text
    assert "Mercarie-Global" in body, f"manifest.json missing new brand: {body[:300]}"


# --- Admin auth (post rotation) ---
def test_admin_login_works(admin_token):
    assert isinstance(admin_token, str) and len(admin_token) > 10


# --- Categories / subcategories ---
def test_categories_include_computer():
    r = requests.get(f"{BASE_URL}/api/products/categories", timeout=30)
    assert r.status_code == 200
    data = r.json()
    items = data if isinstance(data, list) else data.get("categories") or data.get("items") or []
    assert len(items) >= 11, f"expected >=11 categories, got {len(items)}: {items}"
    computer = [c for c in items if (c.get("name") or c.get("category") or c.get("_id")) == "Computer"]
    assert computer, f"Computer not found in {items}"
    count = computer[0].get("count") or computer[0].get("total") or 0
    assert count > 0, f"Computer count not >0: {computer[0]}"


def test_subcategories_computer_includes_laptop():
    r = requests.get(f"{BASE_URL}/api/products/subcategories?category=Computer", timeout=30)
    assert r.status_code == 200
    data = r.json()
    items = data if isinstance(data, list) else data.get("subcategories") or data.get("items") or []
    laptop = [s for s in items if (s.get("name") or s.get("subcategory") or s.get("_id")) == "Laptop"]
    assert laptop, f"Laptop not found in {items}"
    count = laptop[0].get("count") or laptop[0].get("total") or 0
    assert count > 0, f"Laptop count not >0: {laptop[0]}"


# --- Products with seller_country ---
def test_products_computer_laptop_has_seller_country():
    r = requests.get(f"{BASE_URL}/api/products",
                     params={"category": "Computer", "subcategory": "Laptop", "limit": 3}, timeout=30)
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    total = data.get("total") if isinstance(data, dict) else None
    items = data.get("items") if isinstance(data, dict) else data
    assert items, f"no items returned: {data}"
    assert total is None or total >= 300, f"expected total >=300, got {total}"
    for p in items:
        sc = p.get("seller_country")
        assert sc, f"missing seller_country in product: {p}"


# --- Listings with seller_country ---
def test_listings_has_seller_country():
    r = requests.get(f"{BASE_URL}/api/listings?limit=1", timeout=30)
    assert r.status_code == 200
    data = r.json()
    items = data.get("items") if isinstance(data, dict) else data
    assert items, f"no listings: {data}"
    l = items[0]
    assert "seller_country" in l, f"seller_country field missing in listing: {list(l.keys())}"


# --- Admin apify import endpoint ---
def test_apify_import_requires_admin(demo_token):
    r = requests.post(
        f"{BASE_URL}/api/admin/apify/runs/nonexistent_run_xyz/import",
        params={"category": "Computer", "subcategory": "Laptop"},
        headers={"Authorization": f"Bearer {demo_token}"},
        timeout=30,
    )
    assert r.status_code == 403, f"expected 403 for non-admin, got {r.status_code}: {r.text[:200]}"


def test_apify_import_missing_run_returns_404(admin_token):
    r = requests.post(
        f"{BASE_URL}/api/admin/apify/runs/definitely_not_a_real_run_id_zzz/import",
        params={"category": "Computer", "subcategory": "Laptop"},
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=60,
    )
    assert r.status_code == 404, f"expected 404 for missing run, got {r.status_code}: {r.text[:300]}"


def test_apify_import_no_auth():
    r = requests.post(
        f"{BASE_URL}/api/admin/apify/runs/x/import",
        params={"category": "Computer", "subcategory": "Laptop"},
        timeout=30,
    )
    assert r.status_code in (401, 403), f"expected 401/403 without auth, got {r.status_code}"
