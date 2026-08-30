#!/usr/bin/env python3
"""Focused backend verification for Apify-only catalog restore bug.

Runs against the preview backend through the public /api ingress.  This script
does not modify product code; it only exercises the documented admin restore
endpoint and catalog/listing read APIs.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List, Tuple

import requests


BASE_URL = os.environ.get("TEST_BASE_URL", "https://ocean-marketplace.preview.emergentagent.com").rstrip("/")
OUT_PATH = "/app/test_reports/bug_verification_45_runtime_results.json"

ADMIN_EMAIL = "admin@mercari.local"
ADMIN_PASSWORD = "admin123"
USER_EMAIL = "sophia_style@demo.local"
USER_PASSWORD = "demo1234"

CANONICAL_SLUGS = {"women", "men", "kids", "electronics", "home", "beauty", "sports", "toys", "books", "handmade"}
EXOTIC_SLUGS = {
    "vintage", "shoes", "bags-accessories", "jewelry-watches", "pet-supplies",
    "automotive", "musical-instruments", "office-craft", "collectibles", "Jewelry",
    "jewelry", "other", "garden-outdoor",
}


class Recorder:
    def __init__(self) -> None:
        self.results: List[Dict[str, Any]] = []

    def check(self, name: str, passed: bool, details: Dict[str, Any] | None = None) -> None:
        row = {"name": name, "passed": bool(passed), "details": details or {}}
        self.results.append(row)
        status = "PASS" if passed else "FAIL"
        print(f"[{status}] {name}: {json.dumps(row['details'], default=str)[:1000]}")

    @property
    def failed(self) -> List[Dict[str, Any]]:
        return [r for r in self.results if not r["passed"]]


rec = Recorder()
session = requests.Session()


def api(method: str, path: str, token: str | None = None, **kwargs: Any) -> Tuple[int, Any]:
    headers = kwargs.pop("headers", {}) or {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    url = f"{BASE_URL}{path}"
    response = session.request(method, url, headers=headers, timeout=45, **kwargs)
    try:
        payload: Any = response.json()
    except Exception:
        payload = response.text
    return response.status_code, payload


def login(email: str, password: str) -> Tuple[str | None, int, Any]:
    status, payload = api("POST", "/api/auth/login", json={"email": email, "password": password})
    token = payload.get("token") if isinstance(payload, dict) else None
    return token, status, payload


def summarize_counts(final_counts: Dict[str, int] | None) -> Dict[str, int] | None:
    if not isinstance(final_counts, dict):
        return None
    return {k: int(v) for k, v in sorted(final_counts.items())}


def verify_categories(label: str) -> Tuple[bool, List[Dict[str, Any]]]:
    status, cats = api("GET", "/api/categories")
    ok_payload = status == 200 and isinstance(cats, list)
    if not ok_payload:
        rec.check(f"{label}: GET /api/categories returns list", False, {"status": status, "payload": cats})
        return False, []
    slugs = [c.get("slug") for c in cats]
    slug_set = set(slugs)
    passed = len(cats) == 10 and slug_set == CANONICAL_SLUGS and slug_set.isdisjoint(EXOTIC_SLUGS)
    rec.check(
        f"{label}: exactly 10 Apify canonical categories and no exotic slugs",
        passed,
        {"status": status, "count": len(cats), "slugs": slugs, "unexpected": sorted(slug_set - CANONICAL_SLUGS)},
    )
    return passed, cats


def verify_category_browse(cats: List[Dict[str, Any]], label: str) -> bool:
    all_ok = True
    per_cat: Dict[str, Dict[str, Any]] = {}
    for cat in cats:
        cid = cat.get("id")
        slug = cat.get("slug")
        expected_name = cat.get("name")
        status, listings = api("GET", f"/api/listings?category_id={cid}&limit=500")
        list_ok = status == 200 and isinstance(listings, list)
        count = len(listings) if isinstance(listings, list) else None
        sample = listings[:5] if isinstance(listings, list) else []
        sample_mismatches = [
            {
                "id": item.get("id"),
                "category_id": item.get("category_id"),
                "category_name": item.get("category_name"),
            }
            for item in sample
            if item.get("category_id") != cid or item.get("category_name") != expected_name
        ]
        cat_ok = list_ok and count is not None and count >= 1 and not sample_mismatches
        all_ok = all_ok and cat_ok
        per_cat[slug] = {
            "status": status,
            "returned_count_limited_to_500": count,
            "sample_size": len(sample),
            "sample_mismatches": sample_mismatches,
        }
    rec.check(f"{label}: every canonical category browses with >=1 listing and matching primary category", all_ok, per_cat)
    return all_ok


def main() -> int:
    print(f"Running Apify-only catalog verification against {BASE_URL}")

    # Public catalog proof before invoking the admin restore endpoint again.
    initial_categories_ok, cats = verify_categories("Initial state")
    if cats:
        verify_category_browse(cats, "Initial state")

    status, feed = api("GET", "/api/listings")
    feed_count = len(feed) if isinstance(feed, list) else None
    rec.check("Default feed remains populated (>=60 listings)", status == 200 and isinstance(feed, list) and feed_count >= 60, {"status": status, "count": feed_count})

    status, sample = api("GET", "/api/listings?limit=100")
    sample_items = sample[:20] if isinstance(sample, list) else []
    bad_secondary = [
        {"id": item.get("id"), "secondary_categories": item.get("secondary_categories")}
        for item in sample_items
        if item.get("secondary_categories") != []
    ]
    rec.check(
        "Secondary categories cleared in first 20 listings from /api/listings?limit=100",
        status == 200 and isinstance(sample, list) and len(sample_items) == 20 and not bad_secondary,
        {"status": status, "sample_size": len(sample_items), "bad_secondary": bad_secondary},
    )

    # Authentication and authorization guard checks.
    admin_token, admin_status, admin_payload = login(ADMIN_EMAIL, ADMIN_PASSWORD)
    rec.check(
        "Admin credentials can login for restore/sync endpoints",
        bool(admin_token) and admin_status == 200,
        {"status": admin_status, "user": (admin_payload.get("user") if isinstance(admin_payload, dict) else None), "payload_type": type(admin_payload).__name__},
    )

    user_token, user_status, user_payload = login(USER_EMAIL, USER_PASSWORD)
    rec.check(
        "Regular user credentials can login for non-admin guard check",
        bool(user_token) and user_status == 200,
        {"status": user_status, "user": (user_payload.get("user") if isinstance(user_payload, dict) else None), "payload_type": type(user_payload).__name__},
    )

    no_auth_status, no_auth_payload = api("POST", "/api/admin/catalog/restore-apify-only", json={})
    rec.check(
        "Restore endpoint rejects missing bearer token with 401/403",
        no_auth_status in (401, 403),
        {"status": no_auth_status, "payload": no_auth_payload},
    )

    if user_token:
        regular_status, regular_payload = api("POST", "/api/admin/catalog/restore-apify-only", token=user_token, json={})
        rec.check(
            "Restore endpoint rejects non-admin bearer token with 403",
            regular_status == 403,
            {"status": regular_status, "payload": regular_payload},
        )
    else:
        rec.check("Restore endpoint rejects non-admin bearer token with 403", False, {"blocked_by": "regular login failed"})

    first_restore_payload: Any = None
    second_restore_payload: Any = None
    if admin_token:
        first_status, first_restore_payload = api("POST", "/api/admin/catalog/restore-apify-only", token=admin_token, json={})
        second_status, second_restore_payload = api("POST", "/api/admin/catalog/restore-apify-only", token=admin_token, json={})
        first_counts = summarize_counts(first_restore_payload.get("final_counts") if isinstance(first_restore_payload, dict) else None)
        second_counts = summarize_counts(second_restore_payload.get("final_counts") if isinstance(second_restore_payload, dict) else None)
        second_zero = isinstance(second_restore_payload, dict) and all([
            second_restore_payload.get("secondary_categories_cleared") == 0,
            second_restore_payload.get("orphan_listings_deleted") == 0,
            second_restore_payload.get("exotic_categories_dropped") == [],
            second_restore_payload.get("exotic_listings_deleted") == 0,
            second_restore_payload.get("empty_categories_removed") == [],
        ])
        rec.check(
            "Restore endpoint idempotency: two admin calls succeed and second call is no-op with identical counts",
            first_status == 200 and second_status == 200 and second_zero and first_counts == second_counts and (
                isinstance(first_restore_payload, dict)
                and isinstance(second_restore_payload, dict)
                and first_restore_payload.get("total_active_listings") == second_restore_payload.get("total_active_listings")
            ),
            {
                "first_status": first_status,
                "second_status": second_status,
                "first_payload": first_restore_payload,
                "second_payload": second_restore_payload,
                "first_counts": first_counts,
                "second_counts": second_counts,
            },
        )

        sync_status, sync_payload = api("GET", "/api/admin/sync/status", token=admin_token)
        rec.check(
            "Admin sync status succeeds and reports sync_running:false",
            sync_status == 200 and isinstance(sync_payload, dict) and sync_payload.get("sync_running") is False,
            {"status": sync_status, "payload": sync_payload},
        )
    else:
        rec.check("Restore endpoint idempotency: two admin calls succeed and second call is no-op with identical counts", False, {"blocked_by": "admin login failed"})
        rec.check("Admin sync status succeeds and reports sync_running:false", False, {"blocked_by": "admin login failed"})

    # Public catalog proof after the required idempotency calls.
    final_categories_ok, final_cats = verify_categories("Final state after restore re-runs")
    if final_cats:
        verify_category_browse(final_cats, "Final state after restore re-runs")

    output = {
        "base_url": BASE_URL,
        "initial_categories_ok": initial_categories_ok,
        "final_categories_ok": final_categories_ok,
        "results": rec.results,
        "failed": rec.failed,
        "first_restore_payload": first_restore_payload,
        "second_restore_payload": second_restore_payload,
    }
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as fh:
        json.dump(output, fh, indent=2, default=str)
    print(f"Wrote runtime results to {OUT_PATH}")
    return 1 if rec.failed else 0


if __name__ == "__main__":
    sys.exit(main())