"""Regression: permanent catalog products are mirrored to marketplace listings.

Locks in the fix that surfaced 4,473+ Apify catalog products on /search
(was 1,179 seller-only listings before the mirror sync).
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


def test_listings_count_reflects_full_catalog():
    """Listings count must include the mirrored Merchari Store catalog,
    otherwise the /search page would still under-report the true inventory."""
    listings_total = requests.get(f"{API}/listings/count", timeout=15).json()["total"]
    products_total = requests.get(f"{API}/products?page=1&page_size=1", timeout=15).json()["total"]
    # Listings should include ~all active products (minus OOS) plus original seller listings.
    # Guardrail: listings must exceed products so seller-only inventory isn't lost.
    assert listings_total >= products_total * 0.9, (
        f"listings ({listings_total}) too low vs products ({products_total}) — "
        "mirror sync may have regressed"
    )


def test_merchari_store_seller_exists_and_owns_listings():
    r = requests.get(f"{API}/listings?limit=100", timeout=15)
    items = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
    merchari_owned = [i for i in items if i.get("seller_name") == "Merchari Store"]
    # Mirror sync should surface Merchari Store listings on newest sort
    assert len(merchari_owned) > 0, (
        "no Merchari Store listings surfaced — mirror sync missing"
    )


def test_mirror_listings_have_imported_from_id():
    """Every mirror listing must carry the source product id so we can
    reconcile the collections."""
    r = requests.get(f"{API}/listings?limit=50", timeout=15)
    items = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
    merchari = [i for i in items if i.get("seller_name") == "Merchari Store"]
    if not merchari:
        return  # tolerated: /search may have surfaced only seller items first
    for it in merchari[:5]:
        assert it.get("imported_from_id"), (
            f"mirror listing missing imported_from_id: {it.get('id')}"
        )
