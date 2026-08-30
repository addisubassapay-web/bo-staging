#!/usr/bin/env python3
"""Read-only current-state check after frontend rebalance."""
import json
import os
import time
import requests

BASE_URL = os.environ.get("TEST_BASE_URL", "https://ocean-marketplace.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
OUT = "/app/test_reports/apify_current_state_after_ui.json"

def req(method, path, token=None, **kwargs):
    headers = kwargs.pop("headers", {}) or {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return requests.request(method, f"{API}{path}", headers=headers, timeout=30, **kwargs)

token = req("POST", "/auth/login", json={"email": "admin@mercari.local", "password": "admin123"}).json()["token"]
status = req("GET", "/admin/sync/status", token=token).json()
cats = req("GET", "/categories").json()
counts = {}
samples = {}
for c in cats:
    items = req("GET", f"/listings?category_id={c['id']}&limit=96").json()
    counts[c["slug"]] = len(items)
    samples[c["slug"]] = [it.get("title") for it in items[:2]]
out = {
    "base_url": BASE_URL,
    "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "sync_running": status.get("sync_running"),
    "sync_status": status,
    "category_counts_limit96": counts,
    "all_categories_at_least_20": all(v >= 20 for v in counts.values()),
    "empty_categories": [k for k, v in counts.items() if v == 0],
    "samples": samples,
}
print(json.dumps(out, indent=2))
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2)
print(f"Wrote {OUT}")