"""Regression tests for the async Apify webhook ingest path.

Verifies the P0 fix that resolved HTTP 502 timeouts on large payloads:
  1. Small payloads (<= 200 items) go through the sync path and return
     inline created/updated counters.
  2. Large payloads (> 200 items) are handed to the arq worker and the
     endpoint returns immediately with `queued: true` + a `job_id`.
  3. Envelopes that carry a `resource.defaultDatasetId` are ALWAYS
     queued (we don't have inline items to process synchronously).
  4. The admin status endpoint is reachable and reports progress.
"""
from __future__ import annotations

import os
import time
import uuid
from pathlib import Path

import pytest
import requests

# ---- Config ---------------------------------------------------------------
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    for line in Path("/app/frontend/.env").read_text().splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            BASE_URL = line.split("=", 1)[1].strip().strip('"').rstrip("/")
            break

WEBHOOK = f"{BASE_URL}/api/webhooks/apify-import"

# Read the live secret from backend/.env so this stays in sync with rotations.
SECRET = ""
for line in Path("/app/backend/.env").read_text().splitlines():
    if line.startswith("APIFY_WEBHOOK_SECRET="):
        SECRET = line.split("=", 1)[1].strip().strip('"')
        break

ADMIN_EMAIL = "admin@mercari.local"
ADMIN_PASSWORD = "admin123"


@pytest.fixture(scope="module")
def admin_token() -> str:
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    return r.json()["token"]


# ---- Sync path (small payload) -------------------------------------------
class TestSyncPath:
    def test_small_payload_returns_inline_counters(self):
        unique = uuid.uuid4().hex[:6].upper()
        items = [
            {
                "asin": f"B00SYNC{unique}{i}",
                "title": f"Async-Fix Sync Item {i}",
                "price": 10.0 + i,
                "url": f"https://amazon.com/dp/B00SYNC{unique}{i}",
            }
            for i in range(3)
        ]
        r = requests.post(
            WEBHOOK,
            json={"resource": {"items": items}},
            headers={"X-Webhook-Secret": SECRET},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["ok"] is True
        assert data.get("queued") is not True, "small payloads must NOT queue"
        assert data["received"] == 3
        assert data["created"] + data["updated"] == 3


# ---- Async path (large payload) -------------------------------------------
class TestAsyncPath:
    def test_large_payload_is_queued(self, admin_token):
        unique = uuid.uuid4().hex[:6].upper()
        # 220 items — above the 200-item inline limit
        items = [
            {
                "asin": f"B00ASY{unique}{i:04d}",
                "title": f"Async Bulk Item {i}",
                "price": 5.0 + (i % 100),
                "url": f"https://amazon.com/dp/B00ASY{unique}{i:04d}",
            }
            for i in range(220)
        ]
        t0 = time.time()
        r = requests.post(
            WEBHOOK,
            json={"resource": {"items": items}},
            headers={"X-Webhook-Secret": SECRET},
            timeout=15,
        )
        elapsed = time.time() - t0

        assert r.status_code == 200, r.text
        # Endpoint must return quickly (was previously 502ing on this size).
        assert elapsed < 5.0, f"webhook took {elapsed:.2f}s — should be < 5s"

        data = r.json()
        assert data["ok"] is True
        assert data.get("queued") is True
        assert data["kind"] == "items"
        assert data["received"] == 220
        job_id = data["job_id"]
        assert job_id

        # Poll for completion via the admin status endpoint (max ~30s).
        status_url = f"{BASE_URL}/api/admin/webhooks/apify-import/status/{job_id}"
        headers = {"Authorization": f"Bearer {admin_token}"}
        deadline = time.time() + 30
        last = None
        while time.time() < deadline:
            resp = requests.get(status_url, headers=headers, timeout=10)
            assert resp.status_code == 200, resp.text
            last = resp.json()
            if last.get("status") in ("done", "failed"):
                break
            time.sleep(1)
        assert last is not None
        assert last["status"] == "done", f"job did not complete: {last}"
        assert last["received"] == 220
        assert last["created"] + last["updated"] == 220

    def test_dataset_reference_is_always_queued(self):
        """Envelopes with resource.defaultDatasetId must always queue,
        because there are no inline items to process synchronously."""
        r = requests.post(
            WEBHOOK,
            json={"resource": {"defaultDatasetId": "nonexistent-dataset-for-test"}},
            headers={"X-Webhook-Secret": SECRET},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["queued"] is True
        assert data["kind"] == "dataset"
        assert data["dataset_id"] == "nonexistent-dataset-for-test"


# ---- Force flag ----------------------------------------------------------
class TestBackgroundOverride:
    def test_background_true_forces_queue(self):
        r = requests.post(
            f"{WEBHOOK}?background=true",
            json={
                "resource": {
                    "items": [
                        {
                            "asin": f"B00FORCE{uuid.uuid4().hex[:6].upper()}",
                            "title": "Force queue",
                            "price": 1.23,
                            "url": "https://amazon.com/dp/FORCEBG",
                        }
                    ]
                }
            },
            headers={"X-Webhook-Secret": SECRET},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        assert r.json().get("queued") is True


# ---- Admin status endpoint -----------------------------------------------
class TestAdminStatus:
    def test_status_list_requires_admin(self):
        r = requests.get(f"{BASE_URL}/api/admin/webhooks/apify-import/status", timeout=10)
        assert r.status_code in (401, 403), r.text

    def test_status_list_with_admin(self, admin_token):
        r = requests.get(
            f"{BASE_URL}/api/admin/webhooks/apify-import/status?limit=5",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=10,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert "items" in data
        assert isinstance(data["items"], list)

    def test_status_unknown_id_is_404(self, admin_token):
        r = requests.get(
            f"{BASE_URL}/api/admin/webhooks/apify-import/status/does-not-exist",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=10,
        )
        assert r.status_code == 404
