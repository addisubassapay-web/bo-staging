"""Currency-to-USD auto-conversion regression at ingest time."""
from routers.products import _normalize_currency_to_usd, _normalize_product


def test_inr_price_converted_to_usd():
    """₹466 → about $5.60 using the static 83.2 rate."""
    usd_price, currency, orig_price, orig_cur = _normalize_currency_to_usd(466, "INR")
    assert currency == "USD"
    assert orig_price == 466
    assert orig_cur == "INR"
    assert 5.5 < usd_price < 5.7


def test_usd_price_passes_through_unchanged():
    usd_price, currency, orig_price, orig_cur = _normalize_currency_to_usd(19.99, "USD")
    assert currency == "USD"
    assert usd_price == 19.99
    assert orig_price is None
    assert orig_cur is None


def test_unknown_currency_preserves_input():
    """Never corrupt data when we don't have a rate."""
    usd_price, currency, orig_price, orig_cur = _normalize_currency_to_usd(100, "XYZ")
    assert currency == "XYZ"
    assert usd_price == 100
    assert orig_price is None


def test_normalize_product_stores_usd_price_and_original():
    """End-to-end: a Shopsy INR item lands as USD with original stashed."""
    shopsy = {
        "type": "ProductSummaryValue",
        "id": "TEST123",
        "titles": {"title": "Test Wallet", "co_subtitle": "Genuine leather"},
        "pricing": {"final_price": {"value": 832, "currency": "INR"}},
        "media": {"images": [{"url": "http://x.com/{@width}/{@height}/a.jpg?q={@quality}"}]},
        "smart_url": "http://dl.flipkart.com/wallet/p/itmxyz",
    }
    doc = _normalize_product(shopsy)
    assert doc is not None
    assert doc["currency"] == "USD"
    assert 9.9 < doc["price"] < 10.1
    assert doc["original_price"] == 832
    assert doc["original_currency"] == "INR"
