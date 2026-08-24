"""Wallet activity timeline + deposit resubmit — Feb 2026.

These endpoints power the Profile > Sales / Purchases per-order timeline
and the /wallet "Resubmit" one-tap flow for rejected deposits.

Endpoints under test:
  * GET  /api/orders/{order_id}/wallet-events
  * POST /api/wallet/deposits/{dep_id}/resubmit
"""
from __future__ import annotations

import os
import uuid

import pytest
import requests

API = os.environ.get("E2E_API_URL") or "http://127.0.0.1:8001/api"


def _h(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def admin_token() -> str:
    r = requests.post(f"{API}/auth/login",
                      json={"email": "admin@mercari.local", "password": "admin123"}, timeout=15)
    r.raise_for_status()
    return r.json()["token"]


@pytest.fixture(scope="module")
def category_id() -> str:
    d = requests.get(f"{API}/categories", timeout=15).json()
    items = d if isinstance(d, list) else d.get("items", [])
    return items[0]["id"]


def _register(prefix: str) -> tuple[str, dict]:
    uid = uuid.uuid4().hex[:8]
    r = requests.post(f"{API}/auth/register",
                      json={"email": f"{prefix}_{uid}@e2e.com", "password": "pass1234", "username": f"{prefix}{uid}"}, timeout=15)
    r.raise_for_status()
    tok = r.json()["token"]
    me = requests.get(f"{API}/auth/me", headers=_h(tok), timeout=15).json()
    return tok, me


def _make_seller(admin_token: str) -> tuple[str, dict]:
    tok, u = _register("seller")
    requests.put(f"{API}/admin/users/{u['id']}", headers=_h(admin_token),
                 json={"seller_status": "approved"}, timeout=15).raise_for_status()
    return tok, u


def _topup(admin_token: str, user_id: str, amount: float) -> None:
    requests.post(f"{API}/admin/users/{user_id}/wallet-adjust", headers=_h(admin_token),
                  json={"delta": amount, "description": "test"}, timeout=15).raise_for_status()


def _place_order(admin_token, category_id):
    seller_tok, seller = _make_seller(admin_token)
    buyer_tok, buyer = _register("buyer")
    _topup(admin_token, buyer["id"], 200.0)
    lst = requests.post(f"{API}/listings", headers=_h(seller_tok),
                        json={"title": f"E2E timeline {uuid.uuid4().hex[:6]}", "description": "t",
                              "price": 60.0, "category_id": category_id,
                              "images": ["https://picsum.photos/200"], "condition": "new", "quantity": 1},
                        timeout=15).json()
    order = requests.post(f"{API}/orders", headers=_h(buyer_tok),
                          json={"listing_id": lst["id"], "quantity": 1, "payment_method": "wallet",
                                "shipping_address": {"line1": "1 St", "city": "NYC", "zip": "10001"}},
                          timeout=15).json()
    return seller_tok, seller, buyer_tok, buyer, order


# ---------- Timeline endpoint ----------
def test_timeline_buyer_sees_only_own_purchase_debit(admin_token, category_id):
    _seller_tok, _seller, buyer_tok, _buyer, order = _place_order(admin_token, category_id)
    r = requests.get(f"{API}/orders/{order['id']}/wallet-events", headers=_h(buyer_tok), timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] >= 1
    # All events must belong to buyer.
    roles = [e["role"] for e in body["events"]]
    assert "buyer_paid" in roles
    # No seller entries leaked to buyer.
    for e in body["events"]:
        assert e["type"] not in ("sale_frozen", "sale_released"), "seller row leaked to buyer"


def test_timeline_seller_sees_escrow_and_release(admin_token, category_id):
    seller_tok, _seller, buyer_tok, _buyer, order = _place_order(admin_token, category_id)
    # Complete the flow: seller picks, buyer confirms delivery.
    requests.post(f"{API}/orders/{order['id']}/pickup", headers=_h(seller_tok), json={}, timeout=15).raise_for_status()
    requests.post(f"{API}/orders/{order['id']}/confirm-delivery", headers=_h(buyer_tok), timeout=15).raise_for_status()

    r = requests.get(f"{API}/orders/{order['id']}/wallet-events", headers=_h(seller_tok), timeout=15)
    body = r.json()
    roles = [e["role"] for e in body["events"]]
    assert "seller_escrow_held" in roles
    assert "seller_delivery_released" in roles


def test_timeline_non_party_forbidden(admin_token, category_id):
    _seller_tok, _seller, _buyer_tok, _buyer, order = _place_order(admin_token, category_id)
    other_tok, _ = _register("nosy")
    r = requests.get(f"{API}/orders/{order['id']}/wallet-events", headers=_h(other_tok), timeout=15)
    assert r.status_code == 403


def test_timeline_admin_sees_all(admin_token, category_id):
    _seller_tok, _seller, _buyer_tok, _buyer, order = _place_order(admin_token, category_id)
    r = requests.get(f"{API}/orders/{order['id']}/wallet-events", headers=_h(admin_token), timeout=15)
    body = r.json()
    # Admin sees both buyer purchase + seller escrow.
    roles = [e["role"] for e in body["events"]]
    assert "buyer_paid" in roles
    assert "seller_escrow_held" in roles


# ---------- Deposit resubmit ----------
def _make_deposit(buyer_tok: str) -> dict:
    r = requests.post(f"{API}/wallet/deposit/pending", headers=_h(buyer_tok),
                      json={"amount": 30.0, "method": "crypto", "currency": "BTC",
                            "reference": "orig_ref", "screenshot_url": "https://picsum.photos/300"},
                      timeout=15)
    r.raise_for_status()
    return r.json()


def test_resubmit_only_allowed_after_reject(admin_token):
    buyer_tok, _ = _register("buyer")
    dep = _make_deposit(buyer_tok)
    # Pending → cannot resubmit.
    r = requests.post(f"{API}/wallet/deposits/{dep['id']}/resubmit", headers=_h(buyer_tok),
                      json={"screenshot_url": "https://picsum.photos/301"}, timeout=15)
    assert r.status_code == 400


def test_resubmit_happy_path(admin_token):
    buyer_tok, _ = _register("buyer")
    dep = _make_deposit(buyer_tok)
    # Reject
    requests.post(f"{API}/admin/deposits/{dep['id']}/reject", headers=_h(admin_token),
                  json={"reason": "screenshot too dark"}, timeout=15).raise_for_status()
    # Resubmit with new screenshot
    r = requests.post(f"{API}/wallet/deposits/{dep['id']}/resubmit", headers=_h(buyer_tok),
                      json={"screenshot_url": "https://picsum.photos/301"}, timeout=15)
    assert r.status_code == 200, r.text
    updated = r.json()
    assert updated["status"] == "pending"
    assert updated["screenshot_url"] == "https://picsum.photos/301"
    assert updated["resubmit_count"] == 1
    assert updated["admin_note"] == ""


def test_resubmit_requires_new_data(admin_token):
    buyer_tok, _ = _register("buyer")
    dep = _make_deposit(buyer_tok)
    requests.post(f"{API}/admin/deposits/{dep['id']}/reject", headers=_h(admin_token),
                  json={"reason": "unclear"}, timeout=15).raise_for_status()
    r = requests.post(f"{API}/wallet/deposits/{dep['id']}/resubmit", headers=_h(buyer_tok), json={}, timeout=15)
    assert r.status_code == 400


def test_resubmit_only_owner(admin_token):
    buyer_tok, _ = _register("buyer")
    dep = _make_deposit(buyer_tok)
    requests.post(f"{API}/admin/deposits/{dep['id']}/reject", headers=_h(admin_token),
                  json={"reason": "x"}, timeout=15).raise_for_status()
    other_tok, _ = _register("other")
    r = requests.post(f"{API}/wallet/deposits/{dep['id']}/resubmit", headers=_h(other_tok),
                      json={"screenshot_url": "https://picsum.photos/302"}, timeout=15)
    assert r.status_code == 403
