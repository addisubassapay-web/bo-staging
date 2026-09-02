#!/usr/bin/env python3
"""Focused backend verification for Zyte removal / Apify-only listings regression.

Does NOT trigger Apify sync. It only reads auth-protected sync status and public listing routes.
"""
import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List

import requests


BASE_URL = os.environ.get("BASE_URL", "https://bo-staging.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@mercari.local")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")
OUT_PATH = os.environ.get("OUT_PATH", "/app/test_reports/bug_verification_43_backend_results.json")
REMOVED_MSG = "Zyte scraper endpoints have been removed"


class CheckRecorder:
    def __init__(self) -> None:
        self.checks: List[Dict[str, Any]] = []

    def add(self, name: str, passed: bool, details: Dict[str, Any] | None = None) -> None:
        entry = {"name": name, "passed": bool(passed), "details": details or {}}
        self.checks.append(entry)
        status = "PASS" if passed else "FAIL"
        print(f"[{status}] {name}: {json.dumps(entry['details'], default=str)[:1200]}")


def request_json(method: str, path: str, **kwargs) -> tuple[int, Any, str]:
    url = f"{BASE_URL}{path}"
    resp = requests.request(method, url, timeout=25, **kwargs)
    text = resp.text
    try:
        body = resp.json()
    except Exception:
        body = None
    return resp.status_code, body, text


def main() -> int:
    rec = CheckRecorder()
    started = datetime.now(timezone.utc).isoformat()

    token = None
    try:
        status, body, text = request_json(
            "POST",
            "/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        )
        token = (body or {}).get("token") if isinstance(body, dict) else None
        rec.add(
            "admin login for sync status",
            status == 200 and bool(token),
            {"status": status, "has_token": bool(token), "body_keys": sorted((body or {}).keys()) if isinstance(body, dict) else None, "text": text[:300]},
        )
    except Exception as exc:
        rec.add("admin login for sync status", False, {"exception": repr(exc)})

    headers = {"Authorization": f"Bearer {token}"} if token else {}

    # Primary regression: sync_running must not flap true while auto-sync is quota-exhausted/cooling down.
    sync_polls: List[Dict[str, Any]] = []
    if token:
        poll_start = time.monotonic()
        for i in range(10):
            try:
                status, body, text = request_json("GET", "/api/admin/sync/status", headers=headers)
                sync_polls.append({
                    "poll": i + 1,
                    "status": status,
                    "sync_running": body.get("sync_running") if isinstance(body, dict) else None,
                    "message": body.get("message") if isinstance(body, dict) else None,
                    "next_scheduled_at": body.get("next_scheduled_at") if isinstance(body, dict) else None,
                    "last_attempt_at": body.get("last_attempt_at") if isinstance(body, dict) else None,
                    "body_type": type(body).__name__,
                    "text": None if isinstance(body, dict) else text[:300],
                })
            except Exception as exc:
                sync_polls.append({"poll": i + 1, "exception": repr(exc)})
            if i < 9:
                time.sleep(2.35)
        elapsed = round(time.monotonic() - poll_start, 2)
        rec.add(
            "SYNC_RUNNING STABLE: 10 admin status polls over >=20s all false",
            elapsed >= 20 and len(sync_polls) == 10 and all(p.get("status") == 200 and p.get("sync_running") is False for p in sync_polls),
            {"elapsed_seconds": elapsed, "polls": sync_polls},
        )
    else:
        rec.add("SYNC_RUNNING STABLE: 10 admin status polls over >=20s all false", False, {"reason": "admin login failed"})

    # Scraper deprecation stubs must return 410 without redirecting.
    scraper_cases = [
        ("GET", "/api/scraper"),
        ("GET", "/api/scraper/"),
        ("GET", "/api/scraper/foo"),
        ("POST", "/api/scraper/import"),
    ]
    scraper_results = []
    for method, path in scraper_cases:
        try:
            status, body, text = request_json(method, path, allow_redirects=False)
            detail = body.get("detail") if isinstance(body, dict) else text
            scraper_results.append({"method": method, "path": path, "status": status, "detail": str(detail)[:300]})
        except Exception as exc:
            scraper_results.append({"method": method, "path": path, "exception": repr(exc)})
    rec.add(
        "SCRAPER STUB: all legacy scraper endpoints return HTTP 410 JSON removal message",
        all(r.get("status") == 410 and REMOVED_MSG in r.get("detail", "") for r in scraper_results),
        {"results": scraper_results},
    )

    # Legacy listing filters and marketplace size.
    legacy_results = []
    for q in ["Soumission", "toscrape"]:
        try:
            status, body, text = request_json("GET", f"/api/listings?q={q}")
            count = len(body) if isinstance(body, list) else None
            legacy_results.append({"q": q, "status": status, "count": count, "text": None if isinstance(body, list) else text[:300]})
        except Exception as exc:
            legacy_results.append({"q": q, "exception": repr(exc)})
    rec.add(
        "LEGACY LISTING FILTER: Soumission and toscrape searches return 0 items",
        all(r.get("status") == 200 and r.get("count") == 0 for r in legacy_results),
        {"results": legacy_results},
    )

    default_items: List[Dict[str, Any]] = []
    try:
        status, body, text = request_json("GET", "/api/listings")
        default_items = body if isinstance(body, list) else []
        sample = default_items[:20]
        bad_sample = [
            {"id": item.get("id"), "title": item.get("title"), "source_url": item.get("source_url")}
            for item in sample
            if "toscrape" in str(item.get("source_url", "")).lower()
        ]
        rec.add(
            "LEGACY LISTING FILTER: first 20 default listings have no toscrape source_url",
            status == 200 and not bad_sample,
            {"status": status, "default_count": len(default_items), "bad_sample": bad_sample, "sampled": len(sample), "text": None if isinstance(body, list) else text[:300]},
        )
        rec.add(
            "DEFAULT MARKETPLACE FULL: /api/listings returns >=60 items",
            status == 200 and len(default_items) >= 60,
            {"status": status, "count": len(default_items)},
        )
    except Exception as exc:
        rec.add("LEGACY LISTING FILTER: first 20 default listings have no toscrape source_url", False, {"exception": repr(exc)})
        rec.add("DEFAULT MARKETPLACE FULL: /api/listings returns >=60 items", False, {"exception": repr(exc)})

    # Listing limit cap at 500.
    limit_results = []
    for lim in [500, 600]:
        try:
            status, body, text = request_json("GET", f"/api/listings?limit={lim}")
            limit_results.append({"limit": lim, "status": status, "count": len(body) if isinstance(body, list) else None, "text": None if isinstance(body, list) else text[:300]})
        except Exception as exc:
            limit_results.append({"limit": lim, "exception": repr(exc)})
    rec.add(
        "MAX LIMIT: limit=500 works and limit=600 clamps to <=500 with no error",
        all(r.get("status") == 200 and isinstance(r.get("count"), int) and r["count"] <= 500 for r in limit_results),
        {"results": limit_results},
    )

    # Category browse: use first three categories returned by the API as typical marketplace category flow.
    try:
        cat_status, cats, cat_text = request_json("GET", "/api/categories")
        selected = cats[:3] if isinstance(cats, list) else []
        cat_results = []
        for cat in selected:
            cid = cat.get("id")
            status, body, text = request_json("GET", f"/api/listings?category_id={cid}&limit=200")
            cat_results.append({
                "id": cid,
                "name": cat.get("name"),
                "status": status,
                "count": len(body) if isinstance(body, list) else None,
                "text": None if isinstance(body, list) else text[:300],
            })
        rec.add(
            "CATEGORY BROWSE: first 3 categories each return >=20 items with limit=200",
            cat_status == 200 and len(cat_results) == 3 and all(r.get("status") == 200 and r.get("count", 0) >= 20 for r in cat_results),
            {"categories_status": cat_status, "results": cat_results, "categories_text": None if isinstance(cats, list) else cat_text[:300]},
        )
    except Exception as exc:
        rec.add("CATEGORY BROWSE: first 3 categories each return >=20 items with limit=200", False, {"exception": repr(exc)})

    finished = datetime.now(timezone.utc).isoformat()
    overall = all(c["passed"] for c in rec.checks)
    output = {
        "base_url": BASE_URL,
        "started_at": started,
        "finished_at": finished,
        "overall_passed": overall,
        "checks": rec.checks,
    }
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"Wrote results to {OUT_PATH}")
    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(main())