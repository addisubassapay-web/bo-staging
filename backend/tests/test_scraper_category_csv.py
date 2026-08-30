"""Category productList + CSV bulk scrape tests (iteration 31).

Covers:
- POST /api/scraper/jobs/category validation + happy path w/ auto-publish
- POST /api/scraper/jobs/csv validation + happy path w/ auto-publish
- Existing /jobs/bulk validation additions (auto_publish requires category_id, invalid category_id,
  raised cap 500)
- GET /api/scraper/batches/{id} for category batches
- Verify auto-published listings appear in /api/listings?category_id=...
"""
import os
import time
import uuid
import pytest
import requests

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "https://ocean-marketplace.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@mercari-global.local", "password": "admin123"}
USER = {"email": "sophia_style@demo.local", "password": "demo1234"}

CATEGORY_URL = "https://books.toscrape.com/catalogue/category/books/mystery_3/index.html"
BOOKS_A = "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html"
BOOKS_B = "https://books.toscrape.com/catalogue/tipping-the-velvet_999/index.html"


def _login(creds):
    r = requests.post(f"{API}/auth/login", json=creds, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _hdr(t):
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture(scope="module")
def user_token():
    return _login(USER)


@pytest.fixture(scope="module")
def admin_token():
    return _login(ADMIN)


@pytest.fixture(scope="module")
def category_id(user_token):
    r = requests.get(f"{API}/categories", headers=_hdr(user_token), timeout=15)
    assert r.status_code == 200
    cats = r.json()
    assert len(cats) > 0
    # pick first available
    return cats[0]["id"]


# ---- /jobs/category validation ----
class TestCategoryValidation:
    def test_invalid_url(self, user_token):
        r = requests.post(f"{API}/scraper/jobs/category",
                          json={"url": "not a url"},
                          headers=_hdr(user_token), timeout=15)
        assert r.status_code == 400, r.text

    def test_autopublish_requires_category(self, user_token):
        r = requests.post(f"{API}/scraper/jobs/category",
                          json={"url": CATEGORY_URL, "auto_publish": True},
                          headers=_hdr(user_token), timeout=15)
        assert r.status_code == 400, r.text

    def test_invalid_category_id(self, user_token):
        r = requests.post(f"{API}/scraper/jobs/category",
                          json={"url": CATEGORY_URL, "auto_publish": True, "category_id": "does-not-exist"},
                          headers=_hdr(user_token), timeout=15)
        assert r.status_code == 400, r.text

    def test_missing_auth(self):
        r = requests.post(f"{API}/scraper/jobs/category",
                          json={"url": CATEGORY_URL}, timeout=15)
        assert r.status_code in (401, 403)


# ---- /jobs/category happy path + auto-publish ----
class TestCategoryHappyPath:
    def test_submit_and_progress(self, user_token, category_id):
        r = requests.post(f"{API}/scraper/jobs/category",
                          json={
                              "url": CATEGORY_URL,
                              "category_id": category_id,
                              "auto_publish": True,
                              "high_fidelity": False,
                          },
                          headers=_hdr(user_token), timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["status"] == "queued"
        assert data["kind"] == "category"
        assert "batch_id" in data
        pytest.category_batch_id = data["batch_id"]
        pytest.category_id_used = category_id

    def test_batch_completes(self, user_token):
        bid = getattr(pytest, "category_batch_id", None)
        if not bid:
            pytest.skip("no batch id")
        # Category productList may take longer — the Zyte call fans out to N products.
        deadline = time.time() + 180
        data = None
        while time.time() < deadline:
            r = requests.get(f"{API}/scraper/batches/{bid}", headers=_hdr(user_token), timeout=20)
            assert r.status_code == 200, r.text
            data = r.json()
            b_status = data["batch"].get("status")
            counts = data["counts"]
            active = counts.get("queued", 0) + counts.get("running", 0)
            if b_status == "done" and active == 0 and data["total"] >= 1:
                break
            time.sleep(3)
        assert data is not None, "no data"
        assert data["batch"]["status"] == "done", f"batch not done: {data['batch'].get('status')} counts={data['counts']}"
        assert data["total"] >= 1, "expected >=1 extracted product"
        assert data["counts"]["done"] >= 1
        pytest.category_data = data

    def test_jobs_have_publish_status_published(self):
        data = getattr(pytest, "category_data", None)
        if not data:
            pytest.skip("no data")
        published = [j for j in data["jobs"] if j.get("publish_status") == "published"]
        assert len(published) >= 1, f"expected auto-published listings, got: {[j.get('publish_status') for j in data['jobs']][:5]}"
        # published_listing_id must be present
        for j in published:
            assert j.get("published_listing_id"), f"missing published_listing_id: {j}"
        pytest.published_listing_ids = [j["published_listing_id"] for j in published]

    def test_listings_appear_in_category(self, user_token):
        published_ids = getattr(pytest, "published_listing_ids", None)
        cid = getattr(pytest, "category_id_used", None)
        if not published_ids or not cid:
            pytest.skip("no published ids")
        r = requests.get(f"{API}/listings?category_id={cid}&limit=200",
                         headers=_hdr(user_token), timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        # accept either {items:[...]} or bare list
        items = body["items"] if isinstance(body, dict) and "items" in body else body
        assert isinstance(items, list)
        found_ids = {it.get("id") for it in items}
        intersect = found_ids & set(published_ids)
        assert len(intersect) >= 1, f"none of published_ids {published_ids[:3]} present in listings?category_id={cid}"
        # verify status active
        for it in items:
            if it.get("id") in intersect:
                assert it.get("status") == "active", f"expected active, got {it.get('status')}"


# ---- /jobs/csv validation ----
class TestCsvValidation:
    def test_autopublish_requires_category(self, user_token):
        r = requests.post(f"{API}/scraper/jobs/csv",
                          json={"urls": [BOOKS_A], "auto_publish": True},
                          headers=_hdr(user_token), timeout=15)
        assert r.status_code == 400, r.text

    def test_invalid_category_id(self, user_token):
        r = requests.post(f"{API}/scraper/jobs/csv",
                          json={"urls": [BOOKS_A], "auto_publish": True, "category_id": "bogus"},
                          headers=_hdr(user_token), timeout=15)
        assert r.status_code == 400, r.text

    def test_all_invalid_urls(self, user_token):
        r = requests.post(f"{API}/scraper/jobs/csv",
                          json={"urls": ["ftp://x", "no"]},
                          headers=_hdr(user_token), timeout=15)
        assert r.status_code == 400

    def test_over_1000(self, user_token):
        urls = [f"https://books.toscrape.com/x_{i}.html" for i in range(1001)]
        r = requests.post(f"{API}/scraper/jobs/csv",
                          json={"urls": urls}, headers=_hdr(user_token), timeout=20)
        assert r.status_code == 422

    def test_missing_auth(self):
        r = requests.post(f"{API}/scraper/jobs/csv", json={"urls": [BOOKS_A]}, timeout=15)
        assert r.status_code in (401, 403)


# ---- /jobs/csv happy path + auto-publish ----
class TestCsvHappyPath:
    def test_submit(self, user_token, category_id):
        r = requests.post(f"{API}/scraper/jobs/csv",
                          json={
                              "urls": [BOOKS_A, BOOKS_B],
                              "category_id": category_id,
                              "auto_publish": True,
                              "high_fidelity": False,
                          },
                          headers=_hdr(user_token), timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["queued_count"] == 2
        assert len(data["queued"]) == 2
        pytest.csv_batch_id = data["batch_id"]

    def test_csv_batch_completes_and_publishes(self, user_token):
        bid = getattr(pytest, "csv_batch_id", None)
        if not bid:
            pytest.skip("no csv batch id")
        deadline = time.time() + 120
        data = None
        while time.time() < deadline:
            r = requests.get(f"{API}/scraper/batches/{bid}", headers=_hdr(user_token), timeout=15)
            assert r.status_code == 200
            data = r.json()
            active = data["counts"].get("queued", 0) + data["counts"].get("running", 0)
            if active == 0:
                break
            time.sleep(2)
        assert data is not None
        assert data["counts"]["done"] >= 1
        published = [j for j in data["jobs"] if j.get("publish_status") == "published"]
        assert len(published) >= 1, f"expected auto-publish; publish_status values: {[j.get('publish_status') for j in data['jobs']]}"
        for j in published:
            assert j.get("published_listing_id")


# ---- /jobs/bulk additions ----
class TestBulkAdditions:
    def test_autopublish_requires_category(self, user_token):
        r = requests.post(f"{API}/scraper/jobs/bulk",
                          json={"urls": [BOOKS_A], "auto_publish": True},
                          headers=_hdr(user_token), timeout=15)
        assert r.status_code == 400, r.text

    def test_invalid_category_id(self, user_token):
        r = requests.post(f"{API}/scraper/jobs/bulk",
                          json={"urls": [BOOKS_A], "auto_publish": True, "category_id": "nope"},
                          headers=_hdr(user_token), timeout=15)
        assert r.status_code == 400, r.text

    def test_cap_raised_to_500_accepts_100(self, user_token):
        # Prior cap was 20; verify 100 URLs is accepted now (schema-level).
        urls = [f"https://books.toscrape.com/catalogue/x_{i}.html" for i in range(100)]
        r = requests.post(f"{API}/scraper/jobs/bulk",
                          json={"urls": urls}, headers=_hdr(user_token), timeout=30)
        # These URLs are junk 404s but should still be accepted by the schema (invalid_url is only
        # for URLs failing urlparse). If none valid it returns 400. But 100 well-formed URLs pass.
        assert r.status_code == 200, r.text
        # Cleanup: nothing to do — jobs will just fail
        data = r.json()
        assert data["queued_count"] >= 1

    def test_cap_over_500_rejected(self, user_token):
        urls = [f"https://books.toscrape.com/catalogue/x_{i}.html" for i in range(501)]
        r = requests.post(f"{API}/scraper/jobs/bulk",
                          json={"urls": urls}, headers=_hdr(user_token), timeout=15)
        assert r.status_code == 422, r.text
