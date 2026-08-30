#!/usr/bin/env python3
"""Focused backend/API verification for Zyte removal + Apify listings limits."""
import json
import os
import sys
from pathlib import Path

import requests


API_BASE = os.environ.get("TEST_API_BASE", "https://ocean-marketplace.preview.emergentagent.com/api").rstrip("/")


def record(results, name, ok, detail):
    results.append({"name": name, "ok": bool(ok), "detail": detail})
    print(f"{'PASS' if ok else 'FAIL'} {name}: {detail}")


def body_text(resp):
    try:
        return json.dumps(resp.json(), sort_keys=True)[:500]
    except Exception:
        return resp.text[:500]


def get_json(path, **kwargs):
    r = requests.get(f"{API_BASE}{path}", timeout=30, **kwargs)
    return r, r.json() if r.headers.get("content-type", "").startswith("application/json") else None


def main():
    results = []

    # Zyte scraper endpoint deprecation: check paths, trailing slash, and methods.
    scraper_cases = [
        ("GET", "/scraper/anything"),
        ("GET", "/scraper/anything/"),
        ("GET", "/scraper/"),
        ("GET", "/scraper"),
        ("POST", "/scraper/anything"),
        ("PUT", "/scraper/anything"),
        ("DELETE", "/scraper/anything"),
    ]
    for method, path in scraper_cases:
        resp = requests.request(method, f"{API_BASE}{path}", timeout=30, allow_redirects=False)
        text = body_text(resp)
        ok = resp.status_code == 410 and "Zyte scraper endpoints have been removed" in text and "Apify" in text
        record(results, f"scraper_{method}_{path}", ok, f"status={resp.status_code}, body={text}")

    # Public marketplace/listings limits.
    for limit, expected in [(10, 10), (300, 300), (500, 500), (600, 500)]:
        resp, data = get_json(f"/listings?limit={limit}")
        count = len(data) if isinstance(data, list) else -1
        ok = resp.status_code == 200 and count == expected
        record(results, f"listings_limit_{limit}", ok, f"status={resp.status_code}, count={count}, expected={expected}")

    resp, data = get_json("/listings")
    default_count = len(data) if isinstance(data, list) else -1
    record(results, "listings_default_60", resp.status_code == 200 and default_count >= 60, f"status={resp.status_code}, count={default_count}")

    # Category filters: pick first 3 categories with listings and ensure high limit returns at least 20.
    cats_resp, cats = get_json("/categories")
    cat_checked = 0
    if cats_resp.status_code == 200 and isinstance(cats, list):
        for cat in cats:
            cid = cat.get("id")
            if not cid:
                continue
            resp, items = get_json(f"/listings?category_id={cid}&limit=200")
            count = len(items) if isinstance(items, list) else -1
            if count > 0:
                cat_checked += 1
                record(results, f"category_filter_{cat.get('slug') or cid}", resp.status_code == 200 and count >= 20, f"status={resp.status_code}, count={count}, category_id={cid}")
            if cat_checked >= 3:
                break
    record(results, "category_filter_three_categories_found", cat_checked >= 3, f"checked={cat_checked}")

    # Admin sync status.
    login = requests.post(f"{API_BASE}/auth/login", json={"email": "admin@mercari.local", "password": "admin123"}, timeout=30)
    token = None
    if login.status_code == 200:
        token = login.json().get("token")
    record(results, "admin_login", login.status_code == 200 and bool(token), f"status={login.status_code}")
    if token:
        status_resp, status_data = get_json("/admin/sync/status", headers={"Authorization": f"Bearer {token}"})
        ok = (
            status_resp.status_code == 200
            and isinstance(status_data, dict)
            and status_data.get("sync_running") is False
            and int(status_data.get("imported_count") or 0) > 0
            and isinstance(status_data.get("per_category"), dict)
            and len(status_data.get("per_category") or {}) > 0
        )
        record(results, "admin_sync_status", ok, f"status={status_resp.status_code}, data={json.dumps(status_data, default=str)[:700] if status_data else body_text(status_resp)}")

    # Direct DB sanity check: active marketplace rows should be Apify-sourced, not legacy Zyte URL imports.
    try:
        from pymongo import MongoClient
        from dotenv import dotenv_values
        env = dotenv_values("/app/backend/.env")
        mongo_url = env.get("MONGO_URL") or os.environ.get("MONGO_URL")
        db_name = env.get("DB_NAME") or os.environ.get("DB_NAME")
        client = MongoClient(mongo_url, serverSelectionTimeoutMS=10000)
        db = client[db_name]
        active_total = db.listings.count_documents({"status": "active"})
        active_apify = db.listings.count_documents({"status": "active", "apify_asin": {"$exists": True, "$ne": None}})
        active_legacy_source = db.listings.count_documents({"status": "active", "source_url": {"$exists": True, "$nin": [None, ""]}, "apify_asin": {"$exists": False}})
        ok = active_total >= 500 and active_apify >= 500 and active_legacy_source == 0
        record(results, "db_active_listings_apify_only", ok, f"active_total={active_total}, active_apify={active_apify}, active_legacy_source_without_apify={active_legacy_source}")
        legacy = db.listings.find_one(
            {"status": "active", "source_url": {"$exists": True, "$nin": [None, ""]}},
            {"_id": 0, "id": 1, "title": 1, "source_url": 1},
        )
        if legacy and legacy.get("title"):
            q_resp, q_items = get_json(f"/listings?q={requests.utils.quote(legacy['title'])}&limit=10")
            found_ids = [it.get("id") for it in q_items] if isinstance(q_items, list) else []
            record(
                results,
                "legacy_source_listing_not_searchable",
                legacy.get("id") not in found_ids,
                f"legacy_id={legacy.get('id')}, title={legacy.get('title')!r}, api_search_count={len(found_ids)}, found_in_api={legacy.get('id') in found_ids}",
            )
    except Exception as e:
        record(results, "db_active_listings_apify_only", False, f"DB check failed: {type(e).__name__}: {e}")

    out = {
        "api_base": API_BASE,
        "results": results,
        "passed": sum(1 for r in results if r["ok"]),
        "failed": sum(1 for r in results if not r["ok"]),
    }
    out_path = Path("/app/test_reports/bug_verification_41_backend_results.json")
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    return 0 if out["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())