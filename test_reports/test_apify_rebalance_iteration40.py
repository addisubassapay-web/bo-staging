#!/usr/bin/env python3
"""Focused verification for Apify/Aptify catalog category rebalance bug.

Test plan:
- Verify admin-only rebalance auth behavior.
- Run POST /api/admin/listings/rebalance three times and assert runs 2/3 are idempotent.
- Ensure admin listing count is unchanged (no cloned rows).
- Verify categories have at least 20 visible listings and public filtering uses primary OR secondary categories.
- Verify text + category filtering is ANDed.
- Verify sync_running is false after rebalance.
"""
import json
import os
import time
from collections import Counter, defaultdict

import requests


BASE = os.environ.get("APIFY_TEST_BASE", "https://marketplace-dropship.preview.emergentagent.com/api").rstrip("/")
OUT = "/app/test_reports/apify_rebalance_iteration40_backend_results.json"


def req(method, path, token=None, timeout=90, **kwargs):
    headers = kwargs.pop("headers", {}) or {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    url = f"{BASE}{path}"
    resp = requests.request(method, url, headers=headers, timeout=timeout, **kwargs)
    try:
        body = resp.json()
    except Exception:
        body = resp.text[:1000]
    return resp.status_code, body


def login(email, password):
    code, body = req("POST", "/auth/login", json={"email": email, "password": password}, timeout=30)
    if code != 200:
        raise AssertionError(f"login failed for {email}: {code} {body}")
    return body["token"], body["user"]


def text_matches(item, q):
    needle = q.lower()
    hay = " ".join(str(item.get(k) or "") for k in ("title", "description", "brand")).lower()
    return needle in hay


def main():
    results = {
        "base": BASE,
        "checks": {},
        "rebalance_runs": [],
        "category_samples": [],
        "secondary_filter_proof": None,
        "text_category_sample": None,
        "public_distribution": None,
        "failures": [],
    }

    admin_token, admin_user = login("admin@mercari.local", "admin123")
    regular_token, regular_user = login("sophia_style@demo.local", "demo1234")
    results["admin_user"] = {"email": admin_user.get("email"), "role": admin_user.get("role")}
    results["regular_user"] = {"email": regular_user.get("email"), "role": regular_user.get("role")}

    code, cats = req("GET", "/categories", timeout=30)
    if code != 200 or not isinstance(cats, list) or not cats:
        raise AssertionError(f"categories unavailable: {code} {cats}")
    results["categories"] = [{"id": c["id"], "slug": c.get("slug"), "name": c.get("name")} for c in cats]
    cat_by_slug = {c.get("slug"): c for c in cats}

    # Auth checks on rebalance endpoint.
    unauth_code, unauth_body = req("POST", "/admin/listings/rebalance", json={"min_per_category": 20, "clear_sync_flag": True}, timeout=30)
    regular_code, regular_body = req("POST", "/admin/listings/rebalance", token=regular_token, json={"min_per_category": 20, "clear_sync_flag": True}, timeout=30)
    results["checks"]["auth"] = {
        "unauthenticated_status": unauth_code,
        "unauthenticated_body": unauth_body,
        "regular_user_status": regular_code,
        "regular_user_body": regular_body,
        "pass": unauth_code in (401, 403) and regular_code == 403,
    }
    if not results["checks"]["auth"]["pass"]:
        results["failures"].append("rebalance auth did not reject unauthenticated/non-admin as expected")

    # GET /admin/listings length before.
    code, before_listings = req("GET", "/admin/listings", token=admin_token, timeout=90)
    if code != 200 or not isinstance(before_listings, list):
        raise AssertionError(f"admin listings before unavailable: {code} {before_listings}")
    before_len = len(before_listings)
    results["admin_listings_before_len"] = before_len

    for i in range(1, 4):
        start = time.time()
        code, body = req("POST", "/admin/listings/rebalance", token=admin_token, json={"min_per_category": 20, "clear_sync_flag": True}, timeout=180)
        elapsed = round(time.time() - start, 2)
        run = {"run": i, "status": code, "elapsed_sec": elapsed, "body": body}
        results["rebalance_runs"].append(run)
        if code != 200:
            results["failures"].append(f"rebalance run {i} returned {code}")

    run2 = results["rebalance_runs"][1]["body"] if len(results["rebalance_runs"]) > 1 else {}
    run3 = results["rebalance_runs"][2]["body"] if len(results["rebalance_runs"]) > 2 else {}
    idempotent = (
        isinstance(run2, dict)
        and isinstance(run3, dict)
        and run2.get("reclassified") == 0
        and run2.get("listings_tagged") == 0
        and run3.get("reclassified") == 0
        and run3.get("listings_tagged") == 0
        and run2.get("counts_after") == run3.get("counts_after")
    )
    results["checks"]["three_run_idempotency"] = {
        "pass": idempotent,
        "run2_reclassified": run2.get("reclassified") if isinstance(run2, dict) else None,
        "run2_listings_tagged": run2.get("listings_tagged") if isinstance(run2, dict) else None,
        "run3_reclassified": run3.get("reclassified") if isinstance(run3, dict) else None,
        "run3_listings_tagged": run3.get("listings_tagged") if isinstance(run3, dict) else None,
        "counts_after_identical": isinstance(run2, dict) and isinstance(run3, dict) and run2.get("counts_after") == run3.get("counts_after"),
    }
    if not idempotent:
        results["failures"].append("rebalance was not idempotent on runs 2 and 3")

    code, after_listings = req("GET", "/admin/listings", token=admin_token, timeout=90)
    if code != 200 or not isinstance(after_listings, list):
        raise AssertionError(f"admin listings after unavailable: {code} {after_listings}")
    after_len = len(after_listings)
    results["admin_listings_after_len"] = after_len
    results["checks"]["no_new_rows_admin_listings_length"] = {"pass": before_len == after_len, "before": before_len, "after": after_len}
    if before_len != after_len:
        results["failures"].append(f"admin listings length changed from {before_len} to {after_len}")

    final_counts = run3.get("counts_after", {}) if isinstance(run3, dict) else {}
    below_20 = {slug: cnt for slug, cnt in final_counts.items() if cnt < 20}
    results["checks"]["all_counts_after_at_least_20"] = {"pass": not below_20 and bool(final_counts), "below_20": below_20, "counts_after": final_counts}
    if below_20 or not final_counts:
        results["failures"].append(f"some categories still below 20: {below_20}")

    # Verify at least 10 category pages /listings?category_id=... return >=20 listings.
    public_category_failures = []
    for c in cats[:10]:
        code, items = req("GET", f"/listings?category_id={c['id']}&limit=96", timeout=60)
        sample = {"slug": c.get("slug"), "id": c["id"], "status": code, "returned": len(items) if isinstance(items, list) else None}
        if code != 200 or not isinstance(items, list) or len(items) < 20:
            public_category_failures.append(sample)
        results["category_samples"].append(sample)
    results["checks"]["ten_public_category_pages_have_20"] = {"pass": not public_category_failures, "failures": public_category_failures}
    if public_category_failures:
        results["failures"].append(f"some public category endpoints returned fewer than 20: {public_category_failures}")

    # Secondary category filtering proof: API response contains a listing not primary in category but secondary includes it.
    secondary_counts = defaultdict(int)
    for item in after_listings:
        for sid in item.get("secondary_categories") or []:
            secondary_counts[sid] += 1
    secondary_candidates = sorted(secondary_counts, key=lambda cid: secondary_counts[cid], reverse=True)
    secondary_proof = None
    for cid in secondary_candidates:
        code, items = req("GET", f"/listings?category_id={cid}&limit=96", timeout=60)
        if code != 200 or not isinstance(items, list):
            continue
        for item in items:
            if item.get("category_id") != cid and cid in (item.get("secondary_categories") or []):
                cat = next((c for c in cats if c["id"] == cid), {})
                secondary_proof = {
                    "category_id": cid,
                    "category_slug": cat.get("slug"),
                    "secondary_count_in_admin_listing_snapshot": secondary_counts[cid],
                    "returned_listing_id": item.get("id"),
                    "returned_listing_title": item.get("title"),
                    "returned_listing_primary_category_id": item.get("category_id"),
                    "returned_listing_secondary_categories": item.get("secondary_categories"),
                }
                break
        if secondary_proof:
            break
    results["secondary_filter_proof"] = secondary_proof
    results["checks"]["secondary_category_filtering"] = {"pass": secondary_proof is not None}
    if secondary_proof is None:
        results["failures"].append("could not prove public category filter returns secondary-category matches")

    # Text + category combined filter: should be AND.
    electronics = cat_by_slug.get("electronics")
    if electronics:
        code, laptop_items = req("GET", f"/listings?q=laptop&category_id={electronics['id']}&limit=96", timeout=60)
        and_failures = []
        if code == 200 and isinstance(laptop_items, list):
            for item in laptop_items:
                category_ok = item.get("category_id") == electronics["id"] or electronics["id"] in (item.get("secondary_categories") or [])
                query_ok = text_matches(item, "laptop")
                if not (category_ok and query_ok):
                    and_failures.append({"id": item.get("id"), "title": item.get("title"), "category_ok": category_ok, "query_ok": query_ok})
            results["text_category_sample"] = {
                "category_slug": "electronics",
                "category_id": electronics["id"],
                "status": code,
                "returned": len(laptop_items),
                "sample_titles": [i.get("title") for i in laptop_items[:5]],
                "and_failures": and_failures,
            }
        else:
            and_failures.append({"status": code, "body": laptop_items})
        results["checks"]["text_and_category_are_anded"] = {"pass": not and_failures and code == 200 and isinstance(laptop_items, list), "failures": and_failures}
        if and_failures or code != 200:
            results["failures"].append("q=laptop + electronics category returned non-AND matches or failed")
    else:
        results["checks"]["text_and_category_are_anded"] = {"pass": False, "reason": "electronics category missing"}
        results["failures"].append("electronics category missing")

    code, status_body = req("GET", "/admin/sync/status", token=admin_token, timeout=30)
    immediate_status = {"status": code, "body": status_body}
    settled_status = immediate_status
    # The live sync scheduler can briefly flip sync_running=true between checks.
    # Rebalance must clear stuck sync flags; accept only if status settles false quickly.
    if code == 200 and status_body.get("sync_running") is True:
        for _ in range(10):
            time.sleep(2)
            code2, body2 = req("GET", "/admin/sync/status", token=admin_token, timeout=30)
            settled_status = {"status": code2, "body": body2}
            if code2 == 200 and body2.get("sync_running") is False:
                break
    settled_body = settled_status.get("body") or {}
    results["checks"]["sync_running_false"] = {
        "pass": settled_status.get("status") == 200 and settled_body.get("sync_running") is False,
        "immediate": immediate_status,
        "settled": settled_status,
    }
    if settled_status.get("status") != 200 or settled_body.get("sync_running") is not False:
        results["failures"].append("sync_running was not false after rebalance")

    code, public_items = req("GET", "/listings?limit=96", timeout=60)
    if code == 200 and isinstance(public_items, list):
        primary_counts = Counter(i.get("category_id") for i in public_items)
        unique_primary = len([k for k, v in primary_counts.items() if k])
        top_count = max(primary_counts.values()) if primary_counts else 0
        results["public_distribution"] = {
            "status": code,
            "returned": len(public_items),
            "unique_primary_categories": unique_primary,
            "top_primary_count": top_count,
            "top_primary_fraction": round(top_count / max(1, len(public_items)), 3),
            "counts_by_primary_category_id": dict(primary_counts),
        }
        # This is a public visitor smoke check; exact category page counts above are the stronger proof.
        distribution_ok = len(public_items) >= 20 and unique_primary >= 2 and top_count < len(public_items)
    else:
        results["public_distribution"] = {"status": code, "body": public_items}
        distribution_ok = False
    results["checks"]["public_visitor_listings_across_categories"] = {"pass": distribution_ok, "distribution": results["public_distribution"]}
    if not distribution_ok:
        results["failures"].append("public /listings did not show items across multiple categories")

    results["overall_pass"] = not results["failures"]
    with open(OUT, "w") as f:
        json.dump(results, f, indent=2, sort_keys=True)
    print(json.dumps(results, indent=2, sort_keys=True))
    if results["failures"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()