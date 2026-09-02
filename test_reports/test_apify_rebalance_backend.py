#!/usr/bin/env python3
"""Focused verification for Apify listing category rebalance bug."""
import json
import os
import re
import sys
import time
from typing import Any, Dict, List, Optional

import requests


BASE_URL = os.environ.get("TEST_BASE_URL", "https://bo-staging.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
OUT = "/app/test_reports/apify_rebalance_backend_results.json"


def req(method: str, path: str, token: Optional[str] = None, **kwargs) -> requests.Response:
    headers = kwargs.pop("headers", {}) or {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return requests.request(method, f"{API}{path}", headers=headers, timeout=45, **kwargs)


def ok(cond: bool, name: str, details: Any = None, failures: Optional[List[Dict[str, Any]]] = None):
    print(("PASS" if cond else "FAIL") + f" - {name}" + (f": {details}" if details is not None else ""))
    if failures is not None and not cond:
        failures.append({"check": name, "details": details})


def login(email: str, password: str) -> str:
    r = req("POST", "/auth/login", json={"email": email, "password": password})
    r.raise_for_status()
    return r.json()["token"]


def text_matches(item: dict, term: str) -> bool:
    hay = " ".join(str(item.get(k) or "") for k in ("title", "description", "brand")).lower()
    return term.lower() in hay


def fetch_all_until(path: str, token: Optional[str] = None, max_pages: int = 30) -> List[dict]:
    out: List[dict] = []
    limit = 96
    for page in range(max_pages):
        sep = "&" if "?" in path else "?"
        r = req("GET", f"{path}{sep}limit={limit}&skip={page * limit}", token=token)
        r.raise_for_status()
        items = r.json()
        out.extend(items)
        if len(items) < limit:
            break
    return out


def main() -> int:
    failures: List[Dict[str, Any]] = []
    evidence: Dict[str, Any] = {"base_url": BASE_URL, "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}

    print(f"Testing backend against {API}")

    admin_token = login("admin@mercari.local", "admin123")
    evidence["admin_login"] = "ok"
    try:
        user_token = login("sophia_style@demo.local", "demo1234")
        evidence["seller_login"] = "ok"
    except Exception as e:
        user_token = None
        evidence["seller_login"] = f"failed: {e}"

    # Auth rejection checks before any rebalance.
    unauth = req("POST", "/admin/listings/rebalance", json={"min_per_category": 15, "clear_sync_flag": True})
    evidence["unauth_rebalance_status"] = unauth.status_code
    ok(unauth.status_code in (401, 403), "rebalance rejects unauthenticated callers", unauth.status_code, failures)
    if user_token:
        non_admin = req("POST", "/admin/listings/rebalance", token=user_token, json={"min_per_category": 15, "clear_sync_flag": True})
        evidence["non_admin_rebalance_status"] = non_admin.status_code
        ok(non_admin.status_code in (401, 403), "rebalance rejects non-admin callers", non_admin.status_code, failures)

    status_before = req("GET", "/admin/sync/status", token=admin_token)
    status_before.raise_for_status()
    evidence["status_before"] = status_before.json()
    ok(status_before.json().get("sync_running") is False, "admin sync status is not stuck running before rebalance", status_before.json(), failures)

    cats_r = req("GET", "/categories")
    cats_r.raise_for_status()
    categories = cats_r.json()
    evidence["categories"] = [{"slug": c.get("slug"), "id": c.get("id")} for c in categories]
    ok(len(categories) > 0, "categories returned", len(categories), failures)

    # Every seeded category should return at least 20 active listings through category filter.
    category_counts: Dict[str, int] = {}
    category_samples: Dict[str, List[str]] = {}
    for c in categories:
        r = req("GET", f"/listings?category_id={c['id']}&limit=96")
        r.raise_for_status()
        items = r.json()
        category_counts[c["slug"]] = len(items)
        category_samples[c["slug"]] = [it.get("title") for it in items[:3]]
        ok(len(items) >= 20, f"category {c['slug']} has >=20 visible active listings", len(items), failures)
    evidence["category_counts_limit96"] = category_counts
    evidence["category_samples"] = category_samples
    ok(len([s for s, n in category_counts.items() if n > 0]) == len(categories), "no category is empty", category_counts, failures)

    # Re-run idempotent rebalance with moderate threshold.
    rebalance = req("POST", "/admin/listings/rebalance", token=admin_token, json={"min_per_category": 15, "clear_sync_flag": True})
    evidence["rebalance_status_code"] = rebalance.status_code
    try:
        rebalance_body = rebalance.json()
    except Exception:
        rebalance_body = {"raw": rebalance.text[:500]}
    evidence["rebalance_response"] = rebalance_body
    ok(rebalance.status_code == 200 and rebalance_body.get("ok") is True, "admin rebalance endpoint succeeds", rebalance_body, failures)
    if rebalance.status_code == 200:
        ok(isinstance(rebalance_body.get("reclassified"), int), "rebalance returns integer reclassified", rebalance_body.get("reclassified"), failures)
        ok(isinstance(rebalance_body.get("duplicates_created"), int), "rebalance returns integer duplicates_created", rebalance_body.get("duplicates_created"), failures)
        ok(rebalance_body.get("sync_flag_cleared") is True, "rebalance reports sync flag cleared", rebalance_body.get("sync_flag_cleared"), failures)
        counts_after = rebalance_body.get("counts_after") or {}
        ok(bool(counts_after), "rebalance returns counts_after", counts_after, failures)
        too_low = {k: v for k, v in counts_after.items() if int(v) < 15}
        ok(not too_low, "every slug in counts_after >=15 after idempotent rebalance", too_low or counts_after, failures)
        # Because the main agent already filled >=30, a min=15 rerun should not add category top-up clones.
        ok(int(rebalance_body.get("duplicates_created", 0)) == 0, "idempotent rebalance did not create extra duplicates at min_per_category=15", rebalance_body.get("duplicates_created"), failures)

    status_after = req("GET", "/admin/sync/status", token=admin_token)
    status_after.raise_for_status()
    evidence["status_after"] = status_after.json()
    ok(status_after.json().get("sync_running") is False, "admin sync status remains sync_running=false after rebalance", status_after.json(), failures)

    # Verify secondary_categories are honored by category filter.
    all_seen = fetch_all_until("/listings?status_filter=active")
    evidence["listings_scanned_for_secondary"] = len(all_seen)
    secondary_case = None
    for item in all_seen:
        secs = item.get("secondary_categories") or []
        if secs:
            secondary_case = {"listing_id": item.get("id"), "primary": item.get("category_id"), "secondary": secs[0], "title": item.get("title")}
            break
    evidence["secondary_case"] = secondary_case
    ok(secondary_case is not None, "found listing with secondary_categories", secondary_case, failures)
    if secondary_case:
        found = False
        sec_items_seen = 0
        limit = 96
        for page in range(30):
            r = req("GET", f"/listings?category_id={secondary_case['secondary']}&limit={limit}&skip={page * limit}")
            r.raise_for_status()
            items = r.json()
            sec_items_seen += len(items)
            if any(it.get("id") == secondary_case["listing_id"] for it in items):
                found = True
                break
            if len(items) < limit:
                break
        evidence["secondary_filter_items_scanned"] = sec_items_seen
        ok(found, "category filter includes listing via secondary_categories", secondary_case, failures)

    # q + category must be AND, not OR.
    electronics = next((c for c in categories if c.get("slug") == "electronics"), None)
    if electronics:
        plain_e = req("GET", f"/listings?category_id={electronics['id']}&limit=96")
        plain_e.raise_for_status()
        laptop_e = req("GET", f"/listings?q=laptop&category_id={electronics['id']}&limit=96")
        laptop_e.raise_for_status()
        laptop_any = req("GET", "/listings?q=laptop&limit=96")
        laptop_any.raise_for_status()
        e_items = plain_e.json()
        le_items = laptop_e.json()
        any_items = laptop_any.json()
        evidence["electronics_plain_count_limit96"] = len(e_items)
        evidence["laptop_any_count_limit96"] = len(any_items)
        evidence["laptop_electronics_count_limit96"] = len(le_items)
        evidence["laptop_electronics_titles"] = [it.get("title") for it in le_items[:10]]
        ok(len(le_items) <= len(e_items), "q=laptop + electronics count <= plain electronics category count", {"combined": len(le_items), "plain": len(e_items)}, failures)
        ok(len(le_items) <= len(any_items), "q=laptop + electronics count <= plain laptop search count", {"combined": len(le_items), "plain_q": len(any_items)}, failures)
        all_and = all((it.get("category_id") == electronics["id"] or electronics["id"] in (it.get("secondary_categories") or [])) and text_matches(it, "laptop") for it in le_items)
        ok(all_and, "every combined search result matches both laptop text and electronics category", evidence["laptop_electronics_titles"], failures)
    else:
        ok(False, "electronics category exists", None, failures)

    # Public /products page API evidence: active products appear and are not all in one category where categories exist.
    prod_r = req("GET", "/products?page=1&page_size=100")
    evidence["products_status_code"] = prod_r.status_code
    if prod_r.status_code == 200:
        prod = prod_r.json()
        categories_seen = sorted({(p.get("category") or "").strip() for p in prod.get("items", []) if (p.get("category") or "").strip()})
        evidence["products_total"] = prod.get("total")
        evidence["products_categories_seen_page1"] = categories_seen[:30]
        ok(int(prod.get("total") or 0) > 0 and len(prod.get("items", [])) > 0, "public /products API has visible products", {"total": prod.get("total"), "items": len(prod.get("items", []))}, failures)
        ok(len(categories_seen) >= 2, "public /products API page shows multiple product categories", categories_seen, failures)
    else:
        ok(False, "public /products API responds", prod_r.status_code, failures)

    evidence["failures"] = failures
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(evidence, f, indent=2)
    print(f"Wrote {OUT}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())