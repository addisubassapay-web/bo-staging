#!/usr/bin/env python3
"""Focused iteration 27 regression setup/API verification.

Scope:
- Marketplace hygiene after test-listing cleanup.
- Seed temporary buyers for Cart/Checkout mobile fit UI measurement.

This script intentionally does not edit product code.
"""
import json
import os
import re
import time
from pathlib import Path

import requests
from dotenv import load_dotenv
from pymongo import MongoClient


ROOT = Path("/app")
FRONTEND_ENV = ROOT / "frontend" / ".env"
BACKEND_ENV = ROOT / "backend" / ".env"
OUT = ROOT / "test_reports" / "iteration_27_runtime_api.json"

BAD_TITLE_RE = re.compile(r"^(TEST_|test_)|Follow Notif Test")
DEMO_SELLERS = {"sophia_style", "urban_finds", "vintage_maven", "tech_haven", "cozy_home"}


def read_backend_url() -> str:
    for line in FRONTEND_ENV.read_text().splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            return line.split("=", 1)[1].strip().rstrip("/")
    return os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")


BASE = read_backend_url()
API = f"{BASE}/api"


def req(method: str, path: str, **kwargs):
    url = f"{API}{path}"
    r = requests.request(method, url, timeout=30, **kwargs)
    if r.status_code >= 400:
        raise RuntimeError(f"{method} {path} -> {r.status_code}: {r.text[:500]}")
    return r.json() if r.content else None


def fetch_listings(params=None, max_pages=20):
    params = dict(params or {})
    out = []
    limit = min(int(params.pop("limit", 96)), 96)
    for page in range(max_pages):
        batch = req("GET", "/listings", params={**params, "limit": limit, "skip": page * limit})
        out.extend(batch)
        if len(batch) < limit:
            break
    return out


def bad_title_items(items):
    bad = []
    for item in items:
        title = item.get("title") or ""
        if BAD_TITLE_RE.search(title):
            bad.append({
                "id": item.get("id"),
                "title": title,
                "seller_name": item.get("seller_name"),
                "status": item.get("status"),
            })
    return bad


def non_demo_seller_items(items):
    return [
        {"id": x.get("id"), "title": x.get("title"), "seller_name": x.get("seller_name"), "status": x.get("status")}
        for x in items
        if x.get("seller_name") not in DEMO_SELLERS
    ]


def missing_apify_items(items):
    missing = []
    for item in items:
        if not item.get("apify_asin") and not item.get("apify_url"):
            missing.append({"id": item.get("id"), "title": item.get("title"), "seller_name": item.get("seller_name")})
    return missing


def register(prefix: str) -> dict:
    ts = int(time.time() * 1000)
    payload = {
        "email": f"{prefix}.{ts}@example.com",
        "username": f"{prefix.replace('.', '')}{ts % 1000000000}",
        "password": "pass1234",
    }
    data = req("POST", "/auth/register", json=payload)
    return {"payload": payload, "token": data["token"], "user": data["user"]}


def login(email: str, password: str) -> dict:
    data = req("POST", "/auth/login", json={"email": email, "password": password})
    return {"token": data["token"], "user": data["user"]}


def mongo_hygiene():
    load_dotenv(BACKEND_ENV)
    client = MongoClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    regex = {"$regex": r"^(TEST_|test_)|Follow Notif Test"}
    docs = list(db.listings.find({"title": regex}, {"_id": 0, "id": 1, "title": 1, "status": 1, "seller_name": 1}).limit(200))
    counts = {
        "active": db.listings.count_documents({"status": "active"}),
        "all": db.listings.count_documents({}),
        "sold": db.listings.count_documents({"status": "sold"}),
        "bad_title_all_statuses": len(docs),
    }
    return {"counts": counts, "bad_title_all_statuses": docs}


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)

    counts = {
        "active": req("GET", "/listings/count").get("total"),
        "all": req("GET", "/listings/count", params={"status_filter": ""}).get("total"),
        "sold": req("GET", "/listings/count", params={"status_filter": "sold"}).get("total"),
    }
    active_listings = fetch_listings({})
    all_listings = fetch_listings({"status_filter": ""})

    search_checks = {
        "q_TEST": fetch_listings({"q": "TEST"}),
        "q_test_lower": fetch_listings({"q": "test"}),
        "q_Follow_Notif_Test": fetch_listings({"q": "Follow Notif Test"}),
    }

    featured = fetch_listings({"featured": "true"})
    categories = req("GET", "/categories")
    category_checks = []
    for cat in categories:
        docs = fetch_listings({"category_id": cat.get("id")}, max_pages=10)
        category_checks.append({
            "category": cat.get("slug") or cat.get("name") or cat.get("id"),
            "count": len(docs),
            "bad_title": bad_title_items(docs),
            "non_demo_sellers": non_demo_seller_items(docs),
        })

    stores_featured = []
    store_checks = []
    try:
        stores_featured = req("GET", "/stores-featured")
        for store in stores_featured:
            slug = store.get("slug")
            if not slug:
                continue
            docs = req("GET", f"/stores/{slug}/listings")
            store_checks.append({
                "slug": slug,
                "count": len(docs),
                "bad_title": bad_title_items(docs),
                "non_demo_sellers": non_demo_seller_items(docs),
            })
    except Exception as exc:
        store_checks.append({"error": str(exc)})

    # Seed minimal data for browser mobile-fit verification.
    if not active_listings:
        raise RuntimeError("No active listings available for cart/checkout mobile test")
    selected = sorted(active_listings, key=lambda x: (len(x.get("title", "")), float(x.get("price", 0))), reverse=True)[:2]
    buyer = register("iter27.mobile.buyer")
    empty_buyer = register("iter27.mobile.empty")
    headers = {"Authorization": f"Bearer {buyer['token']}"}
    for listing in selected:
        req("POST", f"/cart/{listing['id']}", headers=headers)
    cart = req("GET", "/cart", headers=headers)
    pay_methods = req("GET", "/wallet/payment-methods", headers=headers)

    admin_login = None
    try:
        admin_login = login("admin@mercari.local", "admin123")
    except Exception as exc:
        admin_login = {"error": str(exc)}

    report = {
        "backend_url": BASE,
        "frontend_url": "http://localhost:3000",
        "counts": counts,
        "active_listings_sampled": len(active_listings),
        "all_listings_sampled": len(all_listings),
        "bad_title_active": bad_title_items(active_listings),
        "bad_title_all_statuses": bad_title_items(all_listings),
        "non_demo_sellers_active": non_demo_seller_items(active_listings),
        "missing_apify_active": missing_apify_items(active_listings),
        "search_checks": {k: {"count": len(v), "bad_title": bad_title_items(v), "titles": [x.get("title") for x in v[:20]]} for k, v in search_checks.items()},
        "featured_check": {"count": len(featured), "bad_title": bad_title_items(featured), "non_demo_sellers": non_demo_seller_items(featured)},
        "category_checks": category_checks,
        "store_checks": store_checks,
        "mongo_hygiene": mongo_hygiene(),
        "selected_listings": [{"id": x.get("id"), "title": x.get("title"), "price": x.get("price"), "seller_name": x.get("seller_name")} for x in selected],
        "buyer": buyer,
        "empty_buyer": empty_buyer,
        "admin_login_ok": bool(admin_login and not admin_login.get("error")),
        "cart_count_after_add": len(cart),
        "payment_methods_summary": {
            "crypto_assets": len(pay_methods.get("crypto_assets", [])),
            "crypto_addresses": sorted(list((pay_methods.get("crypto_addresses") or {}).keys())),
            "manual_payment_methods": len(pay_methods.get("manual_payment_methods", [])),
        },
    }
    OUT.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()