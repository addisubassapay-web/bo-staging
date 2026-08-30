"""Zyte scraper pipeline tests — auth, enqueue, worker, admin views, R2 passthrough."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://ocean-marketplace.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@mercari-global.local", "password": "admin123"}
USER = {"email": "sophia_style@demo.local", "password": "demo1234"}

BOOKS_URL = "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html"


def _login(creds):
    r = requests.post(f"{API}/auth/login", json=creds, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin_token():
    return _login(ADMIN)


@pytest.fixture(scope="module")
def user_token():
    return _login(USER)


def _hdr(t):
    return {"Authorization": f"Bearer {t}"}


# -------- /status --------
class TestStatus:
    def test_status_admin_ok(self, admin_token):
        r = requests.get(f"{API}/scraper/status", headers=_hdr(admin_token), timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["zyte"]["enabled"] is True
        assert data["queue"]["provider"] == "arq"
        assert data["queue"]["redis_ok"] is True
        assert "redis_url" in data["queue"]
        assert data["storage"]["provider"] == "local_disk"
        assert data["storage"]["enabled"] is True  # Local disk always enabled

    def test_status_forbids_non_admin(self, user_token):
        r = requests.get(f"{API}/scraper/status", headers=_hdr(user_token), timeout=15)
        assert r.status_code == 403


# -------- POST /jobs --------
class TestCreateJob:
    def test_missing_auth(self):
        r = requests.post(f"{API}/scraper/jobs", json={"url": BOOKS_URL}, timeout=15)
        assert r.status_code in (401, 403)

    def test_invalid_url(self, user_token):
        r = requests.post(f"{API}/scraper/jobs", json={"url": "not a url"}, headers=_hdr(user_token), timeout=15)
        assert r.status_code == 400

    def test_non_http_scheme(self, user_token):
        r = requests.post(f"{API}/scraper/jobs", json={"url": "ftp://example.com/x"}, headers=_hdr(user_token), timeout=15)
        assert r.status_code == 400

    def test_create_ok(self, user_token):
        r = requests.post(f"{API}/scraper/jobs", json={"url": BOOKS_URL}, headers=_hdr(user_token), timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["status"] == "queued"
        assert data["url"] == BOOKS_URL
        assert "id" in data
        pytest.job_id = data["id"]


# -------- worker execution --------
class TestWorkerPipeline:
    def test_worker_completes_job(self, user_token):
        job_id = getattr(pytest, "job_id", None)
        if not job_id:
            pytest.skip("no job created")
        # Poll up to ~40s
        final = None
        for _ in range(40):
            r = requests.get(f"{API}/scraper/jobs/{job_id}", headers=_hdr(user_token), timeout=15)
            assert r.status_code == 200
            doc = r.json()
            if doc["status"] in ("done", "failed"):
                final = doc
                break
            time.sleep(1)
        assert final is not None, "job did not finish within 40s"
        assert final["status"] == "done", f"job failed: {final.get('error')}"
        listing = (final.get("result") or {}).get("listing") or {}
        assert listing.get("title"), "listing.title empty"
        assert listing.get("price") is not None, "listing.price missing"
        assert isinstance(listing.get("images"), list) and len(listing["images"]) >= 1
        # R2 passthrough — images should NOT be r2.dev/pub-* urls, they should be supplier URLs.
        for img in listing["images"]:
            assert "r2.dev" not in img and "r2.cloudflarestorage.com" not in img, \
                f"expected passthrough, got R2 URL: {img}"
            assert img.startswith("http"), img


# -------- GET /jobs/{id} auth --------
class TestJobAuth:
    def test_other_user_cannot_read(self, admin_token, user_token):
        # user's job — admin CAN read, another regular user cannot. We use a second regular user.
        job_id = getattr(pytest, "job_id", None)
        if not job_id:
            pytest.skip("no job")
        # Register a random user
        import uuid as _uuid
        email = f"e2e_{_uuid.uuid4().hex[:8]}@example.com"
        reg = requests.post(f"{API}/auth/register", json={
            "email": email, "password": "pass1234", "username": f"e2e{_uuid.uuid4().hex[:6]}"
        }, timeout=15)
        if reg.status_code not in (200, 201):
            pytest.skip(f"could not register test user: {reg.status_code} {reg.text}")
        other_token = reg.json().get("token") or _login({"email": email, "password": "pass1234"})
        r = requests.get(f"{API}/scraper/jobs/{job_id}", headers=_hdr(other_token), timeout=15)
        assert r.status_code == 403

    def test_admin_can_read(self, admin_token):
        job_id = getattr(pytest, "job_id", None)
        if not job_id:
            pytest.skip("no job")
        r = requests.get(f"{API}/scraper/jobs/{job_id}", headers=_hdr(admin_token), timeout=15)
        assert r.status_code == 200

    def test_not_found(self, user_token):
        r = requests.get(f"{API}/scraper/jobs/does-not-exist", headers=_hdr(user_token), timeout=15)
        assert r.status_code == 404


# -------- GET /jobs (mine) --------
class TestListMyJobs:
    def test_list(self, user_token):
        r = requests.get(f"{API}/scraper/jobs", headers=_hdr(user_token), timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "items" in data and isinstance(data["items"], list)
        assert data["count"] == len(data["items"])
        # newest first
        if len(data["items"]) >= 2:
            a, b = data["items"][0]["created_at"], data["items"][1]["created_at"]
            assert a >= b


# -------- GET /admin/jobs --------
class TestAdminList:
    def test_admin_list_all(self, admin_token):
        r = requests.get(f"{API}/scraper/admin/jobs", headers=_hdr(admin_token), timeout=15)
        assert r.status_code == 200
        assert "items" in r.json()

    def test_admin_list_filter(self, admin_token):
        r = requests.get(f"{API}/scraper/admin/jobs?status=failed", headers=_hdr(admin_token), timeout=15)
        assert r.status_code == 200
        data = r.json()
        for item in data["items"]:
            assert item["status"] == "failed"

    def test_admin_endpoint_forbids_user(self, user_token):
        r = requests.get(f"{API}/scraper/admin/jobs", headers=_hdr(user_token), timeout=15)
        assert r.status_code == 403
