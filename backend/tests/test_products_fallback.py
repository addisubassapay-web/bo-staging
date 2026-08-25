"""Regression tests for the deploy-safe fallback in `/api/products`.

When the permanent `products` collection is nearly-empty (< 100 active
items) — the state a freshly-deployed pod finds itself in until the
first Apify auto-sync completes — `/api/products` transparently tops-up
the response with active seller `listings` so the storefront isn't blank.

On healthy environments (preview / prod post-sync) the fallback is a
NO-OP: the endpoint returns products only.

We also assert the store-page test-artefact filter — `/api/stores/{slug}/listings`
must NEVER surface `Stripe removal…` / `TEST_…` titles that leaked into
some demo stores during earlier test sessions.
"""
from __future__ import annotations

import os
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
    """Module-scoped TestClient so we don't restart the FastAPI app between
    tests — startup/shutdown races with the background asyncio loops
    otherwise trip 'Event loop is closed' errors under xdist."""
    with TestClient(app) as c:
        yield c


def test_products_endpoint_returns_product_shape(http):
    r = http.get(f"{API_PREFIX}/products", params={"page_size": 3})
    assert r.status_code == 200
    body = r.json()
    assert "items" in body and "total" in body
    for it in body["items"]:
        for k in ("id", "title", "price", "images", "created_at"):
            assert k in it, f"missing {k!r} in item"


def test_products_healthy_env_untouched(db, http):
    total_products = db.products.count_documents({"is_active": True})
    if total_products < 100:
        pytest.skip("Env has <100 active products — fallback is active here")
    r = http.get(f"{API_PREFIX}/products", params={"page_size": 24, "sort": "newest"})
    assert r.status_code == 200
    body = r.json()
    drift = abs(body["total"] - total_products)
    assert drift < 200, (
        f"Fallback should NOT have activated: total={body['total']} vs {total_products} (drift={drift})"
    )


def test_store_listings_filter_hides_test_artifacts(db, http):
    store = db.stores.find_one(
        {"slug": {"$not": {"$regex": r"^(e2e|test|56555665)"}}},
        {"_id": 0, "slug": 1},
    )
    if not store:
        pytest.skip("No non-test stores present")
    r = http.get(f"{API_PREFIX}/stores/{store['slug']}/listings")
    assert r.status_code == 200
    for l in r.json():
        title = (l.get("title") or "").lower()
        assert not title.startswith("stripe removal"), (
            f"Storefront leaked test title: {l.get('title')!r}"
        )
        assert not title.startswith("test_"), (
            f"Storefront leaked test title: {l.get('title')!r}"
        )


def test_store_56555665_filters_stripe_removal_specifically(db, http):
    store = db.stores.find_one({"slug": "56555665"}, {"_id": 0, "id": 1})
    if not store:
        pytest.skip("Demo store 56555665 not present in this environment")
    raw_test_hits = db.listings.count_documents({
        "store_id": store["id"],
        "title": {"$regex": r"^Stripe removal", "$options": "i"},
    })
    if raw_test_hits == 0:
        pytest.skip("No Stripe-removal seed listings on this store to filter")
    r = http.get(f"{API_PREFIX}/stores/56555665/listings")
    assert r.status_code == 200
    for l in r.json():
        title = (l.get("title") or "").lower()
        assert not title.startswith("stripe removal"), (
            f"Filter failed — leaked: {l.get('title')!r}"
        )


def test_products_fallback_helper_maps_listing_shape():
    """Unit test the pure `_listing_to_product_shape` mapper without hitting Mongo."""
    from routers.products import _listing_to_product_shape
    src = {
        "id": "listing-abc",
        "title": "Wireless Mouse",
        "description": "Great mouse",
        "price": 24.99,
        "images": ["a.jpg", "b.jpg"],
        "category_name": "Electronics",
        "status": "active",
        "source_url": None,
        "created_at": datetime.now(timezone.utc),
    }
    out = _listing_to_product_shape(src)
    assert out["id"] == "listing-abc"
    assert out["title"] == "Wireless Mouse"
    assert out["price"] == 24.99
    assert out["images"] == ["a.jpg", "b.jpg"]
    assert out["category"] == "Electronics"
    assert out["sku"] == "listing-abc"  # falls back to id
    assert out["in_stock"] is True
    assert out["is_active"] is True

    # An inactive listing is mapped to in_stock=False so the OOS badge
    # renders when the fallback surfaces sold/reserved items.
    src["status"] = "sold"
    out = _listing_to_product_shape(src)
    assert out["is_active"] is False
    assert out["in_stock"] is False


def test_products_fallback_pagination_math():
    """When the fallback is active we need pagination to reflect the merged
    total (products + listings). Verifies the total flows through when the
    real environment has many products."""
    from routers.products import _augment_with_listings
    import asyncio
    from motor.motor_asyncio import AsyncIOMotorClient

    async def _run():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        # Direct helper call — assert merged total > products_total because
        # `db.listings` has some rows.
        merged, total = await _augment_with_listings(
            db=db,
            existing_docs=[],
            products_total=0,
            page=1,
            page_size=5,
            category=None,
            subcategory=None,
            q=None,
            in_stock_only=False,
            sort="newest",
        )
        client.close()
        return merged, total

    merged, total = asyncio.get_event_loop().run_until_complete(_run())
    # At least one active seller listing must be present in a healthy env.
    assert total > 0
    # Merged page must have between 0 and page_size items.
    assert 0 <= len(merged) <= 5
    # Any augmented items must expose the product-shape keys.
    for it in merged:
        for k in ("id", "title", "price", "images"):
            assert k in it
