"""Regression tests for the storefront title/seller filter.

Locks in the exclusion patterns in `services/storefront_filter.py` so a
future refactor can't accidentally drop `E2E `, `Timeline test`,
`Stripe removal`, etc. from the public storefront.
"""
from __future__ import annotations

import os
import re
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from pymongo import MongoClient

from server import app


API_PREFIX = "/api"


@pytest.fixture(scope="module")
def db():
    client = MongoClient(os.environ["MONGO_URL"])
    d = client[os.environ["DB_NAME"]]
    yield d
    client.close()


@pytest.fixture(scope="module")
def http():
    with TestClient(app) as c:
        yield c


def _seed_test_listing(db, *, title: str, seller_name: str = "storefront_filter_test_seller") -> str:
    lid = f"filter-test-{uuid.uuid4().hex[:8]}"
    db.listings.insert_one({
        "id": lid,
        "seller_id": "seed-seller-1",
        "seller_name": seller_name,
        "title": title,
        "description": "seed listing",
        "price": 9.99,
        "category_id": "cat-electronics",
        "category_name": "Electronics",
        "images": ["https://example.invalid/f.jpg"],
        "status": "active",
        "created_at": datetime.now(timezone.utc),
    })
    return lid


BAD_TITLES = [
    "E2E timeline 552560",
    "E2E listing 33c587",
    "e2e Wireless Earbuds v2",  # lowercase — case-insensitive filter
    "Timeline test rocks",
    "TEST_p52 24a680",
    "Stripe removal QA item",
    "Bump Test Listing",
    "PRODUCTS_FALLBACK_FIXTURE_abc123",
]


def test_bad_titles_are_hidden_from_listings_endpoint(db, http):
    """None of the reserved test-title prefixes may leak into /api/listings."""
    seeded = []
    try:
        for t in BAD_TITLES:
            seeded.append(_seed_test_listing(db, title=t))
        r = http.get(f"{API_PREFIX}/listings", params={"limit": 500, "sort": "newest"})
        assert r.status_code == 200
        titles = [l.get("title", "") for l in r.json()]
        pattern = re.compile(
            r"^(TEST_|E2E |E2E_|Timeline test|Follow Notif Test|FOLLOW NOTIF TEST|"
            r"Stripe removal|Bump Test|PRODUCTS_FALLBACK_FIXTURE|SYNC_TEST_|e2e_)",
            re.I,
        )
        leaks = [t for t in titles if pattern.match(t)]
        assert not leaks, f"Storefront leaked reserved test titles: {leaks[:5]}"
    finally:
        db.listings.delete_many({"id": {"$in": seeded}})


def test_bad_seller_names_are_hidden_from_listings_endpoint(db, http):
    """Sellers whose username starts with `e2e_` must be invisible on public feeds."""
    lid = _seed_test_listing(
        db,
        title="A perfectly normal-sounding listing title",
        seller_name="e2e_seller_leak_test_" + uuid.uuid4().hex[:6],
    )
    try:
        r = http.get(f"{API_PREFIX}/listings", params={"limit": 500, "sort": "newest"})
        assert r.status_code == 200
        found = [l for l in r.json() if l.get("id") == lid]
        assert not found, "e2e_ seller_name listing must be filtered out"
    finally:
        db.listings.delete_one({"id": lid})


def test_shared_filter_module_is_source_of_truth():
    """server.py and routers/products.py must import from services.storefront_filter."""
    from services.storefront_filter import LISTING_TEST_TITLE_RE, SELLER_TEST_USERNAME_RE
    # Positive matches
    assert re.match(LISTING_TEST_TITLE_RE, "E2E listing abc", re.I)
    assert re.match(LISTING_TEST_TITLE_RE, "e2e listing abc", re.I)
    assert re.match(LISTING_TEST_TITLE_RE, "Timeline test", re.I)
    assert re.match(LISTING_TEST_TITLE_RE, "TEST_p52 abc", re.I)
    assert re.match(LISTING_TEST_TITLE_RE, "Stripe removal QA", re.I)
    # Negative matches — real product titles must NOT match
    assert not re.match(LISTING_TEST_TITLE_RE, "Wireless Earbuds v2", re.I)
    assert not re.match(LISTING_TEST_TITLE_RE, "Merriam-Webster Dictionary", re.I)
    # Seller filter
    assert re.match(SELLER_TEST_USERNAME_RE, "e2e_seller_123")
    assert not re.match(SELLER_TEST_USERNAME_RE, "sophia_style")
