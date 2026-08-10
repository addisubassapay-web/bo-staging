"""Phase 5 tests: /api/search/suggest and /api/for-you + light regression spot-checks."""
import base64
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.strip().split("=", 1)[1]
                break
BASE_URL = BASE_URL.rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@mercari.local", "password": "admin123"}
SELLER = {"email": "urban_finds@demo.local", "password": "demo1234"}


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
def fresh_user():
    """Register a brand-new user to test cold-start & favorite-driven /for-you behavior."""
    ts = int(time.time())
    email = f"e2e_p5_{ts}_{uuid.uuid4().hex[:6]}@example.com"
    username = f"e2ep5{ts}{uuid.uuid4().hex[:4]}"
    r = requests.post(
        f"{API}/auth/register",
        json={"email": email, "username": username, "password": "pass1234"},
        timeout=30,
    )
    assert r.status_code == 200, r.text
    token = r.json()["token"]
    uid = r.json()["user"]["id"]
    return {"token": token, "id": uid, "email": email}


# ==================== /search/suggest ====================

class TestSearchSuggest:
    def test_short_query_returns_empty(self):
        r = requests.get(f"{API}/search/suggest", params={"q": "a"}, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data == {"items": [], "queries": []}

    def test_empty_query_returns_empty(self):
        r = requests.get(f"{API}/search/suggest", params={"q": ""}, timeout=30)
        assert r.status_code == 200
        assert r.json() == {"items": [], "queries": []}

    def test_no_q_param(self):
        r = requests.get(f"{API}/search/suggest", timeout=30)
        assert r.status_code == 200
        assert r.json() == {"items": [], "queries": []}

    def test_nike_returns_items_and_queries(self):
        r = requests.get(f"{API}/search/suggest", params={"q": "nike"}, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data.get("items"), list)
        assert isinstance(data.get("queries"), list)
        assert len(data["items"]) >= 1, f"expected >=1 nike item, got {data}"
        # Each item has required shape
        for it in data["items"]:
            assert set(["id", "title", "image", "price", "brand", "category_name"]).issubset(it.keys())
            assert isinstance(it["title"], str)
            assert isinstance(it["price"], (int, float))
        # At least one item title or brand should contain 'nike' case-insensitively
        assert any("nike" in (it["title"] or "").lower() or "nike" in (it["brand"] or "").lower()
                   for it in data["items"])
        # Queries should include Nike (from brand distinct)
        assert any("nike" in (q or "").lower() for q in data["queries"]), f"queries={data['queries']}"

    def test_case_insensitive(self):
        low = requests.get(f"{API}/search/suggest", params={"q": "nike"}, timeout=30).json()
        up = requests.get(f"{API}/search/suggest", params={"q": "NIKE"}, timeout=30).json()
        mixed = requests.get(f"{API}/search/suggest", params={"q": "NiKe"}, timeout=30).json()
        # Same set of ids returned (order may differ due to no explicit sort, but limit=8)
        low_ids = {i["id"] for i in low["items"]}
        up_ids = {i["id"] for i in up["items"]}
        mixed_ids = {i["id"] for i in mixed["items"]}
        assert low_ids == up_ids == mixed_ids, f"case mismatch: {low_ids} {up_ids} {mixed_ids}"

    def test_limit_respected(self):
        r = requests.get(f"{API}/search/suggest", params={"q": "a", "limit": 3}, timeout=30)
        # q too short, still empty
        assert r.status_code == 200
        # Use a broader term likely to hit many items
        r2 = requests.get(f"{API}/search/suggest", params={"q": "sh", "limit": 3}, timeout=30)
        assert r2.status_code == 200
        assert len(r2.json()["items"]) <= 3

    def test_only_active_listings(self):
        # All returned items should correspond to active listings
        r = requests.get(f"{API}/search/suggest", params={"q": "nike", "limit": 8}, timeout=30)
        assert r.status_code == 200
        for it in r.json()["items"]:
            d = requests.get(f"{API}/listings/{it['id']}", timeout=30)
            if d.status_code == 200:
                assert d.json().get("status") == "active", f"non-active listing surfaced: {it['id']}"

    def test_no_auth_required(self):
        # Public endpoint — must succeed with no Authorization header
        r = requests.get(f"{API}/search/suggest", params={"q": "nike"}, timeout=30)
        assert r.status_code == 200


# ==================== /for-you ====================

class TestForYou:
    def test_unauthenticated_returns_401(self):
        r = requests.get(f"{API}/for-you", timeout=30)
        assert r.status_code in (401, 403), f"expected 401/403 got {r.status_code}: {r.text[:200]}"

    def test_cold_start_returns_trending(self, fresh_user):
        r = requests.get(
            f"{API}/for-you",
            headers={"Authorization": f"Bearer {fresh_user['token']}"},
            params={"limit": 8},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list)
        assert len(data) > 0, "cold-start should return trending fallback"
        assert len(data) <= 8
        # None are the user's own (fresh user has none anyway)
        for item in data:
            assert item.get("status") == "active"
            assert item.get("seller_id") != fresh_user["id"]

    def test_favorites_bias_recommendations(self, fresh_user):
        # Pick 2 listings from a specific category and favorite them
        listings = requests.get(f"{API}/listings?limit=50", timeout=30).json()
        # Filter listings not owned by fresh user (any listing works)
        # Group by category_id, pick a category with >=3 items
        by_cat = {}
        for it in listings:
            cid = it.get("category_id")
            if cid:
                by_cat.setdefault(cid, []).append(it)
        target_cat = None
        target_items = []
        for cid, items in by_cat.items():
            if len(items) >= 3:
                target_cat = cid
                target_items = items
                break
        if not target_cat:
            pytest.skip("not enough listings in a single category to run favorite-bias test")

        fav1, fav2 = target_items[0]["id"], target_items[1]["id"]
        headers = {"Authorization": f"Bearer {fresh_user['token']}"}
        for lid in (fav1, fav2):
            r = requests.post(f"{API}/favorites/{lid}", headers=headers, timeout=30)
            assert r.status_code in (200, 201), f"favorite failed: {r.status_code} {r.text}"

        # Get favorited brands set
        fav_brands = {target_items[0].get("brand"), target_items[1].get("brand")}
        fav_brands.discard(None)
        fav_brands.discard("")

        r = requests.get(f"{API}/for-you", headers=headers, params={"limit": 12}, timeout=30)
        assert r.status_code == 200, r.text
        rec = r.json()
        assert isinstance(rec, list)
        assert len(rec) > 0, "should return recommendations"

        # None of the favorited items should appear
        rec_ids = {it["id"] for it in rec}
        assert fav1 not in rec_ids and fav2 not in rec_ids, "favorited items should be excluded"

        # Every recommendation should match either the favorited category or a favorited brand
        # (endpoint may backfill with generic trending if not enough matches)
        # We assert the primary matching intent: at least 1 recommendation from favorited cat/brand.
        matches = [
            it for it in rec
            if it.get("category_id") == target_cat or (it.get("brand") and it.get("brand") in fav_brands)
        ]
        assert len(matches) >= 1, (
            f"expected at least one recommendation in category {target_cat} or brand {fav_brands}; "
            f"got categories={[i.get('category_id') for i in rec]} brands={[i.get('brand') for i in rec]}"
        )

    def test_excludes_own_listings(self, seller_token):
        r = requests.get(
            f"{API}/for-you",
            headers={"Authorization": f"Bearer {seller_token}"},
            params={"limit": 20},
            timeout=30,
        )
        assert r.status_code == 200
        # Get seller id
        me = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {seller_token}"}, timeout=30).json()
        for item in r.json():
            assert item.get("seller_id") != me["id"], "own listings must be excluded"

    def test_limit_respected(self, fresh_user):
        r = requests.get(
            f"{API}/for-you",
            headers={"Authorization": f"Bearer {fresh_user['token']}"},
            params={"limit": 3},
            timeout=30,
        )
        assert r.status_code == 200
        assert len(r.json()) <= 3


# ==================== Light Regression Spot-checks ====================

class TestRegressionLite:
    def test_flash_deals(self):
        r = requests.get(f"{API}/flash-deals", timeout=30)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_verify_email_send(self, seller_token):
        r = requests.post(
            f"{API}/verify/email/send",
            headers={"Authorization": f"Bearer {seller_token}"},
            json={},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True

    def test_ai_listing_suggest(self, seller_token):
        img = requests.get("https://picsum.photos/seed/mercari-p5/320/320.jpg", timeout=30).content
        b64 = base64.b64encode(img).decode()
        r = requests.post(
            f"{API}/ai/listing-suggest",
            headers={"Authorization": f"Bearer {seller_token}"},
            json={"image_base64": b64},
            timeout=120,
        )
        assert r.status_code == 200, r.text[:300]

    def test_ai_photo_enhance_small(self, seller_token):
        img = requests.get("https://picsum.photos/seed/mercari-p5b/300/300.jpg", timeout=30).content
        b64 = base64.b64encode(img).decode()
        r = requests.post(
            f"{API}/ai/photo-enhance",
            headers={"Authorization": f"Bearer {seller_token}"},
            json={"image_base64": b64},
            timeout=120,
        )
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        assert data.get("url", "").startswith("/api/files/")

    def test_shipping_label_endpoint_reachable(self, seller_token):
        # Unknown order -> 404 (endpoint exists and auth accepted)
        r = requests.post(
            f"{API}/orders/nonexistent-order-id/shipping-label",
            headers={"Authorization": f"Bearer {seller_token}"},
            timeout=30,
        )
        assert r.status_code == 404, f"expected 404, got {r.status_code}: {r.text[:200]}"

    def test_shipping_advance_endpoint_reachable(self, seller_token):
        r = requests.post(
            f"{API}/orders/nonexistent-order-id/shipping-advance",
            headers={"Authorization": f"Bearer {seller_token}"},
            json={},
            timeout=30,
        )
        assert r.status_code == 404, f"expected 404, got {r.status_code}: {r.text[:200]}"
