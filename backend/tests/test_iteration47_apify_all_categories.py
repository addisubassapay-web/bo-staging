"""Iteration 47 backend tests — Apify all-categories config expansion + endpoints sanity.
Covers: CATEGORY_URLS length=50, per-slug coverage>=3, default target_count=30000,
module import (no syntax errors), and endpoint health for
/api/products, /api/categories, /api/listings, /api/auth/login,
/api/admin/products/import-from-listings, /api/admin/sync/status.
"""
import os
import sys
import importlib
from collections import Counter

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # frontend .env is source of truth for the public URL
    from pathlib import Path
    for line in Path("/app/frontend/.env").read_text().splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
            break

ADMIN = {"email": "admin@mercari.local", "password": "admin123"}
CANONICAL_SLUGS = {"women", "men", "kids", "electronics", "home", "beauty",
                   "sports", "toys", "books", "handmade"}

sys.path.insert(0, "/app/backend")


# ── Config sanity: module import + CATEGORY_URLS + target_count default ─────
class TestApifyConfig:
    def test_module_imports_no_syntax_error(self):
        mod = importlib.import_module("apify_sync")
        importlib.reload(mod)
        assert hasattr(mod, "CATEGORY_URLS")
        assert hasattr(mod, "import_from_apify")

    def test_category_urls_length_50(self):
        import apify_sync
        assert len(apify_sync.CATEGORY_URLS) == 50, \
            f"Expected 50 CATEGORY_URLS, got {len(apify_sync.CATEGORY_URLS)}"

    def test_each_canonical_slug_at_least_3_urls(self):
        import apify_sync
        counts = Counter(slug for slug, _url in apify_sync.CATEGORY_URLS)
        for slug in CANONICAL_SLUGS:
            assert counts.get(slug, 0) >= 3, \
                f"Slug '{slug}' has only {counts.get(slug, 0)} URLs (<3)"

    def test_default_target_count_is_30000(self):
        import inspect
        import apify_sync
        sig = inspect.signature(apify_sync.import_from_apify)
        assert sig.parameters["target_count"].default == 30000


# ── Endpoint health ──────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN, timeout=30)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text[:200]}"
    data = r.json()
    tok = data.get("token") or data.get("access_token")
    assert tok, f"no token in login response: {data}"
    return tok


class TestPublicEndpoints:
    def test_auth_login_admin(self):
        r = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d.get("token") or d.get("access_token")

    def test_products_endpoint(self):
        r = requests.get(f"{BASE_URL}/api/products?page=1&page_size=5", timeout=30)
        assert r.status_code == 200, r.text[:200]
        d = r.json()
        assert "items" in d and isinstance(d["items"], list)
        # total should be >= 165 per iteration 46
        total = d.get("total", 0)
        assert total >= 165, f"products total {total} < 165 (regression?)"

    def test_categories_ten_canonical(self):
        r = requests.get(f"{BASE_URL}/api/categories", timeout=30)
        assert r.status_code == 200
        cats = r.json()
        if isinstance(cats, dict):
            cats = cats.get("items") or cats.get("categories") or []
        slugs = {c.get("slug") for c in cats}
        assert slugs == CANONICAL_SLUGS, f"categories slugs mismatch: {slugs}"

    def test_listings_endpoint(self):
        r = requests.get(f"{BASE_URL}/api/listings?limit=10", timeout=30)
        assert r.status_code == 200, r.text[:200]
        d = r.json()
        items = d.get("items") if isinstance(d, dict) else d
        assert isinstance(items, list) and len(items) >= 1


class TestAdminEndpoints:
    def test_sync_status(self, admin_token):
        r = requests.get(
            f"{BASE_URL}/api/admin/sync/status",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=30,
        )
        assert r.status_code == 200, r.text[:200]
        d = r.json()
        assert d.get("sync_running") is False

    def test_import_from_listings_bridge_still_works(self, admin_token):
        r = requests.post(
            f"{BASE_URL}/api/admin/products/import-from-listings",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=120,
        )
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        # idempotent: created may be 0 on re-run, but response should carry counts
        assert any(k in d for k in ("created", "updated", "total", "ok"))
