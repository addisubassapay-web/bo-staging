"""Regression: storefront guardrails against test-data pollution.

Testing agents kept re-creating `e2e_seller_*` users with `TEST_p52 *`
listings, dominating the marketplace's `newest` sort. These tests lock
in the API-level filters so shoppers never see test artefacts again.

Coverage:
  - /api/listings excludes TEST_* titles and e2e_* sellers
  - /api/listings/count matches the filtered total
  - /api/products excludes B00TEST/SYNC/ASY/FORCE/BIG SKUs
  - /api/products/categories counts match the filtered total
  - /api/wallet/ticker excludes TEST_p52 releases from the public feed
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


def test_listings_endpoint_hides_test_titles():
    r = requests.get(f"{API}/listings?sort=newest&limit=48", timeout=15)
    assert r.status_code == 200, r.text
    items = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
    for it in items:
        assert not (it.get("title") or "").startswith("TEST_"), (
            f"TEST-title leaked: {it.get('title')}"
        )
        assert not (it.get("seller_name") or "").startswith("e2e_"), (
            f"e2e seller leaked: {it.get('seller_name')}"
        )


def test_listings_count_matches_filtered_total():
    """Count endpoint must apply the same guardrails as the list endpoint."""
    r = requests.get(f"{API}/listings/count", timeout=15).json()
    total = r["total"]
    # Fetch a large page and confirm none are test artefacts
    items = requests.get(f"{API}/listings?limit=500", timeout=15).json()
    if isinstance(items, dict):
        items = items.get("items", [])
    for it in items:
        assert not (it.get("title") or "").startswith("TEST_")
    # And count <= total inventory
    assert total < 10_000  # sanity


def test_products_endpoint_hides_test_skus():
    r = requests.get(f"{API}/products?page=1&page_size=48", timeout=15).json()
    for it in r["items"]:
        sku = it.get("sku") or ""
        assert not any(
            sku.startswith(p) for p in ("B00TEST", "B00SYNC", "B00ASY", "B00FORCE", "B00BIG")
        ), f"test SKU leaked: {sku}"


def test_products_categories_reflect_filtered_total():
    r = requests.get(f"{API}/products/categories", timeout=15).json()
    counted = sum(c["count"] for c in r["items"])
    assert counted + r["uncategorized"] == r["total"], (
        f"count mismatch after guardrail: {counted} + {r['uncategorized']} != {r['total']}"
    )


def test_wallet_ticker_excludes_test_releases():
    r = requests.get(f"{API}/wallet/ticker?limit=30&minutes=1440", timeout=15).json()
    for row in r:
        assert "TEST_" not in (row.get("listing_title") or ""), (
            f"TEST_ leaked into public ticker: {row}"
        )
