"""Backend tests for Apify webhook secret rotation (iteration 53)."""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fall back to reading frontend/.env
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().strip('"').rstrip("/")
                break

NEW_SECRET = "mg-webhook-3613c7c4f62f62677c1eb77a1ef1b07d"
OLD_SECRET = "mg-webhook-4f9c2b8e13a04d76b8b7c9e5f2a1d8e6"
WEBHOOK = f"{BASE_URL}/api/webhooks/apify-import"


# --- Auth negative tests ---
class TestWebhookAuthNegative:
    def test_missing_secret_returns_401(self):
        r = requests.post(WEBHOOK, json={"resource": {"items": []}})
        assert r.status_code == 401, r.text
        assert "Invalid or missing webhook secret" in r.text

    def test_wrong_secret_returns_401(self):
        r = requests.post(WEBHOOK, json={"resource": {"items": []}},
                          headers={"X-Webhook-Secret": "this-is-wrong"})
        assert r.status_code == 401, r.text

    def test_old_rotated_secret_returns_401(self):
        r = requests.post(WEBHOOK, json={"resource": {"items": []}},
                          headers={"X-Webhook-Secret": OLD_SECRET})
        assert r.status_code == 401, r.text
        # also via Bearer
        r2 = requests.post(WEBHOOK, json={"resource": {"items": []}},
                           headers={"Authorization": f"Bearer {OLD_SECRET}"})
        assert r2.status_code == 401, r2.text
        # also via query param
        r3 = requests.post(f"{WEBHOOK}?secret={OLD_SECRET}", json={"resource": {"items": []}})
        assert r3.status_code == 401, r3.text


# --- Auth positive tests with empty items ---
class TestWebhookAuthPositive:
    def test_new_secret_via_header(self):
        r = requests.post(WEBHOOK, json={"resource": {"items": []}},
                          headers={"X-Webhook-Secret": NEW_SECRET})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("ok") is True
        assert data.get("received") == 0

    def test_new_secret_via_bearer(self):
        r = requests.post(WEBHOOK, json={"resource": {"items": []}},
                          headers={"Authorization": f"Bearer {NEW_SECRET}"})
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True

    def test_new_secret_via_query(self):
        r = requests.post(f"{WEBHOOK}?secret={NEW_SECRET}", json={"resource": {"items": []}})
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True


# --- Idempotent import ---
class TestIdempotentImport:
    def test_import_creates_then_updates(self):
        unique = uuid.uuid4().hex[:8].upper()
        items = [
            {
                "asin": f"B00TEST{unique}A",
                "title": "Test Product 1",
                "price": 9.99,
                "description": "desc 1",
                "images": ["https://picsum.photos/300"],
                "url": f"https://amazon.com/dp/B00TEST{unique}A",
            },
            {
                "asin": f"B00TEST{unique}B",
                "title": "Test Product 2",
                "price": 19.99,
                "description": "desc 2",
                "images": ["https://picsum.photos/301"],
                "url": f"https://amazon.com/dp/B00TEST{unique}B",
            },
        ]
        payload = {"resource": {"items": items}}
        headers = {"X-Webhook-Secret": NEW_SECRET}

        r1 = requests.post(WEBHOOK, json=payload, headers=headers)
        assert r1.status_code == 200, r1.text
        d1 = r1.json()
        assert d1.get("ok") is True
        # both new
        assert d1.get("created", 0) + d1.get("updated", 0) == 2, d1
        assert d1.get("created", 0) == 2, f"first call should create both: {d1}"

        # repeat -> should be updated (not created again)
        r2 = requests.post(WEBHOOK, json=payload, headers=headers)
        assert r2.status_code == 200, r2.text
        d2 = r2.json()
        assert d2.get("created", 0) + d2.get("updated", 0) == 2, d2
        assert d2.get("updated", 0) == 2, f"second call should update both: {d2}"
        assert d2.get("created", 0) == 0


# --- /api/listings sanity ---
class TestListingsEndpoint:
    def test_listings_returns_200(self):
        r = requests.get(f"{BASE_URL}/api/listings")
        assert r.status_code == 200, r.text
        data = r.json()
        # accept list or {items:[...]}
        if isinstance(data, dict):
            items = data.get("items", data.get("listings", []))
        else:
            items = data
        assert isinstance(items, list)
        # not asserting non-empty strictly, but log if empty
        print(f"/api/listings returned {len(items)} items")
