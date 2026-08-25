"""Storefront guardrails — keep test/regression artefacts out of every
public listing, product and ticker endpoint by default.

Testing agents keep re-creating `e2e_seller_*` users with `TEST_p52 *`
listings; without a hard filter at the API layer, those tiles dominate
`newest`-sorted feeds every time a test suite runs. This module is the
single source of truth for the exclusion filter so we can extend it
without hunting through the codebase.

Public API:
    listing_test_filter()  → dict added to a Mongo `find(filt)` query
    product_test_filter()  → same, for the permanent product catalog

Admins can opt out via `?include_test_data=true` on endpoints that
choose to support it.
"""
from __future__ import annotations

from typing import Any, Dict

# Titles that a testing agent creates. Matched as case-insensitive regex
# on `title` — real Amazon product titles never start with these.
# Kept in a single place (services/storefront_filter) so every route that
# reads listings gets the same guardrail.
LISTING_TEST_TITLE_RE = (
    r"^(TEST_|E2E |E2E_|Timeline test|Follow Notif Test|FOLLOW NOTIF TEST|"
    r"Stripe removal|Bump Test|PRODUCTS_FALLBACK_FIXTURE|SYNC_TEST_|"
    r"e2e_)"
)

# SKU prefixes we reserve for regression tests. Real Amazon ASINs never
# start with these because Amazon's product IDs don't have "TEST" /
# "SYNC" / "ASY" / "FORCE" / "BIG" as ASIN prefixes in practice.
PRODUCT_TEST_SKU_RE = r"^B00(TEST|SYNC|ASY|FORCE|BIG)"

# Test seller usernames — used to filter both listings and store rows.
SELLER_TEST_USERNAME_RE = r"^e2e_"


def listing_test_filter() -> Dict[str, Any]:
    """Mongo query fragment that excludes test listings (case-insensitive)."""
    return {
        "$and": [
            {"title": {"$not": {"$regex": LISTING_TEST_TITLE_RE, "$options": "i"}}},
            {"seller_name": {"$not": {"$regex": SELLER_TEST_USERNAME_RE}}},
        ]
    }


def product_test_filter() -> Dict[str, Any]:
    """Mongo query fragment that excludes test products."""
    return {"sku": {"$not": {"$regex": PRODUCT_TEST_SKU_RE}}}


def user_test_filter() -> Dict[str, Any]:
    """Excludes e2e / lockout test accounts."""
    return {
        "$and": [
            {"username": {"$not": {"$regex": SELLER_TEST_USERNAME_RE}}},
            {"email": {"$not": {"$regex": r"^(e2e_|lockout_test_)"}}},
        ]
    }
