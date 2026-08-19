#!/usr/bin/env python3
"""Focused verification for Stripe-removal deployment readiness.

Creates only minimal test data needed to prove wallet checkout still works.
"""
import json
import os
import sys
import time
from pathlib import Path

import requests


FRONTEND_ENV = Path("/app/frontend/.env")
API_BASE = os.environ.get("API_BASE")
if not API_BASE and FRONTEND_ENV.exists():
    for line in FRONTEND_ENV.read_text().splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            API_BASE = line.split("=", 1)[1].strip().strip('"')
            break
API = (API_BASE or "http://localhost:8001").rstrip("/") + "/api"

ADMIN = {"email": "admin@mercari.local", "password": "admin123"}
DEMO = {"email": "sophia_style@demo.local", "password": "demo1234"}

results = []


def record(name, ok, details=None):
    results.append({"name": name, "ok": bool(ok), "details": details or {}})
    print(("PASS" if ok else "FAIL") + f" - {name}: {json.dumps(details or {}, default=str)}")


def request(method, path, **kwargs):
    return requests.request(method, API + path, timeout=30, **kwargs)


def login(creds):
    r = request("POST", "/auth/login", json=creds)
    r.raise_for_status()
    return r.json()["token"], r.json()["user"]


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def ensure_wallet_balance(user_token, admin_token, min_balance=20.0):
    wallet = request("GET", "/wallet", headers=auth(user_token))
    wallet.raise_for_status()
    bal = float(wallet.json().get("balance") or 0)
    if bal >= min_balance:
        return bal, None
    dep_payload = {
        "amount": min_balance,
        "method": "manual",
        "currency": "bank_transfer",
        "reference": f"stripe-removal-test-{int(time.time())}",
        "note": "QA wallet checkout funding",
    }
    dep = request("POST", "/wallet/deposit", headers=auth(user_token), json=dep_payload)
    dep.raise_for_status()
    dep_id = dep.json()["id"]
    approve = request("POST", f"/admin/deposits/{dep_id}/approve", headers=auth(admin_token))
    approve.raise_for_status()
    wallet2 = request("GET", "/wallet", headers=auth(user_token))
    wallet2.raise_for_status()
    return float(wallet2.json().get("balance") or 0), dep_id


def get_or_create_category(admin_token):
    cats = request("GET", "/categories")
    cats.raise_for_status()
    data = cats.json()
    if data:
        return data[0]
    payload = {"name": "QA", "slug": f"qa-{int(time.time())}", "icon": "package", "order": 999}
    r = request("POST", "/categories", headers=auth(admin_token), json=payload)
    r.raise_for_status()
    return r.json()


def create_listing(admin_token, category_id, suffix, price=5.0):
    payload = {
        "title": f"Stripe removal QA item {suffix}",
        "description": "Temporary item created by focused Stripe-removal verification.",
        "price": price,
        "category_id": category_id,
        "condition": "good",
        "brand": "QA",
        "images": ["https://images.unsplash.com/photo-1516321318423-f06f85e504b3?w=600"],
        "shipping_paid_by": "seller",
        "shipping_method": "Standard",
    }
    r = request("POST", "/listings", headers=auth(admin_token), json=payload)
    r.raise_for_status()
    return r.json()


def main():
    print(f"API={API}")

    # Public/deployment sanity endpoints.
    root = request("GET", "/")
    record("GET /api/ root contract", root.status_code == 200 and root.json().get("message") == "Mercari Clone API" and root.json().get("status") == "ok", {"status": root.status_code, "body": root.text[:200]})

    for path in ["/sitemap_index.xml", "/robots.txt", "/wallet/ticker"]:
        r = request("GET", path)
        record(f"GET /api{path} returns 200", r.status_code == 200, {"status": r.status_code, "body": r.text[:120]})

    admin_token, admin_user = login(ADMIN)
    demo_token, demo_user = login(DEMO)
    record("Admin and demo login", bool(admin_token and demo_token), {"admin": admin_user.get("email"), "demo": demo_user.get("email")})

    # Removed Stripe Connect endpoints should be deleted.
    for method, path in [("GET", "/stripe/connect/status"), ("POST", "/stripe/connect/onboard")]:
        r = request(method, path, headers=auth(demo_token), json={} if method == "POST" else None)
        record(f"{method} /api{path} deleted", r.status_code == 404, {"status": r.status_code, "body": r.text[:200]})

    # Store boost checkout intentionally disabled.
    boost_payload = {"store_id": "qa-nonexistent", "tier": "bronze", "origin_url": "https://example.test"}
    r = request("POST", "/store-boost/checkout", headers=auth(demo_token), json=boost_payload)
    body = r.text
    record("POST /api/store-boost/checkout disabled friendly 503", r.status_code == 503 and "Paid store boosts" in body, {"status": r.status_code, "body": body[:240]})

    category = get_or_create_category(admin_token)
    balance, dep_id = ensure_wallet_balance(demo_token, admin_token, min_balance=20.0)
    record("Demo wallet has sufficient balance", balance >= 20.0, {"balance": balance, "created_deposit_id": dep_id})

    listing = create_listing(admin_token, category["id"], f"wallet-{int(time.time())}", price=5.0)
    order_payload = {
        "listing_id": listing["id"],
        "quantity": 1,
        "shipping_address": {"full_name": "Sophia QA", "street": "1 Test St", "city": "Testville", "state": "CA", "zip": "94105", "country": "USA"},
        "payment_method": "wallet",
    }
    order = request("POST", "/orders", headers=auth(demo_token), json=order_payload)
    order_ok = order.status_code == 200 and order.json().get("payment_method") == "wallet" and order.json().get("status") == "paid"
    record("Wallet checkout creates paid order", order_ok, {"status": order.status_code, "body": order.text[:500]})

    # Negative/dangling integration check: card should not remain an available backend payment path after Stripe removal.
    listing2 = create_listing(admin_token, category["id"], f"card-{int(time.time())}", price=5.0)
    card_payload = dict(order_payload, listing_id=listing2["id"], payment_method="card")
    card_order = request("POST", "/orders", headers=auth(demo_token), json=card_payload)
    record("Backend rejects removed card payment method", card_order.status_code >= 400, {"status": card_order.status_code, "body": card_order.text[:500]})

    all_ok = all(r["ok"] for r in results)
    print("RESULT_JSON=" + json.dumps({"all_ok": all_ok, "results": results}, default=str))
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())