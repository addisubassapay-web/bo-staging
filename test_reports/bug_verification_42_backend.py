#!/usr/bin/env python3
"""Focused backend verification for Apify-only listing/Zyte removal bug."""
import json
import os
import re
import sys
import time
from pathlib import Path
from datetime import datetime, timezone

import requests
from requests.exceptions import ChunkedEncodingError, ConnectionError, Timeout

BASE_URL = os.environ.get("TEST_BASE_URL", "https://ocean-marketplace.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@mercari.local")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")
OUT = Path("/app/test_reports/bug_verification_42_backend_results.json")

session = requests.Session()
session.headers.update({"Accept": "application/json", "Connection": "close"})

results = {
    "started_at": datetime.now(timezone.utc).isoformat(),
    "base_url": BASE_URL,
    "checks": [],
}


def record(name, ok, details=None):
    entry = {"name": name, "ok": bool(ok), "details": details or {}}
    results["checks"].append(entry)
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name}: {json.dumps(entry['details'], default=str)[:1400]}")
    return ok


def request(method, path, **kwargs):
    url = BASE_URL + path
    kwargs.setdefault("timeout", 60)
    kwargs.setdefault("allow_redirects", False)
    last_exc = None
    for attempt in range(1, 4):
        try:
            resp = session.request(method, url, **kwargs)
            resp._qa_attempt = attempt
            return resp
        except (ChunkedEncodingError, ConnectionError, Timeout) as exc:
            last_exc = exc
            if attempt < 3:
                time.sleep(0.8 * attempt)
            else:
                raise last_exc


def parse_json(resp):
    try:
        return resp.json()
    except Exception:
        return {"_non_json_text": resp.text[:500]}

# 1) Zyte scraper stub: exact no-slash route and variants must return 410, not 307 redirects.
scraper_paths = ["/api/scraper", "/api/scraper/", "/api/scraper/anything"]
scraper_methods = ["GET", "POST", "PUT", "DELETE", "PATCH"]
expected_msg = "Zyte scraper endpoints have been removed"
scraper_failures = []
scraper_samples = []
for path in scraper_paths:
    for method in scraper_methods:
        try:
            resp = request(method, path)
            data = parse_json(resp)
            body_text = json.dumps(data)
            ok = resp.status_code == 410 and expected_msg in body_text
            detail = {"method": method, "path": path, "status": resp.status_code, "location": resp.headers.get("location"), "body": data, "attempt": getattr(resp, "_qa_attempt", 1)}
        except Exception as exc:
            ok = False
            detail = {"method": method, "path": path, "exception": repr(exc)}
        if not ok:
            scraper_failures.append(detail)
        scraper_samples.append(detail)
record("scraper_stub_all_paths_methods_410_no_redirect", not scraper_failures, {"failures": scraper_failures, "sample": scraper_samples[:8]})

# 2) Legacy listing purge/filter via public listings search.
for term in ["Soumission", "toscrape"]:
    try:
        resp = request("GET", "/api/listings", params={"q": term, "limit": 500})
        data = parse_json(resp)
        ok = resp.status_code == 200 and isinstance(data, list) and len(data) == 0
        details = {"status": resp.status_code, "count": len(data) if isinstance(data, list) else None, "sample_titles": [d.get("title") for d in data[:5]] if isinstance(data, list) else None, "body_if_error": data if not isinstance(data, list) else None, "attempt": getattr(resp, "_qa_attempt", 1)}
    except Exception as exc:
        ok = False
        details = {"exception": repr(exc)}
    record(f"legacy_query_{term}_zero_results", ok, details)

# 3) Sample current response source_url values exclude toscrape/scrape.me.
try:
    resp = request("GET", "/api/listings", params={"limit": 20})
    first20 = parse_json(resp)
    bad_source_rows = []
    if isinstance(first20, list):
        for item in first20:
            source_url = item.get("source_url")
            if source_url and re.search(r"toscrape|scrape\.me", source_url, re.I):
                bad_source_rows.append({"id": item.get("id"), "title": item.get("title"), "source_url": source_url})
    ok = resp.status_code == 200 and isinstance(first20, list) and not bad_source_rows
    details = {"status": resp.status_code, "count": len(first20) if isinstance(first20, list) else None, "bad_rows": bad_source_rows, "source_url_sample": [d.get("source_url") for d in first20[:5]] if isinstance(first20, list) else None, "attempt": getattr(resp, "_qa_attempt", 1)}
except Exception as exc:
    ok = False
    details = {"exception": repr(exc)}
record("source_url_sample_first_20_has_no_toscrape_or_scrape_me", ok, details)

# 4) Limit/default marketplace fullness checks.
limit_expectations = [
    ({}, "default_limit_60_returns_at_least_60", lambda n: n >= 60),
    ({"limit": 300}, "limit_300_returns_300", lambda n: n == 300),
    ({"limit": 500}, "limit_500_returns_500", lambda n: n == 500),
    ({"limit": 600}, "limit_600_clamps_to_500", lambda n: n == 500),
]
for params, name, predicate in limit_expectations:
    try:
        resp = request("GET", "/api/listings", params=params)
        data = parse_json(resp)
        count = len(data) if isinstance(data, list) else None
        ok = resp.status_code == 200 and isinstance(data, list) and predicate(count)
        details = {"status": resp.status_code, "count": count, "first_ids": [d.get("id") for d in data[:3]] if isinstance(data, list) else None, "body_if_error": data if not isinstance(data, list) else None, "attempt": getattr(resp, "_qa_attempt", 1)}
    except Exception as exc:
        ok = False
        details = {"exception": repr(exc)}
    record(name, ok, details)

# 5) Admin sync status should not be running. Do NOT trigger any sync.
try:
    login_resp = request("POST", "/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    login_data = parse_json(login_resp)
    token = login_data.get("token") if isinstance(login_data, dict) else None
    login_ok = login_resp.status_code == 200 and bool(token)
    record("admin_login_for_sync_status", login_ok, {"status": login_resp.status_code, "has_token": bool(token), "user_role": (login_data.get("user") or {}).get("role") if isinstance(login_data, dict) else None, "body_if_error": login_data if not login_ok else None, "attempt": getattr(login_resp, "_qa_attempt", 1)})
except Exception as exc:
    token = None
    record("admin_login_for_sync_status", False, {"exception": repr(exc)})

if token:
    try:
        auth_headers = {"Authorization": f"Bearer {token}", "Accept": "application/json", "Connection": "close"}
        samples = []
        # Poll several times without triggering a sync; status should be stable false.
        for idx in range(10):
            sync_resp = request("GET", "/api/admin/sync/status", headers=auth_headers)
            sync_data = parse_json(sync_resp)
            samples.append({
                "index": idx,
                "status": sync_resp.status_code,
                "sync_running": sync_data.get("sync_running") if isinstance(sync_data, dict) else None,
                "target_count": sync_data.get("target_count") if isinstance(sync_data, dict) else None,
                "message": sync_data.get("message") if isinstance(sync_data, dict) else None,
                "started_at": sync_data.get("started_at") if isinstance(sync_data, dict) else None,
                "attempt": getattr(sync_resp, "_qa_attempt", 1),
            })
            time.sleep(0.8)
        ok = all(s["status"] == 200 and s["sync_running"] is False for s in samples)
        record("admin_sync_status_sync_running_stably_false", ok, {"samples": samples})
    except Exception as exc:
        record("admin_sync_status_sync_running_stably_false", False, {"exception": repr(exc)})
else:
    record("admin_sync_status_sync_running_stably_false", False, {"reason": "admin login failed, cannot call protected status"})

results["finished_at"] = datetime.now(timezone.utc).isoformat()
results["passed"] = sum(1 for c in results["checks"] if c["ok"])
results["failed"] = sum(1 for c in results["checks"] if not c["ok"])
OUT.write_text(json.dumps(results, indent=2, default=str))
print(f"Wrote {OUT}")
if results["failed"]:
    sys.exit(1)
