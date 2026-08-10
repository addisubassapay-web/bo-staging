"""Phase 4 tests: /ai/photo-enhance (Nano Banana), /flash-deals, /admin/flash-deals/rotate
+ light regression on prior phase endpoints.
"""
import base64
import os
import io
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    # Fallback to frontend .env explicitly (do not use a default at import failure)
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.strip().split("=", 1)[1]
                break
BASE_URL = BASE_URL.rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@mercari.local", "password": "admin123"}
SELLER = {"email": "urban_finds@demo.local", "password": "demo1234"}
SELLER2 = {"email": "vintage_maven@demo.local", "password": "demo1234"}


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed {email}: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="session")
def admin_token():
    return _login(ADMIN["email"], ADMIN["password"])


@pytest.fixture(scope="session")
def seller_token():
    return _login(SELLER["email"], SELLER["password"])


@pytest.fixture(scope="session")
def seller2_token():
    return _login(SELLER2["email"], SELLER2["password"])


@pytest.fixture(scope="session")
def small_product_image_b64():
    """Fetch a small ~picsum image (JPEG) and return its base64."""
    r = requests.get("https://picsum.photos/seed/mercari-product/400/400.jpg", timeout=30)
    r.raise_for_status()
    return base64.b64encode(r.content).decode("utf-8"), r.content


# ---------------- Flash deals ----------------

class TestFlashDeals:
    def test_flash_deals_list_default(self):
        r = requests.get(f"{API}/flash-deals", timeout=60)
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list)
        # Startup task should have populated ~10
        assert len(data) >= 5, f"expected >=5 flash deals, got {len(data)}"
        for item in data:
            assert item.get("is_flash_deal") is True
            assert item.get("status") == "active"
            assert item.get("flash_deal_ends_at")
            pct = item.get("flash_deal_discount_pct")
            assert isinstance(pct, int)
            assert 20 <= pct <= 74, f"bad pct {pct}"

    def test_flash_deals_limit(self):
        r = requests.get(f"{API}/flash-deals?limit=5", timeout=60)
        assert r.status_code == 200
        data = r.json()
        assert len(data) <= 5

    def test_flash_deal_ends_at_midnight_utc(self):
        r = requests.get(f"{API}/flash-deals?limit=3", timeout=60)
        assert r.status_code == 200
        from datetime import datetime, timezone
        for item in r.json():
            ends_at = item["flash_deal_ends_at"]
            dt = datetime.fromisoformat(ends_at.replace("Z", "+00:00"))
            # server may return naive UTC — normalize
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            assert dt.hour == 0 and dt.minute == 0 and dt.second == 0, f"not midnight: {ends_at}"
            assert dt > datetime.now(timezone.utc), f"ends_at not in future: {ends_at}"

    def test_admin_rotate_flash_deals(self, admin_token):
        r = requests.post(
            f"{API}/admin/flash-deals/rotate",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=60,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert "selected" in data
        assert "active" in data

    def test_admin_rotate_multiple_times_pool_capped(self, admin_token):
        # Two more rotations shouldn't exceed 10 active
        for _ in range(2):
            r = requests.post(
                f"{API}/admin/flash-deals/rotate",
                headers={"Authorization": f"Bearer {admin_token}"},
                timeout=60,
            )
            assert r.status_code == 200
        list_r = requests.get(f"{API}/flash-deals?limit=50", timeout=60)
        assert list_r.status_code == 200
        assert len(list_r.json()) <= 10, "flash deal pool exceeded FLASH_DEAL_COUNT=10"

    def test_rotate_forbidden_for_non_admin(self, seller_token):
        r = requests.post(
            f"{API}/admin/flash-deals/rotate",
            headers={"Authorization": f"Bearer {seller_token}"},
            timeout=30,
        )
        assert r.status_code == 403, f"expected 403, got {r.status_code} {r.text}"

    def test_listing_model_exposes_flash_fields(self):
        # Any listing (even non-flash) — verify fields exist in model responses
        r = requests.get(f"{API}/listings?limit=5", timeout=30)
        assert r.status_code == 200
        for item in r.json():
            assert "is_flash_deal" in item
            assert "flash_deal_ends_at" in item
            assert "flash_deal_discount_pct" in item


# ---------------- Photo Enhance (Nano Banana) ----------------

class TestPhotoEnhance:
    def test_missing_input_returns_400(self, seller_token):
        r = requests.post(
            f"{API}/ai/photo-enhance",
            headers={"Authorization": f"Bearer {seller_token}"},
            json={},
            timeout=30,
        )
        assert r.status_code == 400, r.text

    def test_photo_enhance_base64_creates_file_and_downloadable(self, seller_token, small_product_image_b64):
        b64, _raw = small_product_image_b64
        r = requests.post(
            f"{API}/ai/photo-enhance",
            headers={"Authorization": f"Bearer {seller_token}"},
            json={"image_base64": b64},
            timeout=120,
        )
        assert r.status_code == 200, f"{r.status_code} {r.text[:500]}"
        data = r.json()
        assert data.get("id")
        assert data.get("url", "").startswith("/api/files/")
        assert data.get("content_type", "").startswith("image/")
        assert isinstance(data.get("size"), int) and data["size"] > 0
        assert "prompt_used" in data
        # Download the enhanced file via token
        file_id = data["id"]
        d = requests.get(f"{API}/files/{file_id}?auth={seller_token}", timeout=60)
        assert d.status_code == 200, d.text[:300]
        assert d.headers.get("Content-Type", "").startswith("image/")
        assert len(d.content) > 100
        pytest.enhanced_file_id = file_id  # remember

    def test_photo_enhance_with_file_id(self, seller_token, small_product_image_b64):
        # First upload a file via /api/upload
        _b64, raw = small_product_image_b64
        files = {"file": ("input.jpg", raw, "image/jpeg")}
        up = requests.post(
            f"{API}/upload",
            headers={"Authorization": f"Bearer {seller_token}"},
            files=files,
            timeout=60,
        )
        assert up.status_code == 200, up.text
        uploaded_id = up.json()["id"]
        pytest.uploaded_file_id = uploaded_id
        pytest.uploaded_owner_token = seller_token

        r = requests.post(
            f"{API}/ai/photo-enhance",
            headers={"Authorization": f"Bearer {seller_token}"},
            json={"file_id": uploaded_id},
            timeout=120,
        )
        assert r.status_code == 200, f"{r.status_code} {r.text[:500]}"
        data = r.json()
        assert data.get("id") and data["id"] != uploaded_id
        assert data.get("content_type", "").startswith("image/")

    def test_photo_enhance_unknown_file_id_returns_404(self, seller_token):
        r = requests.post(
            f"{API}/ai/photo-enhance",
            headers={"Authorization": f"Bearer {seller_token}"},
            json={"file_id": "00000000-0000-0000-0000-000000000000"},
            timeout=30,
        )
        assert r.status_code == 404, r.text

    def test_photo_enhance_other_users_file_returns_403(self, seller2_token):
        # Use file uploaded by seller in previous test
        uploaded_id = getattr(pytest, "uploaded_file_id", None)
        if not uploaded_id:
            pytest.skip("no uploaded file id available from previous test")
        r = requests.post(
            f"{API}/ai/photo-enhance",
            headers={"Authorization": f"Bearer {seller2_token}"},
            json={"file_id": uploaded_id},
            timeout=30,
        )
        assert r.status_code == 403, f"expected 403 got {r.status_code} {r.text[:200]}"


# ---------------- Regression (light) ----------------

class TestRegression:
    def test_listings_default(self):
        r = requests.get(f"{API}/listings", timeout=30)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_listings_sort_trending(self):
        r = requests.get(f"{API}/listings?sort=trending&limit=5", timeout=30)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_listings_detail(self):
        r = requests.get(f"{API}/listings?limit=1", timeout=30)
        assert r.status_code == 200
        items = r.json()
        if not items:
            pytest.skip("no listings")
        lid = items[0]["id"]
        d = requests.get(f"{API}/listings/{lid}", timeout=30)
        assert d.status_code == 200
        assert d.json()["id"] == lid

    def test_verify_email_send(self, seller_token):
        r = requests.post(
            f"{API}/verify/email/send",
            headers={"Authorization": f"Bearer {seller_token}"},
            json={},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("ok") is True

    def test_ai_listing_suggest(self, seller_token, small_product_image_b64):
        b64, _ = small_product_image_b64
        r = requests.post(
            f"{API}/ai/listing-suggest",
            headers={"Authorization": f"Bearer {seller_token}"},
            json={"image_base64": b64},
            timeout=120,
        )
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"

    def test_seller_apply_endpoint_exists(self, seller_token):
        # Minimal valid-ish payload; endpoint may block on verification but should not 422
        r = requests.post(
            f"{API}/seller/apply",
            headers={"Authorization": f"Bearer {seller_token}"},
            json={
                "legal_name": "Test Seller",
                "business_name": "TestBiz",
                "business_type": "individual",
                "tax_id": "123456789",
                "country": "US",
                "address_line1": "1 Test St",
                "city": "SF",
                "state": "CA",
                "postal_code": "94105",
            },
            timeout=30,
        )
        # Accept 200 (created), 400 (needs verification / duplicate)
        assert r.status_code in (200, 400, 409), f"unexpected {r.status_code}: {r.text[:300]}"
