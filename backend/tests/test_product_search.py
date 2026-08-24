"""Regression: search suggest + subcategory endpoints.

Covers:
  - autocomplete prefix hits
  - spelling correction on misspelled queries
  - related-term extraction
  - subcategory rollup from breadcrumbs
  - subcategory query filter on /api/products
"""
from __future__ import annotations

import os
from pathlib import Path

import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    for line in Path("/app/frontend/.env").read_text().splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            BASE_URL = line.split("=", 1)[1].strip().strip('"').rstrip("/")
            break
API = f"{BASE_URL}/api"


def test_suggest_prefix_returns_products():
    r = requests.get(f"{API}/products/suggest?q=headphon", timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["query"] == "headphon"
    assert data["corrected"] is None  # prefix hit, no correction needed
    assert len(data["products"]) > 0
    # every product must mention the query substring
    for p in data["products"]:
        assert "headphon" in p["title"].lower(), p["title"]


def test_suggest_spelling_correction():
    r = requests.get(f"{API}/products/suggest?q=kindel", timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["corrected"] == "kindle", f"expected correction 'kindle', got {data['corrected']!r}"
    # AND we should get actual products for the corrected query
    assert len(data["products"]) > 0


def test_suggest_returns_related_terms():
    r = requests.get(f"{API}/products/suggest?q=headphon", timeout=15).json()
    assert isinstance(r["terms"], list)
    # We expect at least a couple of common shopping terms
    assert len(r["terms"]) >= 2


def test_suggest_short_query_returns_empty():
    r = requests.get(f"{API}/products/suggest?q=a", timeout=15).json()
    assert r["products"] == []
    assert r["corrected"] is None


def test_subcategories_endpoint():
    r = requests.get(f"{API}/products/subcategories?category=Home", timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["category"] == "Home"
    assert data["total"] > 0
    assert len(data["items"]) > 0
    # counts must be > 0 for every returned bucket
    for it in data["items"]:
        assert it["count"] > 0
        assert isinstance(it["name"], str) and it["name"]


def test_subcategory_filter_narrows_results():
    all_electronics = requests.get(
        f"{API}/products?category=Electronics&page_size=1", timeout=15
    ).json()["total"]
    ps5_only = requests.get(
        f"{API}/products?category=Electronics&subcategory=PlayStation%205&page_size=1", timeout=15
    ).json()["total"]
    assert ps5_only > 0
    assert ps5_only < all_electronics, "subcategory filter should narrow results"


def test_suggest_perf_under_2s():
    r = requests.get(f"{API}/products/suggest?q=wireless", timeout=15).json()
    assert r["took_ms"] < 2000, f"suggest took {r['took_ms']}ms — perf regression"
