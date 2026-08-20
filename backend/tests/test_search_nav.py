"""Backend tests for new nav+search endpoints (Mercuri-global clone)."""
import os
import pytest
import requests
from pathlib import Path

def _load_backend_url():
    url = os.environ.get("REACT_APP_BACKEND_URL")
    if url:
        return url.rstrip("/")
    env = Path("/app/frontend/.env")
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL not set")

BASE_URL = _load_backend_url()


@pytest.fixture(scope="module")
def s():
    return requests.Session()


class TestCategories:
    def test_categories_returns_21(self, s):
        r = s.get(f"{BASE_URL}/api/categories", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) >= 21, f"Expected >=21 categories, got {len(data)}"
        slugs = {c["slug"] for c in data}
        for expected in [
            "shoes", "bags-accessories", "jewelry-watches", "pet-supplies",
            "automotive", "garden-outdoor", "musical-instruments",
            "office-craft", "collectibles",
        ]:
            assert expected in slugs, f"Missing category slug: {expected}"


class TestSearchSuggest:
    def test_suggest_returns_structure(self, s):
        r = s.get(f"{BASE_URL}/api/search/suggest", params={"q": "watch"}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        for key in ("items", "queries", "brands", "categories"):
            assert key in d, f"Missing key {key} in suggest response"
            assert isinstance(d[key], list)

    def test_suggest_short_query_empty(self, s):
        r = s.get(f"{BASE_URL}/api/search/suggest", params={"q": "a"}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["items"] == [] and d["queries"] == []


class TestSearchFacets:
    def test_facets_returns_structure(self, s):
        r = s.get(f"{BASE_URL}/api/search/facets", params={"q": "watch"}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        for key in ("brands", "conditions", "price", "total"):
            assert key in d
        assert isinstance(d["brands"], list)
        assert isinstance(d["conditions"], list)
        assert isinstance(d["price"], dict) and "min" in d["price"] and "max" in d["price"]
        assert isinstance(d["total"], int)


class TestSearchTrending:
    def test_trending_returns_list(self, s):
        r = s.get(f"{BASE_URL}/api/search/trending", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "trending" in d
        assert isinstance(d["trending"], list)


class TestListingsBrandFilter:
    def test_listings_filter_by_brand(self, s):
        # Discover a real brand from trending or listings first
        r_list = s.get(f"{BASE_URL}/api/listings", params={"limit": 20}, timeout=15)
        assert r_list.status_code == 200
        listings = r_list.json()
        brand = None
        for l in listings:
            if l.get("brand"):
                brand = l["brand"]
                break
        if not brand:
            pytest.skip("No listings with brand present")
        r = s.get(f"{BASE_URL}/api/listings", params={"brand": brand, "limit": 5}, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        for item in data:
            assert item.get("brand") == brand, f"Brand filter leaked: {item.get('brand')} != {brand}"
