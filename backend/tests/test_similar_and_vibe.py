"""Tests for new endpoints: /api/listings/{id}/similar and /api/search/vibe"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://mercari-global-clone-1.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def sample_listing():
    r = requests.get(f"{API}/listings", params={"limit": 5}, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    items = data if isinstance(data, list) else data.get("items") or data.get("listings") or []
    assert items, f"No listings returned: {data}"
    return items[0]


class TestSimilar:
    def test_similar_returns_list(self, sample_listing):
        lid = sample_listing["id"]
        r = requests.get(f"{API}/listings/{lid}/similar", timeout=30)
        assert r.status_code == 200, r.text
        arr = r.json()
        assert isinstance(arr, list)
        assert len(arr) <= 12
        # exclude self
        assert all(x["id"] != lid for x in arr)
        # same category
        cat = sample_listing.get("category_id")
        if cat and arr:
            same_cat = sum(1 for x in arr if x.get("category_id") == cat)
            assert same_cat == len(arr), "All similar items must share source category"

    def test_similar_404(self):
        r = requests.get(f"{API}/listings/nonexistent-xyz/similar", timeout=30)
        assert r.status_code == 404


class TestVibe:
    def test_vibe_short_rejected(self):
        r = requests.post(f"{API}/search/vibe", json={"vibe": "a", "limit": 4}, timeout=30)
        assert r.status_code == 400

    def test_vibe_cozy_minimalist(self):
        r = requests.post(f"{API}/search/vibe", json={"vibe": "cozy minimalist home", "limit": 8}, timeout=60)
        assert r.status_code == 200, r.text
        data = r.json()
        for key in ["explanation", "keywords", "categories", "brand_hints", "price_range", "fallback", "items", "total"]:
            assert key in data, f"Missing key: {key}. Got: {list(data.keys())}"
        assert isinstance(data["categories"], list)
        for c in data["categories"]:
            assert "id" in c and "name" in c and "slug" in c
        assert isinstance(data["items"], list)
        assert len(data["items"]) > 0, f"Expected non-empty items even via fallback. fallback={data.get('fallback')}"
