"""Order payment rules — Mercari-Global Feb 2026.

* Only `payment_method="wallet"` is accepted (or omitted → defaults to wallet).
* `crypto` and `bank` are rejected at the schema level (HTTP 422).
* An insufficient wallet returns HTTP 402 with an `insufficient_wallet_balance`
  body containing `deposit_needed`, `wallet_balance`, `total_due`, `redirect`.
* Buyers top up their wallet using crypto or bank transfer via the existing
  `/api/wallet/deposit/pending` flow, admin-reviewed with proof screenshot.
* The frozen-reinvest cap for sellers is now **50%** (was 75%).
"""
from __future__ import annotations

import os
import time
import uuid

import pytest
import requests

API = os.environ.get("E2E_API_URL") or "http://127.0.0.1:8001/api"
ADMIN_EMAIL = "admin@mercari.local"
ADMIN_PASSWORD = "admin123"


def _h(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def admin_token() -> str:
    r = requests.post(
        f"{API}/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()["token"]


@pytest.fixture(scope="module")
def category_id() -> str:
    r = requests.get(f"{API}/categories", timeout=15)
    r.raise_for_status()
    d = r.json()
    items = d if isinstance(d, list) else d.get("items", [])
    return items[0]["id"]


def _register(prefix: str) -> tuple[str, dict]:
    uid = uuid.uuid4().hex[:8]
    email = f"{prefix}_{uid}@e2e.com"
    r = requests.post(
        f"{API}/auth/register",
        json={"email": email, "password": "pass1234", "username": f"{prefix}{uid}"},
        timeout=15,
    )
    r.raise_for_status()
    tok = r.json()["token"]
    me = requests.get(f"{API}/auth/me", headers=_h(tok), timeout=15).json()
    return tok, me


def _make_seller(admin_token: str) -> tuple[str, dict]:
    tok, u = _register("seller")
    requests.put(
        f"{API}/admin/users/{u['id']}",
        headers=_h(admin_token),
        json={"seller_status": "approved"},
        timeout=15,
    ).raise_for_status()
    return tok, u


def _topup(admin_token: str, user_id: str, amount: float) -> None:
    r = requests.post(
        f"{API}/admin/users/{user_id}/wallet-adjust",
        headers=_h(admin_token),
        json={"delta": amount, "description": "test topup"},
        timeout=15,
    )
    r.raise_for_status()


def _create_listing(seller_tok: str, category_id: str, price: float = 50.0) -> dict:
    r = requests.post(
        f"{API}/listings",
        headers=_h(seller_tok),
        json={
            "title": f"E2E listing {uuid.uuid4().hex[:6]}",
            "description": "test",
            "price": price,
            "category_id": category_id,
            "images": ["https://picsum.photos/400"],
            "condition": "new",
            "quantity": 1,
        },
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


# ---------- Schema rejection ----------
@pytest.mark.parametrize("method", ["crypto", "bank"])
def test_order_rejects_non_wallet_methods(admin_token, category_id, method):
    seller_tok, _ = _make_seller(admin_token)
    buyer_tok, _ = _register("buyer")
    lst = _create_listing(seller_tok, category_id)
    r = requests.post(
        f"{API}/orders",
        headers=_h(buyer_tok),
        json={
            "listing_id": lst["id"],
            "quantity": 1,
            "payment_method": method,
            "shipping_address": {"line1": "1 St", "city": "NYC", "zip": "10001"},
        },
        timeout=15,
    )
    assert r.status_code == 422, r.text
    body = r.json()
    assert "wallet" in str(body).lower()


# ---------- Insufficient wallet 402 shape ----------
def test_order_insufficient_wallet_returns_402_with_deposit_needed(admin_token, category_id):
    seller_tok, _ = _make_seller(admin_token)
    buyer_tok, buyer = _register("buyer")
    # buyer has $0 balance
    lst = _create_listing(seller_tok, category_id, price=75.0)
    r = requests.post(
        f"{API}/orders",
        headers=_h(buyer_tok),
        json={
            "listing_id": lst["id"],
            "quantity": 1,
            "payment_method": "wallet",
            "shipping_address": {"line1": "1 St", "city": "NYC", "zip": "10001"},
        },
        timeout=15,
    )
    assert r.status_code == 402, r.text
    detail = r.json()["detail"]
    assert detail["error"] == "insufficient_wallet_balance"
    assert detail["wallet_balance"] == 0.0
    assert detail["total_due"] == 75.0
    assert detail["deposit_needed"] == 75.0
    assert detail["redirect"] == "/wallet"


# ---------- Happy path: default method → wallet ----------
def test_order_default_method_uses_wallet(admin_token, category_id):
    seller_tok, _ = _make_seller(admin_token)
    buyer_tok, buyer = _register("buyer")
    _topup(admin_token, buyer["id"], 100.0)
    lst = _create_listing(seller_tok, category_id, price=40.0)
    # NOTE: no payment_method passed
    r = requests.post(
        f"{API}/orders",
        headers=_h(buyer_tok),
        json={
            "listing_id": lst["id"],
            "quantity": 1,
            "shipping_address": {"line1": "1 St", "city": "NYC", "zip": "10001"},
        },
        timeout=15,
    )
    assert r.status_code == 200, r.text
    o = r.json()
    assert o["status"] == "paid"
    assert o["fulfillment_status"] == "pending_pickup"
    assert o["payment_method"] == "wallet"


# ---------- 50% cap live from pickup-quote ----------
def test_pickup_quote_reports_50pct_cap(admin_token, category_id):
    """Give seller $200 frozen (from a first sale), then a second sale whose
    quote must show `frozen_usable = 100.0` (50% of the $200 not in this order)."""
    seller_tok, seller = _make_seller(admin_token)
    buyer_tok, buyer = _register("buyer")
    _topup(admin_token, buyer["id"], 500.0)

    # First order: seller earns $200 frozen.
    lst1 = _create_listing(seller_tok, category_id, price=200.0)
    r = requests.post(
        f"{API}/orders", headers=_h(buyer_tok),
        json={"listing_id": lst1["id"], "quantity": 1, "payment_method": "wallet",
              "shipping_address": {"line1": "1 St", "city": "NYC", "zip": "10001"}}, timeout=15,
    )
    assert r.status_code == 200, r.text

    # Second order.
    lst2 = _create_listing(seller_tok, category_id, price=50.0)
    r = requests.post(
        f"{API}/orders", headers=_h(buyer_tok),
        json={"listing_id": lst2["id"], "quantity": 1, "payment_method": "wallet",
              "shipping_address": {"line1": "1 St", "city": "NYC", "zip": "10001"}}, timeout=15,
    )
    order2 = r.json()

    # Quote on order2 — frozen_ex_own = $200, frozen_usable = 50% = $100.
    r = requests.get(f"{API}/orders/{order2['id']}/pickup-quote", headers=_h(seller_tok), timeout=15)
    assert r.status_code == 200, r.text
    q = r.json()
    w = q["wallet"]
    assert w["frozen_excluding_this_order"] == 200.0
    assert w["frozen_usable"] == 100.0, f"expected 50% cap = $100, got {w['frozen_usable']}"
