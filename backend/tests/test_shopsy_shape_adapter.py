"""Shopsy/Flipkart shape adapter regression.

Verifies that _flatten_shopsy_item + _normalize_product together correctly
convert the nested `ProductSummaryValue` shape (from Apify dataset
5P9IEkxZRt7Vpti00) into a valid catalog document — title, price, currency,
images (with {@width}/{@height}/{@quality} placeholders replaced), sku,
source_url are all populated and NOT skipped by the normalizer.
"""
from routers.products import _normalize_product, _flatten_shopsy_item


SAMPLE_SHOPSY = {
    "type": "ProductSummaryValue",
    "id": "XJNHKGKCUGEBC35D",
    "item_id": "ITMB8CA0B5798D69",
    "listing_id": "LSTXJNHKGKCUGEBC35DDF6HP7",
    "product_brand": "HOKER",
    "titles": {"title": "HOKER Loose Fit Men Dark Grey Jeans", "co_subtitle": "Size: 32"},
    "pricing": {
        "final_price": {"value": 466, "decimal_value": "466.00", "currency": "INR"},
    },
    "media": {
        "images": [
            {"url": "http://rukmini1.flixcart.com/image/{@width}/{@height}/xif0q/jean/x.jpeg?q={@quality}"},
            {"url": "http://rukmini1.flixcart.com/image/{@width}/{@height}/xif0q/jean/y.jpeg?q={@quality}"},
        ],
    },
    "smart_url": "http://dl.flipkart.com/dl/hoker-loose-fit-men-dark-grey-jeans/p/itmb8ca0b5798d69?pid=XJNHKGKCUGEBC35D",
    "base_url": "/hoker-loose-fit-men-dark-grey-jeans/p/itmb8ca0b5798d69",
}


def test_flatten_shopsy_produces_expected_flat_keys():
    flat = _flatten_shopsy_item(SAMPLE_SHOPSY)
    assert flat["title"] == "HOKER Loose Fit Men Dark Grey Jeans"
    assert flat["price"] == 466
    assert flat["currency"] == "INR"
    assert flat["sku"] == "XJNHKGKCUGEBC35D"
    assert flat["url"].startswith("https://dl.flipkart.com/")
    assert "HOKER" in flat["description"] and "Size: 32" in flat["description"]
    assert len(flat["images"]) == 2
    for u in flat["images"]:
        assert "{@" not in u, f"placeholder not replaced in {u}"
        assert u.startswith("https://"), f"http→https upgrade missed: {u}"


def test_normalize_product_accepts_shopsy_shape():
    doc = _normalize_product(SAMPLE_SHOPSY)
    assert doc is not None, "Shopsy item was rejected by normalizer"
    assert doc["title"] == "HOKER Loose Fit Men Dark Grey Jeans"
    assert doc["price"] == 466.0
    assert doc["currency"] == "INR"
    assert doc["sku"] == "XJNHKGKCUGEBC35D"
    assert doc["source_url"].startswith("https://dl.flipkart.com/")
    assert doc["in_stock"] is True
    assert len(doc["images"]) == 2


def test_non_shopsy_item_still_works_untouched():
    """Regression: a plain Amazon-shape item must still normalize normally."""
    amazon = {
        "title": "Old Amazon T-shirt",
        "price": 19.99,
        "currency": "USD",
        "url": "https://www.amazon.com/dp/B123",
        "asin": "B123",
        "images": ["https://m.media-amazon.com/images/x.jpg"],
    }
    doc = _normalize_product(amazon)
    assert doc is not None
    assert doc["title"] == "Old Amazon T-shirt"
    assert doc["sku"] == "B123"
