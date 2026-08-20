"""
Phase 2 backend tests:
- Public user snapshot endpoint
- File upload/download via Emergent object storage
- AI Listing Assistant (GPT vision via Emergent LLM Key)
- Mocked shipping labels + tracking
- Seller apply with id_document_file_id
- Regression sanity for core flows
"""
import base64
import io
import os
import time
import uuid
import pytest
import requests
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).resolve().parents[2] / "frontend" / ".env")
BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@mercuri-global.local"
ADMIN_PASSWORD = "admin123"


# ---------- helpers ----------
def _login(email: str, password: str) -> str:
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return r.json()["token"]


def _register(email: str, username: str, password: str = "pass1234") -> dict:
    r = requests.post(f"{API}/auth/register", json={
        "email": email, "username": username, "password": password
    }, timeout=30)
    assert r.status_code in (200, 201), f"register failed: {r.status_code} {r.text}"
    return r.json()


def _auth(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}


# Real 400x400 JPEG photo — fetched once at session start (visible objects/textures)
@pytest.fixture(scope="session")
def real_image_bytes():
    # Retry a few times in case of transient
    last_exc = None
    for _ in range(3):
        try:
            r = requests.get("https://picsum.photos/id/1080/400/400.jpg", timeout=30, allow_redirects=True)
            if r.status_code == 200 and len(r.content) > 5000 and r.content[:3] == b"\xff\xd8\xff":
                return r.content
        except Exception as e:
            last_exc = e
    pytest.skip(f"Could not fetch test image: {last_exc}")


@pytest.fixture(scope="session")
def real_image_b64(real_image_bytes):
    return base64.b64encode(real_image_bytes).decode()


@pytest.fixture(scope="session")
def real_image_url():
    return "https://picsum.photos/id/1080/400/400.jpg"


@pytest.fixture(scope="session")
def admin_token():
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture(scope="session")
def admin_user(admin_token):
    r = requests.get(f"{API}/auth/me", headers=_auth(admin_token), timeout=15)
    assert r.status_code == 200
    return r.json()


@pytest.fixture(scope="session")
def alt_user():
    """A fresh unrelated user (never seller, never buyer for our order)."""
    ts = int(time.time() * 1000)
    email = f"e2e_alt_{ts}@example.com"
    username = f"e2ealt{ts}"
    _register(email, username)
    tok = _login(email, "pass1234")
    me = requests.get(f"{API}/auth/me", headers=_auth(tok), timeout=15).json()
    return {"token": tok, "user": me}


@pytest.fixture(scope="session")
def buyer_user():
    ts = int(time.time() * 1000)
    email = f"e2e_buyer_{ts}@example.com"
    username = f"e2ebuyer{ts}"
    _register(email, username)
    tok = _login(email, "pass1234")
    me = requests.get(f"{API}/auth/me", headers=_auth(tok), timeout=15).json()
    return {"token": tok, "user": me}


# =========================================================
# Public user endpoint
# =========================================================
class TestPublicUser:
    def test_public_user_returns_snapshot(self, admin_user):
        r = requests.get(f"{API}/users/{admin_user['id']}/public", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        for k in ("id", "username", "email_verified", "phone_verified",
                  "seller_status", "rating", "sales_count"):
            assert k in data, f"missing key {k} in {data}"
        assert data["id"] == admin_user["id"]
        assert isinstance(data["email_verified"], bool)
        assert isinstance(data["phone_verified"], bool)
        # public snapshot must NOT expose password hash
        assert "password_hash" not in data

    def test_public_user_no_auth_required(self, admin_user):
        # explicitly send no Authorization header
        r = requests.get(f"{API}/users/{admin_user['id']}/public", timeout=15,
                         headers={"Authorization": ""})
        assert r.status_code == 200

    def test_public_user_404(self):
        r = requests.get(f"{API}/users/does-not-exist-{uuid.uuid4().hex}/public", timeout=15)
        assert r.status_code == 404


# =========================================================
# File upload/download
# =========================================================
class TestUploadDownload:
    def test_upload_image_success(self, admin_token, real_image_bytes):
        files = {"file": ("photo.jpg", real_image_bytes, "image/jpeg")}
        r = requests.post(f"{API}/upload", headers=_auth(admin_token), files=files, timeout=60)
        assert r.status_code == 200, r.text
        j = r.json()
        for k in ("id", "url", "size", "content_type"):
            assert k in j
        assert j["url"].startswith("/api/files/")
        assert j["size"] > 0
        # save for other tests via class attr
        TestUploadDownload._admin_file_id = j["id"]

    def test_upload_rejects_unsupported_ext(self, admin_token):
        files = {"file": ("evil.svg", b"<svg></svg>", "image/svg+xml")}
        r = requests.post(f"{API}/upload", headers=_auth(admin_token), files=files, timeout=30)
        assert r.status_code == 400, r.text

    def test_upload_rejects_too_large(self, admin_token):
        big = b"\xff\xd8\xff" + os.urandom(13 * 1024 * 1024)  # >12MB
        files = {"file": ("big.jpg", big, "image/jpeg")}
        r = requests.post(f"{API}/upload", headers=_auth(admin_token), files=files, timeout=120)
        assert r.status_code == 400, r.text

    def test_upload_requires_auth(self, real_image_bytes):
        files = {"file": ("photo.jpg", real_image_bytes[:5000], "image/jpeg")}
        r = requests.post(f"{API}/upload", files=files, timeout=30)
        assert r.status_code in (401, 403)

    def test_download_owner_ok_via_query_auth(self, admin_token):
        fid = getattr(TestUploadDownload, "_admin_file_id", None)
        assert fid, "prior upload test must run first"
        r = requests.get(f"{API}/files/{fid}?auth={admin_token}", timeout=60)
        assert r.status_code == 200, r.text
        assert r.headers.get("content-type", "").startswith("image/")
        assert len(r.content) > 500

    def test_download_owner_ok_via_bearer(self, admin_token):
        fid = getattr(TestUploadDownload, "_admin_file_id", None)
        r = requests.get(f"{API}/files/{fid}", headers=_auth(admin_token), timeout=60)
        assert r.status_code == 200

    def test_download_no_auth_401(self):
        fid = getattr(TestUploadDownload, "_admin_file_id", None)
        r = requests.get(f"{API}/files/{fid}", timeout=15)
        assert r.status_code == 401

    def test_download_other_user_403(self, alt_user, admin_token, real_image_bytes):
        # upload as alt_user
        files = {"file": ("mine.jpg", real_image_bytes[:8000], "image/jpeg")}
        up = requests.post(f"{API}/upload", headers=_auth(alt_user["token"]), files=files, timeout=60)
        assert up.status_code == 200, up.text
        fid = up.json()["id"]
        # admin CAN read (admin bypass) — verify that
        r_admin = requests.get(f"{API}/files/{fid}?auth={admin_token}", timeout=30)
        assert r_admin.status_code == 200
        # unrelated buyer cannot
        ts = int(time.time() * 1000)
        _register(f"e2e_other_{ts}@example.com", f"e2eother{ts}")
        other_tok = _login(f"e2e_other_{ts}@example.com", "pass1234")
        r_other = requests.get(f"{API}/files/{fid}?auth={other_tok}", timeout=30)
        assert r_other.status_code == 403, r_other.text

    def test_download_unknown_file_404(self, admin_token):
        r = requests.get(f"{API}/files/nope-{uuid.uuid4().hex}?auth={admin_token}", timeout=15)
        assert r.status_code == 404


# =========================================================
# AI Listing Suggest
# =========================================================
class TestAIListingSuggest:
    REQUIRED_KEYS = {
        "title", "description", "category_slug", "category_id", "category_name",
        "condition", "brand", "color", "size", "suggested_price_usd"
    }

    def test_ai_requires_image(self, admin_token):
        r = requests.post(f"{API}/ai/listing-suggest", headers=_auth(admin_token),
                          json={}, timeout=30)
        assert r.status_code == 400

    def test_ai_base64_returns_structured(self, admin_token, real_image_b64):
        r = requests.post(f"{API}/ai/listing-suggest",
                          headers=_auth(admin_token),
                          json={"image_base64": real_image_b64},
                          timeout=180)
        assert r.status_code == 200, r.text
        data = r.json()
        missing = self.REQUIRED_KEYS - set(data.keys())
        assert not missing, f"missing keys: {missing}. Got: {list(data.keys())}"
        # Category coerced to valid slug
        cats = requests.get(f"{API}/categories", timeout=15).json()
        valid_slugs = {c["slug"] for c in cats}
        valid_ids = {c["id"] for c in cats}
        assert data["category_slug"] in valid_slugs, data["category_slug"]
        assert data["category_id"] in valid_ids
        # Suggested price is a number
        assert isinstance(data["suggested_price_usd"], (int, float))

    def test_ai_image_url_returns_structured(self, admin_token, real_image_url):
        r = requests.post(f"{API}/ai/listing-suggest",
                          headers=_auth(admin_token),
                          json={"image_url": real_image_url},
                          timeout=180)
        assert r.status_code == 200, r.text
        data = r.json()
        missing = self.REQUIRED_KEYS - set(data.keys())
        assert not missing, f"missing keys: {missing}"


# =========================================================
# Shipping labels + tracking
# =========================================================
@pytest.fixture(scope="module")
def admin_listing_and_order(admin_token, buyer_user):
    """Admin creates a listing (admin bypasses seller-gate). Buyer creates an order for it."""
    # pick any category
    cats = requests.get(f"{API}/categories", timeout=15).json()
    assert cats, "categories required"
    cat = cats[0]
    listing_payload = {
        "title": f"TEST Phase2 Item {uuid.uuid4().hex[:6]}",
        "description": "Test listing for shipping label tests.",
        "price": 25.5,
        "category_id": cat["id"],
        "condition": "good",
        "images": ["https://picsum.photos/id/1080/400/400.jpg"],
        "shipping_paid_by": "buyer",
    }
    r = requests.post(f"{API}/listings", headers=_auth(admin_token),
                      json=listing_payload, timeout=30)
    assert r.status_code == 200, r.text
    listing = r.json()

    order_payload = {
        "listing_id": listing["id"],
        "shipping_address": {
            "name": "Buyer", "line1": "1 Test St", "city": "Testville",
            "state": "CA", "postal_code": "94000", "country": "US",
        },
    }
    r = requests.post(f"{API}/orders", headers=_auth(buyer_user["token"]),
                      json=order_payload, timeout=30)
    assert r.status_code == 200, r.text
    order = r.json()
    return {"listing": listing, "order": order}


class TestShippingLabel:
    def test_tracking_before_label_returns_has_label_false(self, admin_token, admin_listing_and_order):
        oid = admin_listing_and_order["order"]["id"]
        r = requests.get(f"{API}/orders/{oid}/tracking", headers=_auth(admin_token), timeout=15)
        assert r.status_code == 200, r.text
        assert r.json().get("has_label") is False

    def test_seller_creates_label(self, admin_token, admin_listing_and_order):
        oid = admin_listing_and_order["order"]["id"]
        r = requests.post(f"{API}/orders/{oid}/shipping-label",
                          headers=_auth(admin_token), timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["tracking_number"].startswith("MOCK")
        assert d["carrier"] in ("USPS", "UPS", "FedEx")
        assert d["label_url"]
        assert d["dev_mock"] is True
        TestShippingLabel._first_tracking = d["tracking_number"]

    def test_label_is_idempotent(self, admin_token, admin_listing_and_order):
        oid = admin_listing_and_order["order"]["id"]
        r = requests.post(f"{API}/orders/{oid}/shipping-label",
                          headers=_auth(admin_token), timeout=30)
        assert r.status_code == 200
        assert r.json()["tracking_number"] == TestShippingLabel._first_tracking

    def test_non_seller_403(self, alt_user, admin_listing_and_order):
        oid = admin_listing_and_order["order"]["id"]
        r = requests.post(f"{API}/orders/{oid}/shipping-label",
                          headers=_auth(alt_user["token"]), timeout=30)
        assert r.status_code == 403

    def test_tracking_events_timeline(self, admin_token, admin_listing_and_order):
        oid = admin_listing_and_order["order"]["id"]
        r = requests.get(f"{API}/orders/{oid}/tracking", headers=_auth(admin_token), timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["has_label"] is True
        assert d["tracking_number"].startswith("MOCK")
        assert d["dev_mock"] is True
        assert isinstance(d["events"], list) and len(d["events"]) >= 1
        # First event should be label_created; current_status should match last event
        assert d["events"][0]["status"] == "label_created"
        assert d["current_status"] == d["events"][-1]["status"]
        valid = {"label_created", "picked_up", "in_transit", "out_for_delivery", "delivered"}
        for ev in d["events"]:
            assert ev["status"] in valid
            for k in ("at", "location", "description"):
                assert k in ev

    def test_tracking_buyer_can_access(self, buyer_user, admin_listing_and_order):
        oid = admin_listing_and_order["order"]["id"]
        r = requests.get(f"{API}/orders/{oid}/tracking",
                         headers=_auth(buyer_user["token"]), timeout=15)
        assert r.status_code == 200
        assert r.json()["has_label"] is True

    def test_tracking_other_user_403(self, alt_user, admin_listing_and_order):
        oid = admin_listing_and_order["order"]["id"]
        r = requests.get(f"{API}/orders/{oid}/tracking",
                         headers=_auth(alt_user["token"]), timeout=15)
        assert r.status_code == 403


# =========================================================
# Seller apply with id_document_file_id (e2e)
# =========================================================
class TestSellerApplyWithDocFile:
    def test_upload_then_apply(self, real_image_bytes):
        ts = int(time.time() * 1000)
        email = f"e2e_sellerdoc_{ts}@example.com"
        username = f"e2esd{ts}"
        _register(email, username)
        tok = _login(email, "pass1234")

        # verify email + phone (mock)
        r = requests.post(f"{API}/verify/email/send", headers=_auth(tok), json={}, timeout=15)
        assert r.status_code == 200, r.text
        etok = r.json().get("token")
        assert etok
        r = requests.post(f"{API}/verify/email/confirm", headers=_auth(tok),
                          json={"token": etok}, timeout=15)
        assert r.status_code == 200

        r = requests.post(f"{API}/verify/phone/send", headers=_auth(tok),
                          json={"phone": "+15551234567"}, timeout=15)
        assert r.status_code == 200, r.text
        code = r.json().get("code")
        assert code
        r = requests.post(f"{API}/verify/phone/confirm", headers=_auth(tok),
                          json={"phone": "+15551234567", "code": code}, timeout=15)
        assert r.status_code == 200

        # upload ID doc (JPEG)
        files = {"file": ("id.jpg", real_image_bytes, "image/jpeg")}
        up = requests.post(f"{API}/upload", headers=_auth(tok), files=files, timeout=60)
        assert up.status_code == 200, up.text
        file_id = up.json()["id"]

        # apply
        app_payload = {
            "legal_name": "Test Seller",
            "business_name": "",
            "business_type": "individual",
            "tax_id": "123456789",
            "country": "US",
            "address_line1": "1 Merch Way",
            "address_line2": "",
            "city": "Testville",
            "state": "CA",
            "postal_code": "94000",
            "phone": "+15551234567",
            "payout_method": "bank_transfer",
            "id_document_note": "sample",
            "id_document_file_id": file_id,
        }
        r = requests.post(f"{API}/seller/apply", headers=_auth(tok),
                          json=app_payload, timeout=30)
        assert r.status_code == 200, r.text
        appd = r.json()
        assert appd.get("id_document_file_id") == file_id
        assert appd.get("status") == "pending"

        # fetch via GET
        r = requests.get(f"{API}/seller/application", headers=_auth(tok), timeout=15)
        assert r.status_code == 200
        gotten = r.json()
        assert gotten and gotten.get("id_document_file_id") == file_id


# =========================================================
# Regression sanity
# =========================================================
class TestRegression:
    def test_login(self):
        _login(ADMIN_EMAIL, ADMIN_PASSWORD)

    def test_listings_list(self):
        r = requests.get(f"{API}/listings", timeout=30)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_categories(self):
        r = requests.get(f"{API}/categories", timeout=15)
        assert r.status_code == 200
        assert len(r.json()) > 0

    def test_favorites(self, admin_token):
        r = requests.get(f"{API}/favorites", headers=_auth(admin_token), timeout=15)
        assert r.status_code == 200

    def test_cart(self, admin_token):
        r = requests.get(f"{API}/cart", headers=_auth(admin_token), timeout=15)
        assert r.status_code == 200

    def test_orders(self, admin_token):
        r = requests.get(f"{API}/orders", headers=_auth(admin_token), timeout=15)
        assert r.status_code == 200

    def test_admin_stats(self, admin_token):
        r = requests.get(f"{API}/admin/stats", headers=_auth(admin_token), timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert "pending_seller_apps" in d

    def test_chat_threads(self, admin_token):
        r = requests.get(f"{API}/chat/threads", headers=_auth(admin_token), timeout=15)
        assert r.status_code == 200

    def test_verify_status_or_me(self, admin_token):
        r = requests.get(f"{API}/auth/me", headers=_auth(admin_token), timeout=15)
        assert r.status_code == 200
