"""Iteration 49 – Product image ingestion filter + DB cleanup verification."""
import os
import sys
import asyncio
import pytest
import requests

sys.path.insert(0, "/app/backend")
from apify_sync import _is_clean_amazon_image  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]


# ── URL filter unit tests ───────────────────────────────────────────────
class TestIsCleanAmazonImage:
    def test_valid_amazon_image(self):
        assert _is_clean_amazon_image("https://m.media-amazon.com/images/I/61abc.jpg") is True

    def test_composite_cl_marker(self):
        assert _is_clean_amazon_image(
            "https://m.media-amazon.com/images/I/B1p._CLa%7C2140.png"
        ) is False

    def test_other_domain_valid(self):
        assert _is_clean_amazon_image("https://foo.com/x.jpg") is True

    def test_not_a_url(self):
        assert _is_clean_amazon_image("not-a-url") is False

    def test_none(self):
        assert _is_clean_amazon_image(None) is False

    def test_pipe_encoded(self):
        assert _is_clean_amazon_image("https://m.media-amazon.com/images/I/x%7Cy.jpg") is False

    def test_raw_pipe(self):
        assert _is_clean_amazon_image("https://m.media-amazon.com/images/I/x|y.jpg") is False


# ── DB cleanup verification ─────────────────────────────────────────────
@pytest.fixture(scope="module")
def db():
    client = AsyncIOMotorClient(MONGO_URL)
    return client[DB_NAME]


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TestDbCleanup:
    def test_no_bad_urls_in_listings(self, db):
        async def _q():
            return await db.listings.count_documents({
                "images": {"$regex": r"(\._CL|%7C|%7c)"}
            })
        count = _run(_q())
        assert count == 0, f"Found {count} listings with bad image URLs"

    def test_no_bad_urls_in_products(self, db):
        async def _q():
            return await db.products.count_documents({
                "images": {"$regex": r"(\._CL|%7C|%7c)"}
            })
        count = _run(_q())
        assert count == 0, f"Found {count} products with bad image URLs"


# ── Backend API sanity ──────────────────────────────────────────────────
class TestApi:
    def test_categories_returns_electronics(self):
        r = requests.get(f"{BASE_URL}/api/categories", timeout=15)
        assert r.status_code == 200
        cats = r.json()
        slugs = [c.get("slug") for c in cats]
        assert "electronics" in slugs

    def test_listings_endpoint(self):
        r = requests.get(f"{BASE_URL}/api/listings?limit=20", timeout=15)
        assert r.status_code == 200
        data = r.json()
        items = data if isinstance(data, list) else data.get("items") or data.get("listings") or []
        assert len(items) > 0
        # Verify no bad URLs in the top listings
        bad = []
        for item in items:
            for url in item.get("images", []):
                if url and ("._CL" in url or "%7C" in url or "%7c" in url):
                    bad.append(url)
        assert bad == [], f"Bad URLs surfaced by API: {bad[:5]}"
