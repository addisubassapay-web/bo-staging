"""Regression: category endpoint + case-insensitive category filter.

Guards the category-chip UX and the auto-classifier that fills them.
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

CANONICAL = [
    "Women", "Men", "Kids", "Electronics", "Home",
    "Beauty", "Sports", "Toys", "Books", "Handmade",
]


def test_categories_endpoint_returns_all_canonical():
    r = requests.get(f"{API}/products/categories", timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    names = [c["name"] for c in data["items"]]
    assert names == CANONICAL, f"unexpected order/list: {names}"
    for c in data["items"]:
        assert set(c.keys()) == {"name", "slug", "count"}
        assert c["slug"] == c["name"].lower()
        assert isinstance(c["count"], int) and c["count"] >= 0
    assert "total" in data
    assert "uncategorized" in data


def test_counts_sum_close_to_total():
    r = requests.get(f"{API}/products/categories", timeout=15)
    data = r.json()
    counted = sum(c["count"] for c in data["items"])
    assert counted + data["uncategorized"] == data["total"], (
        f"count mismatch: {counted} + {data['uncategorized']} != {data['total']}"
    )


def test_category_filter_case_insensitive():
    r_lower = requests.get(f"{API}/products?category=electronics&page_size=1", timeout=15).json()
    r_upper = requests.get(f"{API}/products?category=Electronics&page_size=1", timeout=15).json()
    assert r_lower["total"] == r_upper["total"], "case sensitivity leaked into filter"
    assert r_upper["total"] > 0, "Electronics bucket unexpectedly empty"


def test_category_filter_in_stock_only():
    all_electronics = requests.get(
        f"{API}/products?category=Electronics&page_size=1", timeout=15
    ).json()["total"]
    in_stock_electronics = requests.get(
        f"{API}/products?category=Electronics&in_stock_only=true&page_size=1", timeout=15
    ).json()["total"]
    assert in_stock_electronics <= all_electronics


def test_returned_products_actually_have_matching_category():
    r = requests.get(f"{API}/products?category=Books&page_size=10", timeout=15)
    data = r.json()
    assert data["items"], "empty Books bucket"
    for it in data["items"]:
        assert it.get("category") == "Books", (
            f"{it.get('sku')} leaked into Books with category={it.get('category')!r}"
        )


def test_uncategorized_only_leaves_a_small_tail():
    """The re-categorization backfill should have reduced uncategorized
    to a small tail — regression guard against future ingests that
    re-introduce many uncategorized rows."""
    data = requests.get(f"{API}/products/categories", timeout=15).json()
    # We know from the initial backfill that ~54 items were legitimately
    # unclassifiable. Guard against regressions that push it back up.
    assert data["uncategorized"] < 300, (
        f"uncategorized products blew up: {data['uncategorized']}"
    )
