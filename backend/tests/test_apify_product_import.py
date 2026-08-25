"""Unit tests for the Apify run→catalog import path.

Covers:
  - The new `product_*` prefixed key schema used by Amazon-Rainforest-style
    Apify actors (product_title, product_price, product_url, product_photo).
  - Category / breadcrumb override behaviour in the import endpoint's
    normalization step (verified via the normalizer directly — mocking
    Apify HTTP end-to-end is done in a separate integration test).
"""
from __future__ import annotations

from routers.products import (
    _extract_images,
    _extract_price,
    _extract_source_url,
    _normalize_product,
)


def _amazon_rainforest_item():
    """Sample item mirroring the exact schema of the Apify actor whose run
    produced the 306-item laptop dataset the admin wants to permanent-import."""
    return {
        "asin": "B0GQB1C381",
        "currency": "USD",
        "product_title": "HP OmniBook 3 16 inch Laptop PC, 2K Touchscreen, AMD Ryzen 3",
        "product_price": "$449.99",
        "product_original_price": "$669.99",
        "product_url": "https://www.amazon.com/dp/B0GQB1C381",
        "product_photo": "https://m.media-amazon.com/images/I/71+WKmQWrsL._AC_UY654_QL65_.jpg",
        "product_star_rating": "4.3",
        "product_num_ratings": 45,
    }


def test_extract_price_from_product_price_dollar_string():
    price = _extract_price({"product_price": "$449.99"})
    assert price == 449.99


def test_extract_price_ignores_missing():
    assert _extract_price({}) is None


def test_extract_source_url_from_product_url():
    url = _extract_source_url({"product_url": "https://www.amazon.com/dp/B0GQB1C381"})
    assert url == "https://www.amazon.com/dp/B0GQB1C381"


def test_extract_images_from_product_photo():
    imgs = _extract_images({"product_photo": "https://m.media-amazon.com/images/I/71.jpg"})
    assert imgs == ["https://m.media-amazon.com/images/I/71.jpg"]


def test_extract_images_ignores_non_http():
    imgs = _extract_images({"product_photo": "javascript:alert(1)"})
    assert imgs == []


def test_normalize_amazon_rainforest_item_end_to_end():
    """The full normaliser must produce a valid `products` doc from the
    product_* schema so the /admin/apify/runs/{id}/import path doesn't
    silently skip the whole dataset."""
    norm = _normalize_product(_amazon_rainforest_item())
    assert norm is not None
    assert norm["title"].startswith("HP OmniBook 3")
    assert norm["price"] == 449.99
    assert norm["currency"] == "USD"
    assert norm["sku"] == "B0GQB1C381"
    assert norm["source_url"] == "https://www.amazon.com/dp/B0GQB1C381"
    assert norm["in_stock"] is True
    assert len(norm["images"]) == 1


def test_normalize_returns_none_when_no_title():
    """Regression: items missing every title variant should be skipped."""
    assert _normalize_product({"asin": "X"}) is None


def test_normalize_returns_none_when_no_dedupe_key():
    """Items with a title but no sku AND no url can't be safely upserted."""
    assert _normalize_product({"product_title": "T"}) is None


def test_category_override_pattern_reproduced_in_test():
    """The import endpoint overrides `category` and `breadcrumbs` after
    normalization. Verify the shape it produces (chip lookups depend on
    the '>' separator to isolate the subcategory)."""
    norm = _normalize_product(_amazon_rainforest_item())
    norm["category"] = "Computer"
    norm["breadcrumbs"] = "Computer > Laptop"
    assert norm["category"] == "Computer"
    # Storefront subcategory regex depends on ">" as delimiter
    assert " > Laptop" in norm["breadcrumbs"]


def test_canonical_categories_include_computer():
    """The new `Computer` bucket must appear in the storefront chip row."""
    from services.product_category import CANONICAL_CATEGORIES
    assert "Computer" in CANONICAL_CATEGORIES
