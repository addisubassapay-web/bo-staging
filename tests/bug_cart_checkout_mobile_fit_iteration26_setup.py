#!/usr/bin/env python3
"""Focused setup/API checks for Cart + Checkout mobile clipping regression.

Creates fresh gmail-domain buyers, adds real listings to one cart, and records
marketplace listing-count/seller hygiene evidence used by the browser test.
"""
import json
import os
import re
import time
from pathlib import Path

import requests


ROOT = Path("/app")
FRONTEND_ENV = ROOT / "frontend" / ".env"
OUT = ROOT / "test_reports" / "iteration_26_runtime_setup.json"


def read_backend_url() -> str:
    for line in FRONTEND_ENV.read_text().splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            return line.split("=", 1)[1].strip().rstrip("/")
    return os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")


BASE = read_backend_url()
API = f"{BASE}/api"


def req(method, path, **kwargs):
    url = f"{API}{path}"
    r = requests.request(method, url, timeout=30, **kwargs)
    if r.status_code >= 400:
        raise RuntimeError(f"{method} {path} -> {r.status_code}: {r.text[:500]}")
    return r.json() if r.content else None


def register(prefix: str) -> dict:
    ts = int(time.time() * 1000)
    payload = {
        "email": f"{prefix}.{ts}@gmail.com",
        "username": f"{prefix.replace('.', '')}{ts % 1000000000}",
        "password": "pass1234",
    }
    data = req("POST", "/auth/register", json=payload)
    return {"payload": payload, "token": data["token"], "user": data["user"]}


def fetch_listings(params=None, max_pages=5):
    params = dict(params or {})
    out = []
    limit = min(int(params.pop("limit", 96)), 96)
    for page in range(max_pages):
        batch = req("GET", "/listings", params={**params, "limit": limit, "skip": page * limit})
        out.extend(batch)
        if len(batch) < limit:
            break
    return out


def bad_listing_sellers(listings):
    bad = []
    whitelist = {"sophia_style", "urban_finds", "vintage_maven", "tech_haven", "cozy_home"}
    bad_pat = re.compile(r"(test|e2e|qa|dummy|sample)", re.I)
    for item in listings:
        seller = item.get("seller_name", "")
        if seller not in whitelist or bad_pat.search(seller) or bad_pat.search(item.get("title", "")):
            bad.append({"id": item.get("id"), "title": item.get("title"), "seller_name": seller})
    return bad


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)

    counts = {
        "active": req("GET", "/listings/count").get("total"),
        "all": req("GET", "/listings/count", params={"status_filter": ""}).get("total"),
        "sold": req("GET", "/listings/count", params={"status_filter": "sold"}).get("total"),
    }

    all_listings = fetch_listings({"status_filter": ""}, max_pages=4)
    active_listings = fetch_listings({}, max_pages=4)
    if not active_listings:
        raise RuntimeError("No active listings available for cart/checkout test")

    # Stress with long titles/high prices where possible.
    selected = sorted(active_listings, key=lambda x: (len(x.get("title", "")), float(x.get("price", 0))), reverse=True)[:2]

    buyer = register("mobile.fit.buyer")
    empty_buyer = register("mobile.fit.empty")
    headers = {"Authorization": f"Bearer {buyer['token']}"}
    for listing in selected:
        req("POST", f"/cart/{listing['id']}", headers=headers)
    cart = req("GET", "/cart", headers=headers)

    pay_methods = req("GET", "/wallet/payment-methods", headers=headers)

    categories = req("GET", "/categories")
    category_samples = []
    for cat in categories[:20]:
        docs = fetch_listings({"category_id": cat.get("id")}, max_pages=1)
        if docs:
            category_samples.append({"category": cat.get("slug") or cat.get("name"), "count_sampled": len(docs), "bad": bad_listing_sellers(docs[:20])})

    featured = fetch_listings({"featured": "true"}, max_pages=1)

    stores_featured = []
    try:
        stores_featured = req("GET", "/stores-featured")
    except Exception as exc:  # keep this evidence but do not block the mobile UI test
        stores_featured = [{"error": str(exc)}]
    store_samples = []
    for store in stores_featured[:10] if isinstance(stores_featured, list) else []:
        slug = store.get("slug")
        if not slug:
            continue
        try:
            docs = req("GET", f"/stores/{slug}/listings")
            store_samples.append({"slug": slug, "count": len(docs), "bad": bad_listing_sellers(docs[:50])})
        except Exception as exc:
            store_samples.append({"slug": slug, "error": str(exc)})

    report = {
        "backend_url": BASE,
        "frontend_url": "http://localhost:3000",
        "counts": counts,
        "all_listings_sampled": len(all_listings),
        "active_listings_sampled": len(active_listings),
        "bad_sellers_all": bad_listing_sellers(all_listings),
        "bad_sellers_active": bad_listing_sellers(active_listings),
        "bad_sellers_featured": bad_listing_sellers(featured),
        "category_samples": category_samples,
        "store_samples": store_samples,
        "selected_listings": [{"id": x.get("id"), "title": x.get("title"), "price": x.get("price"), "seller_name": x.get("seller_name")} for x in selected],
        "buyer": buyer,
        "empty_buyer": empty_buyer,
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