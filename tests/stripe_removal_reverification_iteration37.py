#!/usr/bin/env python3
"""Iteration 37 focused Stripe-removal re-verification.

Scope only covers the reported deployment blocker:
- removed Stripe/card payment paths reject at validation layer
- store-boost paid checkout disabled
- deploy-sanity endpoints still respond
- wallet checkout still creates a paid order
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
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

results: list[dict] = []


def record(name: str, ok: bool, details: dict | None = None) -> None:
    row = {"name": name, "ok": bool(ok), "details": details or {}}
    results.append(row)
    print(("PASS" if ok else "FAIL") + " - " + name + ": " + json.dumps(row["details"], default=str))


def req(method: str, path: str, **kwargs) -> requests.Response:
    return requests.request(method, API + path, timeout=45, **kwargs)


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def login(creds: dict) -> tuple[str, dict]:
    r = req("POST", "/auth/login", json=creds)
    r.raise_for_status()
    data = r.json()
    return data["token"], data["user"]


def get_or_create_category(admin_token: str) -> dict:
    r = req("GET", "/categories")
    r.raise_for_status()
    cats = r.json()
    if cats:
        return cats[0]
    payload = {"name": "QA", "slug": f"qa-{int(time.time())}", "icon": "package", "order": 999}
    r = req("POST", "/categories", headers=auth(admin_token), json=payload)
    r.raise_for_status()
    return r.json()


def create_listing(admin_token: str, category_id: str, label: str, price: float = 5.0) -> dict:
    payload = {
        "title": f"Stripe removal reverification {label} {uuid.uuid4().hex[:8]}",
        "description": "Temporary listing created by focused Stripe-removal QA.",
        "price": price,
        "category_id": category_id,
        "condition": "good",
        "brand": "QA",
        "images": ["https://images.unsplash.com/photo-1516321318423-f06f85e504b3?w=600"],
        "shipping_paid_by": "seller",
        "shipping_method": "Standard",
    }
    r = req("POST", "/listings", headers=auth(admin_token), json=payload)
    r.raise_for_status()
    return r.json()


def ensure_wallet_balance(user_token: str, admin_token: str, min_balance: float = 20.0) -> float:
    r = req("GET", "/wallet", headers=auth(user_token))
    r.raise_for_status()
    balance = float(r.json().get("balance") or 0)
    if balance >= min_balance:
        return balance
    dep_payload = {
        "amount": min_balance,
        "method": "manual",
        "currency": "bank_transfer",
        "reference": f"stripe-removal-reverify-{uuid.uuid4().hex[:10]}",
        "note": "QA wallet checkout funding",
    }
    dep = req("POST", "/wallet/deposit", headers=auth(user_token), json=dep_payload)
    dep.raise_for_status()
    approve = req("POST", f"/admin/deposits/{dep.json()['id']}/approve", headers=auth(admin_token))
    approve.raise_for_status()
    r2 = req("GET", "/wallet", headers=auth(user_token))
    r2.raise_for_status()
    return float(r2.json().get("balance") or 0)


def make_verified_user() -> tuple[str, str]:
    suffix = uuid.uuid4().hex[:10]
    email = f"e2e_stripe_removed_{suffix}@example.com"
    password = "pass1234"
    reg = req("POST", "/auth/register", json={"email": email, "username": f"stripegone{suffix}", "password": password})
    reg.raise_for_status()
    token = reg.json()["token"]

    send_email = req("POST", "/verify/email/send", headers=auth(token), json={})
    send_email.raise_for_status()
    email_token = send_email.json().get("token")
    confirm_email = req("POST", "/verify/email/confirm", headers=auth(token), json={"token": email_token})
    confirm_email.raise_for_status()

    phone = "+1555" + str(int(time.time()))[-7:]
    send_phone = req("POST", "/verify/phone/send", headers=auth(token), json={"phone": phone})
    send_phone.raise_for_status()
    code = send_phone.json().get("code")
    confirm_phone = req("POST", "/verify/phone/confirm", headers=auth(token), json={"phone": phone, "code": code})
    confirm_phone.raise_for_status()
    return token, phone


def main() -> int:
    print(f"API={API}")

    root = req("GET", "/")
    record("GET /api/ returns 200", root.status_code == 200, {"status": root.status_code, "body": root.text[:160]})
    for path in ["/sitemap_index.xml", "/robots.txt", "/wallet/ticker"]:
        r = req("GET", path)
        record(f"GET /api{path} returns 200", r.status_code == 200, {"status": r.status_code, "body": r.text[:160]})

    admin_token, admin_user = login(ADMIN)
    demo_token, demo_user = login(DEMO)
    record("Admin and demo credentials usable", True, {"admin": admin_user.get("email"), "demo": demo_user.get("email")})

    stripe_status = req("GET", "/stripe/connect/status", headers=auth(demo_token))
    record("GET /api/stripe/connect/status returns 404", stripe_status.status_code == 404, {"status": stripe_status.status_code, "body": stripe_status.text[:200]})

    boost = req("POST", "/store-boost/checkout", headers=auth(demo_token), json={"store_id": "qa-nonexistent", "tier": "bronze", "origin_url": "https://example.test"})
    record("POST /api/store-boost/checkout returns 503", boost.status_code == 503, {"status": boost.status_code, "body": boost.text[:220]})

    category = get_or_create_category(admin_token)
    balance = ensure_wallet_balance(demo_token, admin_token, min_balance=20.0)
    record("Demo user has sufficient wallet balance", balance >= 20.0, {"balance": balance})

    address = {"full_name": "Sophia QA", "street": "1 Test St", "city": "Testville", "state": "CA", "zip": "94105", "country": "USA"}

    wallet_listing = create_listing(admin_token, category["id"], "wallet", 5.0)
    wallet_order = req("POST", "/orders", headers=auth(demo_token), json={"listing_id": wallet_listing["id"], "quantity": 1, "shipping_address": address, "payment_method": "wallet"})
    wallet_ok = wallet_order.status_code == 200 and wallet_order.json().get("payment_method") == "wallet" and wallet_order.json().get("status") == "paid"
    record("POST /api/orders wallet creates paid order", wallet_ok, {"status": wallet_order.status_code, "body": wallet_order.text[:500]})

    card_listing = create_listing(admin_token, category["id"], "card-negative", 5.0)
    card_order = req("POST", "/orders", headers=auth(demo_token), json={"listing_id": card_listing["id"], "quantity": 1, "shipping_address": address, "payment_method": "card"})
    record("POST /api/orders card returns exact 422 validation error", card_order.status_code == 422, {"status": card_order.status_code, "body": card_order.text[:600]})

    seller_token, phone = make_verified_user()
    seller_payload = {
        "legal_name": "Stripe Removed QA",
        "business_name": "",
        "business_type": "individual",
        "tax_id": "1234",
        "country": "US",
        "address_line1": "1 Test St",
        "address_line2": "",
        "city": "Testville",
        "state": "CA",
        "postal_code": "94105",
        "phone": phone,
        "payout_method": "stripe_connect",
        "id_document_note": "negative test",
    }
    seller_apply = req("POST", "/seller/apply", headers=auth(seller_token), json=seller_payload)
    record("POST /api/seller/apply stripe_connect returns exact 422 validation error", seller_apply.status_code == 422, {"status": seller_apply.status_code, "body": seller_apply.text[:600]})

    summary = {"all_ok": all(r["ok"] for r in results), "results": results}
    print("RESULT_JSON=" + json.dumps(summary, default=str))
    return 0 if summary["all_ok"] else 1


if __name__ == "__main__":
    sys.exit(main())