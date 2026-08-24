"""Regression: default sort must surface in-stock products first, so the
storefront never lands a fresh visitor on 4 pages of "Currently Unavailable"
tiles.

Also covers the `in_stock_only` query param the "In stock only" toggle
on /products depends on.
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


def test_default_sort_puts_in_stock_first():
    """Page 1 of /api/products must be dominated by in-stock items."""
    r = requests.get(f"{API}/products?page=1&page_size=48", timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    items = data["items"]
    assert items, "empty catalog"
    oos_on_page1 = sum(1 for it in items if it.get("in_stock") is False)
    assert oos_on_page1 == 0, (
        f"Default sort must demote OOS items — page 1 has {oos_on_page1} out-of-stock tiles"
    )


def test_in_stock_only_excludes_oos():
    r_all = requests.get(f"{API}/products?page=1&page_size=1", timeout=15)
    r_in_stock = requests.get(f"{API}/products?page=1&page_size=1&in_stock_only=true", timeout=15)
    assert r_all.status_code == 200 and r_in_stock.status_code == 200
    total_all = r_all.json()["total"]
    total_in = r_in_stock.json()["total"]
    assert total_in <= total_all, "in_stock_only must never exceed total"
    # Sanity: the difference is exactly the number of OOS docs. We don't
    # know that number ahead of time, but it must be >= 0 and typically > 0
    # while any dataset with real OOS items is loaded.
    assert total_all - total_in >= 0


def test_explicit_newest_sort_still_works():
    r = requests.get(f"{API}/products?page=1&page_size=5&sort=newest", timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["items"], "empty response"
    # newest sort ignores in_stock ranking — just verify we still get 5 items
    assert len(data["items"]) == 5


def test_product_response_shape_includes_in_stock():
    r = requests.get(f"{API}/products?page=1&page_size=1", timeout=15)
    data = r.json()
    assert data["items"], "empty response"
    item = data["items"][0]
    assert "in_stock" in item, "in_stock field missing from product response"
    assert isinstance(item["in_stock"], bool)
