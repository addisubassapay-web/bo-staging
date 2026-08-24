"""Iteration 32 backend tests: local storage, quotas, paginated seed scrape."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://mercari-global-clone-1.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

DEMO_EMAIL = "sophia_style@demo.local"
DEMO_PASS = "demo1234"
ADMIN_EMAIL = "admin@mercari-global.local"
ADMIN_PASS = "admin123"


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module")
def demo_auth():
    d = _login(DEMO_EMAIL, DEMO_PASS)
    return {"token": d["token"], "user": d["user"], "headers": {"Authorization": f"Bearer {d['token']}"}}


@pytest.fixture(scope="module")
def admin_auth():
    d = _login(ADMIN_EMAIL, ADMIN_PASS)
    return {"token": d["token"], "user": d["user"], "headers": {"Authorization": f"Bearer {d['token']}"}}


@pytest.fixture(scope="module")
def category_id():
    r = requests.get(f"{API}/categories", timeout=10)
    assert r.status_code == 200
    cats = r.json()
    # Response might be list or {items:[]}
    items = cats if isinstance(cats, list) else cats.get("items") or cats.get("categories") or []
    assert items, "No categories"
    return items[0].get("id") or items[0].get("_id")


# ============================================================
# Storage
# ============================================================
class TestStorage:
    def test_status_reports_local_disk(self, admin_auth):
        r = requests.get(f"{API}/scraper/status", headers=admin_auth["headers"], timeout=10)
        assert r.status_code == 200, r.text
        s = r.json()["storage"]
        assert s["provider"] == "local_disk"
        assert s["enabled"] is True

    def test_scrape_returns_local_image_url(self, demo_auth):
        # Clear quota headroom via admin override done in other test — set an override for sophia here
        # Just use a fresh, cheap scrape from books.toscrape
        # Ensure user has room:
        _bump_sophia_cap(demo_auth["user"]["id"], 10_000)
        r = requests.post(
            f"{API}/scraper/jobs",
            headers=demo_auth["headers"],
            json={"url": "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html"},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        job_id = r.json()["id"]
        # Poll
        for _ in range(30):
            time.sleep(2)
            g = requests.get(f"{API}/scraper/jobs/{job_id}", headers=demo_auth["headers"], timeout=10)
            if g.status_code == 200 and g.json().get("status") in ("done", "failed"):
                break
        job = g.json()
        assert job["status"] == "done", f"job did not complete: {job.get('error')}"
        images = job["result"]["listing"]["images"]
        assert images, "no images rehosted"
        img_url = images[0]
        assert img_url.startswith(BASE_URL + "/api/uploads/scraper/"), f"expected local url, got {img_url}"
        # GET the image and confirm 200 + non-zero content length
        head = requests.get(img_url, timeout=15)
        assert head.status_code == 200
        assert len(head.content) > 0


# ============================================================
# Quotas
# ============================================================
def _bump_sophia_cap(user_id, cap):
    admin = _login(ADMIN_EMAIL, ADMIN_PASS)
    r = requests.post(
        f"{API}/scraper/admin/quota/override",
        headers={"Authorization": f"Bearer {admin['token']}"},
        json={"user_id": user_id, "cap": cap},
        timeout=10,
    )
    assert r.status_code == 200, r.text


def _clear_sophia_cap(user_id):
    admin = _login(ADMIN_EMAIL, ADMIN_PASS)
    requests.post(
        f"{API}/scraper/admin/quota/override",
        headers={"Authorization": f"Bearer {admin['token']}"},
        json={"user_id": user_id, "cap": 0},
        timeout=10,
    )


class TestQuotas:
    def test_get_my_quota_shape(self, demo_auth):
        _bump_sophia_cap(demo_auth["user"]["id"], 10_000)
        r = requests.get(f"{API}/scraper/quota", headers=demo_auth["headers"], timeout=10)
        assert r.status_code == 200, r.text
        q = r.json()
        for k in ("month", "used", "cap", "remaining", "override_active"):
            assert k in q
        assert q["cap"] == 10_000
        assert q["remaining"] == q["cap"] - q["used"]

    def test_low_cap_blocks_scrape_with_429(self, demo_auth):
        uid = demo_auth["user"]["id"]
        # Set cap 1 below current usage → force 429
        cur = requests.get(f"{API}/scraper/quota", headers=demo_auth["headers"], timeout=10).json()
        _bump_sophia_cap(uid, max(1, cur["used"]))  # cap == used → remaining 0
        r = requests.post(
            f"{API}/scraper/jobs",
            headers=demo_auth["headers"],
            json={"url": "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html"},
            timeout=15,
        )
        assert r.status_code == 429, r.text
        assert "quota" in (r.json().get("detail") or "").lower()
        # Paginated should also be blocked
        r2 = requests.post(
            f"{API}/scraper/jobs/paginated",
            headers=demo_auth["headers"],
            json={"provider": "amazon_search", "query": "x", "pages": 1},
            timeout=15,
        )
        assert r2.status_code == 429
        _bump_sophia_cap(uid, 10_000)  # restore

    def test_admin_quota_list_and_global_cap(self, admin_auth):
        r = requests.get(f"{API}/scraper/admin/quota", headers=admin_auth["headers"], timeout=10)
        assert r.status_code == 200
        body = r.json()
        assert "rows" in body and "global_cap" in body
        assert isinstance(body["rows"], list)

        # Update global cap
        r2 = requests.post(
            f"{API}/scraper/admin/quota/global-cap",
            headers=admin_auth["headers"],
            json={"cap": 1234},
            timeout=10,
        )
        assert r2.status_code == 200
        assert r2.json()["cap"] == 1234
        # Verify persisted
        r3 = requests.get(f"{API}/scraper/admin/quota", headers=admin_auth["headers"], timeout=10)
        assert r3.json()["global_cap"] == 1234
        # Restore
        requests.post(
            f"{API}/scraper/admin/quota/global-cap",
            headers=admin_auth["headers"],
            json={"cap": 500},
            timeout=10,
        )

    def test_admin_endpoints_require_admin(self, demo_auth):
        for path, method, body in [
            ("/scraper/admin/quota", "GET", None),
            ("/scraper/admin/quota/global-cap", "POST", {"cap": 100}),
            ("/scraper/admin/quota/override", "POST", {"user_id": "x", "cap": 1}),
        ]:
            if method == "GET":
                r = requests.get(f"{API}{path}", headers=demo_auth["headers"], timeout=10)
            else:
                r = requests.post(f"{API}{path}", headers=demo_auth["headers"], json=body, timeout=10)
            assert r.status_code == 403, f"{path} expected 403, got {r.status_code}"


# ============================================================
# Paginated seed scraper
# ============================================================
class TestPaginated:
    def test_validation_rejects(self, demo_auth, category_id):
        _bump_sophia_cap(demo_auth["user"]["id"], 10_000)
        h = demo_auth["headers"]
        # unknown provider
        r = requests.post(f"{API}/scraper/jobs/paginated", headers=h,
                          json={"provider": "ebay_x", "query": "q", "pages": 1}, timeout=10)
        assert r.status_code == 400
        # missing category when auto_publish
        r = requests.post(f"{API}/scraper/jobs/paginated", headers=h,
                          json={"provider": "amazon_search", "query": "q", "pages": 1, "auto_publish": True}, timeout=10)
        assert r.status_code == 400
        # pages > 50
        r = requests.post(f"{API}/scraper/jobs/paginated", headers=h,
                          json={"provider": "amazon_search", "query": "q", "pages": 51}, timeout=10)
        assert r.status_code == 422
        # pages < 1
        r = requests.post(f"{API}/scraper/jobs/paginated", headers=h,
                          json={"provider": "amazon_search", "query": "q", "pages": 0}, timeout=10)
        assert r.status_code == 422

    def test_happy_path_returns_super_batch(self, demo_auth, category_id):
        _bump_sophia_cap(demo_auth["user"]["id"], 10_000)
        r = requests.post(
            f"{API}/scraper/jobs/paginated",
            headers=demo_auth["headers"],
            json={
                "provider": "amazon_search",
                "query": "wireless headphones",
                "pages": 2,
                "category_id": category_id,
                "auto_publish": True,
            },
            timeout=15,
        )
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["pages_queued"] == 2
        assert len(j["child_batch_ids"]) == 2
        sb_id = j["super_batch_id"]
        # Status endpoint
        s = requests.get(f"{API}/scraper/super-batches/{sb_id}", headers=demo_auth["headers"], timeout=10)
        assert s.status_code == 200
        body = s.json()
        for k in ("pages_done", "pages_failed", "pages_total", "products_total", "products_published"):
            assert k in body
        assert body["pages_total"] == 2

    def test_seed_url_templates(self):
        # White-box: import the templates and confirm shape
        from routers.scraper import _SEED_TEMPLATES
        assert _SEED_TEMPLATES["amazon_search"] == "https://www.amazon.com/s?k={q}&page={p}"
        assert _SEED_TEMPLATES["mercari-global_search"] == "https://www.mercari-global.com/search/?keyword={q}&page={p}"
        assert _SEED_TEMPLATES["amazon_bestsellers"] == "https://www.amazon.com/gp/bestsellers/{q}?pg={p}"
