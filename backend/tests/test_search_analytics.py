"""Regression: search analytics endpoint.

Also validates that /products/suggest fires the log write in the background
so admin insights actually accumulate.
"""
from __future__ import annotations

import os
import time
import uuid
from pathlib import Path

import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    for line in Path("/app/frontend/.env").read_text().splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            BASE_URL = line.split("=", 1)[1].strip().strip('"').rstrip("/")
            break
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@mercari.local"
ADMIN_PASSWORD = "admin123"


def _login():
    r = requests.post(
        f"{API}/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    return r.json()["token"]


def test_analytics_endpoint_requires_admin():
    r = requests.get(f"{API}/admin/search/analytics", timeout=10)
    assert r.status_code in (401, 403)


def test_analytics_shape():
    token = _login()
    r = requests.get(
        f"{API}/admin/search/analytics?hours=24",
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    for key in ("window_hours", "total_searches", "unique_queries",
                "correction_rate", "top_queries", "zero_result"):
        assert key in data, f"missing {key}"
    assert isinstance(data["top_queries"], list)
    assert isinstance(data["zero_result"], list)


def test_suggest_logs_zero_result_search():
    # Use a random query so the zero-result assertion is bulletproof
    unique_q = f"noresultq{uuid.uuid4().hex[:8]}"
    r_sug = requests.get(f"{API}/products/suggest?q={unique_q}", timeout=15).json()
    assert r_sug["products"] == []
    assert r_sug["corrected"] is None

    # Give the fire-and-forget log write a moment to land
    time.sleep(1.5)

    token = _login()
    data = requests.get(
        f"{API}/admin/search/analytics?hours=1",
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    ).json()
    zero_queries = [z["query"] for z in data["zero_result"]]
    assert unique_q in zero_queries, (
        f"expected {unique_q!r} in zero_result, got {zero_queries[:5]}"
    )
