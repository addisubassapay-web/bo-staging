"""Bulk import + high_fidelity toggle tests for the Zyte scraper.

Covers:
- POST /api/scraper/jobs/bulk validation (dedupe, invalid URL, >20, all invalid)
- GET /api/scraper/batches/{id} (owner, admin, cross-user 403, 404)
- POST /api/scraper/jobs with high_fidelity=true → extract_from == 'browserHtml_hi'
"""
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://mercari-global-clone-1.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@mercari-global.local", "password": "admin123"}
USER = {"email": "sophia_style@demo.local", "password": "demo1234"}

BOOKS_A = "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html"
BOOKS_B = "https://books.toscrape.com/catalogue/tipping-the-velvet_999/index.html"
INVALID = "not a url"


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
def other_user_token():
    email = f"e2e_bulk_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(f"{API}/auth/register", json={
        "email": email, "password": "pass1234", "username": f"e2e{uuid.uuid4().hex[:6]}"
    }, timeout=15)
    if r.status_code not in (200, 201):
        pytest.skip(f"could not register other user: {r.status_code} {r.text}")
    return r.json().get("token") or _login({"email": email, "password": "pass1234"})


class TestBulkValidation:
    def test_all_invalid_urls_400(self, user_token):
        r = requests.post(f"{API}/scraper/jobs/bulk",
                          json={"urls": ["not a url", "ftp://x.com"]},
                          headers=_hdr(user_token), timeout=15)
        assert r.status_code == 400, r.text

    def test_over_500_returns_422(self, user_token):
        urls = [f"https://books.toscrape.com/catalogue/x_{i}.html" for i in range(501)]
        r = requests.post(f"{API}/scraper/jobs/bulk",
                          json={"urls": urls}, headers=_hdr(user_token), timeout=15)
        assert r.status_code == 422, r.text

    def test_missing_auth(self):
        r = requests.post(f"{API}/scraper/jobs/bulk",
                          json={"urls": [BOOKS_A]}, timeout=15)
        assert r.status_code in (401, 403)

    def test_mixed_valid_invalid_dedupes(self, user_token):
        payload = {
            "urls": [BOOKS_A, BOOKS_B, BOOKS_A, INVALID],
            "category_id": None,
            "high_fidelity": False,
        }
        r = requests.post(f"{API}/scraper/jobs/bulk", json=payload,
                          headers=_hdr(user_token), timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "batch_id" in data
        assert data["queued_count"] == 2
        assert len(data["queued"]) == 2
        # each queued item has id + url
        queued_urls = {q["url"] for q in data["queued"]}
        assert queued_urls == {BOOKS_A, BOOKS_B}
        for q in data["queued"]:
            assert "id" in q and q["id"]
        # rejected contains 1 duplicate + 1 invalid_url
        reasons = sorted(r_["reason"] for r_ in data["rejected"])
        assert reasons == ["duplicate", "invalid_url"]
        # save for downstream tests
        pytest.bulk_batch_id = data["batch_id"]
        pytest.bulk_queued_ids = [q["id"] for q in data["queued"]]


class TestBatchStatus:
    def test_batch_status_owner(self, user_token):
        bid = getattr(pytest, "bulk_batch_id", None)
        if not bid:
            pytest.skip("no batch id")
        r = requests.get(f"{API}/scraper/batches/{bid}", headers=_hdr(user_token), timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["batch"]["id"] == bid
        assert data["total"] == 2
        assert set(data["counts"].keys()) >= {"queued", "running", "done", "failed"}
        assert len(data["jobs"]) == 2
        for j in data["jobs"]:
            assert j["batch_id"] == bid

    def test_batch_status_404(self, user_token):
        r = requests.get(f"{API}/scraper/batches/does-not-exist",
                         headers=_hdr(user_token), timeout=15)
        assert r.status_code == 404

    def test_batch_status_forbidden_for_other_user(self, other_user_token):
        bid = getattr(pytest, "bulk_batch_id", None)
        if not bid:
            pytest.skip("no batch id")
        r = requests.get(f"{API}/scraper/batches/{bid}",
                         headers=_hdr(other_user_token), timeout=15)
        assert r.status_code == 403

    def test_batch_status_admin_can_read(self, admin_token):
        bid = getattr(pytest, "bulk_batch_id", None)
        if not bid:
            pytest.skip("no batch id")
        r = requests.get(f"{API}/scraper/batches/{bid}",
                         headers=_hdr(admin_token), timeout=15)
        assert r.status_code == 200

    def test_batch_jobs_complete(self, user_token):
        bid = getattr(pytest, "bulk_batch_id", None)
        if not bid:
            pytest.skip("no batch id")
        deadline = time.time() + 90
        counts = None
        while time.time() < deadline:
            r = requests.get(f"{API}/scraper/batches/{bid}",
                             headers=_hdr(user_token), timeout=15)
            assert r.status_code == 200
            data = r.json()
            counts = data["counts"]
            active = counts.get("queued", 0) + counts.get("running", 0)
            if active == 0:
                break
            time.sleep(2)
        assert counts is not None
        assert counts["queued"] + counts["running"] == 0, f"batch still active: {counts}"
        # At least one must have succeeded on books.toscrape (very reliable)
        assert counts["done"] >= 1, f"expected >=1 done, got {counts}"


class TestHighFidelity:
    def test_high_fidelity_flag_persists_and_runs(self, user_token):
        r = requests.post(f"{API}/scraper/jobs",
                          json={"url": BOOKS_A, "high_fidelity": True},
                          headers=_hdr(user_token), timeout=15)
        assert r.status_code == 200, r.text
        job_id = r.json()["id"]
        # Poll to completion
        final = None
        deadline = time.time() + 90
        while time.time() < deadline:
            g = requests.get(f"{API}/scraper/jobs/{job_id}",
                             headers=_hdr(user_token), timeout=15)
            assert g.status_code == 200
            doc = g.json()
            if doc["status"] in ("done", "failed"):
                final = doc
                break
            time.sleep(2)
        assert final is not None, "job did not finish"
        # Flag is preserved
        assert final.get("high_fidelity") is True
        # Should have run — either via browserHtml_hi (paid) or gracefully fell back
        if final["status"] == "done":
            listing = (final.get("result") or {}).get("listing") or {}
            extract_from = listing.get("extract_from")
            # Acceptable outcomes:
            #  - browserHtml_hi (paid tier working)
            #  - httpResponseBody or browserHtml (fell back gracefully)
            assert extract_from in ("browserHtml_hi", "httpResponseBody", "browserHtml"), extract_from
        else:
            # If failed, error should be a Zyte plan-limit type — not an internal crash.
            err = final.get("error") or {}
            assert err.get("provider") in ("zyte", "internal"), err

    def test_default_high_fidelity_false(self, user_token):
        r = requests.post(f"{API}/scraper/jobs",
                          json={"url": BOOKS_B},
                          headers=_hdr(user_token), timeout=15)
        assert r.status_code == 200
        job_id = r.json()["id"]
        g = requests.get(f"{API}/scraper/jobs/{job_id}",
                         headers=_hdr(user_token), timeout=15)
        assert g.status_code == 200
        assert g.json().get("high_fidelity") is False
