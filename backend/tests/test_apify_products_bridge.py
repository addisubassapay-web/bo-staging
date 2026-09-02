"""
Iteration 46 backend tests:
- Apify listings → permanent products bridge
- Idempotency
- Auth guards on admin import endpoint
- MongoDB products collection has no TTL
- Webhook still works
- Category & listings sanity
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://bo-staging.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@mercari.local"
ADMIN_PASSWORD = "admin123"
USER_EMAIL = "sophia_style@demo.local"
USER_PASSWORD = "demo1234"
WEBHOOK_SECRET = "mg-webhook-4f9c2b8e13a04d76b8b7c9e5f2a1d8e6"

CANONICAL_CATEGORIES = {"women", "men", "kids", "electronics", "home",
                        "beauty", "sports", "toys", "books", "handmade",
                        "computer"}


# ---------- Fixtures ----------
@pytest.fixture(scope="session")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _login(session, email, password):
    r = session.post(f"{API}/auth/login", json={"email": email, "password": password})
    if r.status_code != 200:
        pytest.skip(f"Login failed for {email}: {r.status_code} {r.text[:200]}")
    return r.json().get("access_token") or r.json().get("token")


@pytest.fixture(scope="session")
def admin_token(session):
    return _login(session, ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture(scope="session")
def user_token(session):
    return _login(session, USER_EMAIL, USER_PASSWORD)


# ---------- SANITY (DB regression check) ----------
def test_categories_are_canonical_ten(session):
    r = session.get(f"{API}/categories")
    assert r.status_code == 200, r.text
    data = r.json()
    items = data if isinstance(data, list) else data.get("items", data.get("categories", []))
    slugs = {c.get("slug") for c in items}
    assert slugs == CANONICAL_CATEGORIES, f"Expected canonical 10, got {slugs}"


def test_listings_default_page_not_empty(session):
    r = session.get(f"{API}/listings")
    assert r.status_code == 200, r.text
    data = r.json()
    if isinstance(data, list):
        items = data
        total = len(items)
    else:
        items = data.get("items", [])
        total = data.get("total", len(items))
    assert len(items) > 0 or total > 0, "Listings empty — DB_NAME regression?"


def test_products_has_data_no_db_regression(session):
    r = session.get(f"{API}/products?page=1&page_size=1")
    assert r.status_code == 200, r.text
    data = r.json()
    total = data.get("total", 0)
    assert total > 0, f"DB_NAME REGRESSION: products total=0 ({data})"


# ---------- BRIDGE: 165+ products ----------
def test_products_bridge_has_165_plus(session):
    r = session.get(f"{API}/products?page=1&page_size=100")
    assert r.status_code == 200, r.text
    data = r.json()
    total = data.get("total", 0)
    items = data.get("items", [])
    assert total >= 165, f"Expected >=165 products, got {total}"
    assert len(items) > 0
    # Every sampled item has non-null sku
    for it in items[:20]:
        assert it.get("sku"), f"Product missing sku: {it.get('id')} - {it.get('title')}"


# ---------- IDEMPOTENCY ----------
def test_import_from_listings_idempotent(session, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    # First run
    r1 = session.post(f"{API}/admin/products/import-from-listings",
                      json={"only_apify": True}, headers=headers)
    assert r1.status_code == 200, r1.text
    j1 = r1.json()
    total1 = j1.get("total_products_in_catalog")
    assert total1 is not None, j1

    # Second run — should create 0, total constant
    r2 = session.post(f"{API}/admin/products/import-from-listings",
                      json={"only_apify": True}, headers=headers)
    assert r2.status_code == 200, r2.text
    j2 = r2.json()
    assert j2.get("created", -1) == 0, f"Second run created={j2.get('created')} (expected 0). {j2}"
    total2 = j2.get("total_products_in_catalog")
    assert total2 == total1, f"Total changed across runs: {total1} -> {total2}"


# ---------- AUTH ----------
def test_import_endpoint_requires_auth(session):
    # Use a fresh session (no auth headers)
    r = requests.post(f"{API}/admin/products/import-from-listings",
                      json={"only_apify": True})
    assert r.status_code in (401, 403), f"Unauthed got {r.status_code}: {r.text[:200]}"


def test_import_endpoint_forbidden_for_non_admin(session, user_token):
    headers = {"Authorization": f"Bearer {user_token}"}
    r = requests.post(f"{API}/admin/products/import-from-listings",
                      json={"only_apify": True}, headers=headers)
    assert r.status_code == 403, f"Non-admin got {r.status_code}: {r.text[:200]}"


# ---------- PERMANENCE: no TTL ----------
def test_products_collection_no_ttl():
    from pymongo import MongoClient
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
    client = MongoClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    indexes = list(db.products.list_indexes())
    ttl = [i for i in indexes if "expireAfterSeconds" in i]
    assert not ttl, f"Products has TTL indexes: {ttl}"


# ---------- SINGLE PRODUCT ----------
REQUIRED_FIELDS = {"id", "title", "description", "price", "currency",
                   "images", "category", "sku", "source_url", "created_at", "is_active"}


def test_single_product_returns_required_fields(session):
    r = session.get(f"{API}/products?page=1&page_size=1")
    assert r.status_code == 200
    items = r.json().get("items", [])
    assert items, "No products to sample"
    pid = items[0]["id"]
    r2 = session.get(f"{API}/products/{pid}")
    assert r2.status_code == 200, r2.text
    p = r2.json()
    missing = REQUIRED_FIELDS - set(p.keys())
    assert not missing, f"Missing required fields: {missing}. Got keys: {list(p.keys())}"


def test_invalid_product_returns_404(session):
    r = session.get(f"{API}/products/xxx-fake")
    assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text[:200]}"


# ---------- WEBHOOK ----------
def test_apify_webhook_still_works():
    payload = {"items": [{"asin": "B0RETEST", "title": "Retest",
                          "price": 9.99, "url": "https://amazon.com/dp/B0RETEST"}]}
    r = requests.post(f"{API}/webhooks/apify-import",
                      headers={"X-Webhook-Secret": WEBHOOK_SECRET,
                               "Content-Type": "application/json"},
                      json=payload)
    assert r.status_code == 200, f"{r.status_code}: {r.text[:300]}"
    j = r.json()
    assert ("created" in j) or ("updated" in j), f"Response missing created/updated: {j}"
