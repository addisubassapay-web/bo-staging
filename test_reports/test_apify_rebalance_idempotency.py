#!/usr/bin/env python3
"""Focused retest for Apify-scraped product category rebalance idempotency.

This script intentionally exercises only the reported bug flow:
- admin-only POST /api/admin/listings/rebalance
- category visibility via primary or secondary categories
- no new listing rows after repeated rebalance calls
- sync status remains idle
"""
from __future__ import annotations

import json
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import requests


BASE_URL = os.environ.get("TEST_BASE_URL", "https://bo-staging.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
OUT = "/app/test_reports/apify_rebalance_idempotency_results.json"


def request(method: str, path: str, token: Optional[str] = None, **kwargs) -> requests.Response:
    headers = kwargs.pop("headers", {}) or {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return requests.request(method, f"{API}{path}", headers=headers, timeout=90, **kwargs)


def check(condition: bool, name: str, failures: List[Dict[str, Any]], details: Any = None) -> None:
    print(("PASS" if condition else "FAIL") + f" - {name}" + (f": {details}" if details is not None else ""))
    if not condition:
        failures.append({"check": name, "details": details})


def login(email: str, password: str) -> Tuple[str, Dict[str, Any]]:
    r = request("POST", "/auth/login", json={"email": email, "password": password})
    r.raise_for_status()
    body = r.json()
    return body["token"], body.get("user") or {}


def admin_active_count(token: str) -> Tuple[int, List[Dict[str, Any]]]:
    r = request("GET", "/admin/listings?status_filter=active", token=token)
    r.raise_for_status()
    items = r.json()
    return len(items), items


def active_count_from_status(token: str) -> int:
    r = request("GET", "/admin/sync/status", token=token)
    r.raise_for_status()
    return int(r.json().get("active_listings") or 0)


def rebalance(token: str, min_per_category: int, clear_sync_flag: bool = True) -> Tuple[int, Dict[str, Any]]:
    r = request(
        "POST",
        "/admin/listings/rebalance",
        token=token,
        json={"min_per_category": min_per_category, "clear_sync_flag": clear_sync_flag},
    )
    try:
        body = r.json()
    except Exception:
        body = {"raw": r.text[:1000]}
    return r.status_code, body


def counts_visible_by_category(categories: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for cat in categories:
        r = request("GET", f"/listings?category_id={cat['id']}&limit=96")
        r.raise_for_status()
        counts[cat["slug"]] = len(r.json())
    return counts


def find_secondary_filter_case(categories: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    for cat in categories:
        r = request("GET", f"/listings?category_id={cat['id']}&limit=96")
        r.raise_for_status()
        items = r.json()
        all_match = all((it.get("category_id") == cat["id"]) or (cat["id"] in (it.get("secondary_categories") or [])) for it in items)
        secondary_items = [it for it in items if it.get("category_id") != cat["id"] and cat["id"] in (it.get("secondary_categories") or [])]
        if secondary_items:
            sample = secondary_items[0]
            return {
                "category_slug": cat.get("slug"),
                "category_id": cat.get("id"),
                "result_count": len(items),
                "all_results_match_primary_or_secondary": all_match,
                "secondary_match_listing_id": sample.get("id"),
                "secondary_match_title": sample.get("title"),
                "secondary_match_primary_category_id": sample.get("category_id"),
                "secondary_categories": sample.get("secondary_categories") or [],
            }
    return None


def main() -> int:
    failures: List[Dict[str, Any]] = []
    evidence: Dict[str, Any] = {
        "base_url": BASE_URL,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    print(f"Focused Apify rebalance idempotency retest against {API}")
    admin_token, admin_user = login("admin@mercari.local", "admin123")
    evidence["admin_user"] = {"email": admin_user.get("email"), "role": admin_user.get("role")}
    user_token, user = login("sophia_style@demo.local", "demo1234")
    evidence["regular_user"] = {"email": user.get("email"), "role": user.get("role")}

    # Auth guard checks.
    unauth = request("POST", "/admin/listings/rebalance", json={"min_per_category": 20, "clear_sync_flag": True})
    evidence["unauth_rebalance_status"] = unauth.status_code
    check(unauth.status_code in (401, 403), "rebalance rejects unauthenticated caller", failures, unauth.status_code)

    non_admin = request("POST", "/admin/listings/rebalance", token=user_token, json={"min_per_category": 20, "clear_sync_flag": True})
    evidence["non_admin_rebalance_status"] = non_admin.status_code
    check(non_admin.status_code == 403, "rebalance rejects non-admin caller with 403", failures, non_admin.status_code)

    cats_r = request("GET", "/categories")
    cats_r.raise_for_status()
    categories = cats_r.json()
    evidence["categories"] = [{"slug": c.get("slug"), "id": c.get("id")} for c in categories]
    check(len(categories) >= 1, "categories are available", failures, len(categories))

    before_admin_count, before_items = admin_active_count(admin_token)
    before_status_count = active_count_from_status(admin_token)
    evidence["active_count_before_admin_listings"] = before_admin_count
    evidence["active_count_before_sync_status"] = before_status_count
    evidence["admin_listings_returned_cap_notice"] = "admin endpoint currently returns up to 2000 rows; sync status active_listings captured as a secondary count"

    # Primary idempotency retest: same threshold twice.
    status1, body1 = rebalance(admin_token, 20, True)
    status2, body2 = rebalance(admin_token, 20, True)
    evidence["rebalance_min20_first"] = {"status": status1, "body": body1}
    evidence["rebalance_min20_second"] = {"status": status2, "body": body2}
    check(status1 == 200 and body1.get("ok") is True, "first min=20 rebalance succeeds", failures, {"status": status1, "body": body1})
    check(status2 == 200 and body2.get("ok") is True, "second min=20 rebalance succeeds", failures, {"status": status2, "body": body2})

    if status2 == 200:
        second_reclassified = int(body2.get("reclassified") or 0)
        second_tagged = int(body2.get("listings_tagged") or 0)
        evidence["second_min20_reclassified"] = second_reclassified
        evidence["second_min20_listings_tagged"] = second_tagged
        check(second_reclassified == 0, "second identical rebalance reports reclassified=0", failures, second_reclassified)
        check(second_tagged < 5, "second identical rebalance reports listings_tagged <5", failures, second_tagged)
        check(second_tagged == 0, "second identical rebalance reports listings_tagged=0", failures, second_tagged)
        check(body1.get("counts_after") == body2.get("counts_after"), "counts_after unchanged between repeated min=20 calls", failures, {"first": body1.get("counts_after"), "second": body2.get("counts_after")})
        too_low_20 = {slug: count for slug, count in (body2.get("counts_after") or {}).items() if int(count) < 20}
        check(not too_low_20, "every category in counts_after has at least 20 listings after min=20", failures, too_low_20 or body2.get("counts_after"))

    after_twice_admin_count, _ = admin_active_count(admin_token)
    after_twice_status_count = active_count_from_status(admin_token)
    evidence["active_count_after_two_min20_admin_listings"] = after_twice_admin_count
    evidence["active_count_after_two_min20_sync_status"] = after_twice_status_count
    check(after_twice_admin_count == before_admin_count, "no new active listing rows after two rebalances (admin listing count unchanged)", failures, {"before": before_admin_count, "after": after_twice_admin_count})
    check(after_twice_status_count == before_status_count, "no new active listing rows after two rebalances (sync status active_listings unchanged)", failures, {"before": before_status_count, "after": after_twice_status_count})

    visible_counts = counts_visible_by_category(categories)
    evidence["visible_counts_after_two_min20_limit96"] = visible_counts
    too_low_visible = {slug: count for slug, count in visible_counts.items() if count < 20}
    check(not too_low_visible, "every category filter returns at least 20 visible listings", failures, too_low_visible or visible_counts)

    # Lower threshold edge case: lowering then raising threshold must not undo work or error.
    status10, body10 = rebalance(admin_token, 10, True)
    status15, body15 = rebalance(admin_token, 15, True)
    evidence["rebalance_min10"] = {"status": status10, "body": body10}
    evidence["rebalance_min15_after_min10"] = {"status": status15, "body": body15}
    check(status10 == 200 and body10.get("ok") is True, "min=10 rebalance succeeds", failures, {"status": status10, "body": body10})
    check(status15 == 200 and body15.get("ok") is True, "min=15 rebalance after min=10 succeeds", failures, {"status": status15, "body": body15})
    if status15 == 200:
        too_low_15 = {slug: count for slug, count in (body15.get("counts_after") or {}).items() if int(count) < 15}
        check(not too_low_15, "min=15 counts_after has every category >=15", failures, too_low_15 or body15.get("counts_after"))

    after_all_admin_count, _ = admin_active_count(admin_token)
    after_all_status_count = active_count_from_status(admin_token)
    evidence["active_count_after_all_rebalances_admin_listings"] = after_all_admin_count
    evidence["active_count_after_all_rebalances_sync_status"] = after_all_status_count
    check(after_all_admin_count == before_admin_count, "no new active listing rows after all rebalance calls (admin listing count unchanged)", failures, {"before": before_admin_count, "after": after_all_admin_count})
    check(after_all_status_count == before_status_count, "no new active listing rows after all rebalance calls (sync status active_listings unchanged)", failures, {"before": before_status_count, "after": after_all_status_count})

    # Secondary category filtering remains part of the user-visible category distribution fix.
    secondary_case = find_secondary_filter_case(categories)
    evidence["secondary_filter_case"] = secondary_case
    check(secondary_case is not None, "found at least one category result matched via secondary_categories on first limit=96 page", failures, None)
    if secondary_case:
        check(secondary_case["all_results_match_primary_or_secondary"] is True, "selected category results all match primary or secondary category id", failures, secondary_case)

    status_after = request("GET", "/admin/sync/status", token=admin_token)
    status_after.raise_for_status()
    evidence["sync_status_after_rebalances"] = status_after.json()
    check(status_after.json().get("sync_running") is False, "sync_running remains false after rebalance calls", failures, status_after.json())

    evidence["failures"] = failures
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(evidence, f, indent=2)
    print(f"Wrote {OUT}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())