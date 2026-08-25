"""Iteration 48 — AI Quality Polish tests.

Covers:
- Sanity import of services.product_ai
- GET /api/admin/products/ai-polish/status auth + shape
- POST /api/admin/products/ai-polish real LLM call (limit=3)
- Idempotency: second call must not overwrite already-polished rows
- force=true re-polishes an already-polished row
- Auth guards (401/403)
- limit clamping to 200
- Structural check of polished fields
- Permanence — GET /api/products total_count unchanged after polish
- Sanity of existing endpoints (categories, listings, products/:id)
"""
from __future__ import annotations

import asyncio
import os
import time
import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://marketplace-dropship.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@mercari.local"
ADMIN_PASS = "admin123"
USER_EMAIL = "sophia_style@demo.local"
USER_PASS = "demo1234"


def _login(email: str, password: str) -> str:
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login {email} failed: {r.status_code} {r.text[:300]}"
    tok = r.json().get("access_token") or r.json().get("token")
    assert tok, f"no token in login response: {r.json()}"
    return tok


@pytest.fixture(scope="module")
def admin_token():
    return _login(ADMIN_EMAIL, ADMIN_PASS)


@pytest.fixture(scope="module")
def user_token():
    return _login(USER_EMAIL, USER_PASS)


@pytest.fixture(scope="module")
def admin_h(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def user_h(user_token):
    return {"Authorization": f"Bearer {user_token}"}


# --- Direct DB access for verifying fields Pydantic strips ------------------
# NOTE: /api/admin/products serializes rows through ProductOut which does NOT
# declare ai_meta / polished_title / meta_title / meta_description / ai_polished_at,
# so those fields are dropped from the HTTP response. To verify polish results
# we read the products collection directly.
def _load_env(path: str = "/app/backend/.env"):
    kv = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                kv[k.strip()] = v.strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return kv


_ENV = _load_env()
_MONGO_URL = os.environ.get("MONGO_URL") or _ENV.get("MONGO_URL")
_DB_NAME = os.environ.get("DB_NAME") or _ENV.get("DB_NAME")


def _db_query(coll_op):
    """Run an async motor operation synchronously in tests."""
    async def _runner():
        client = AsyncIOMotorClient(_MONGO_URL)
        try:
            db = client[_DB_NAME]
            return await coll_op(db)
        finally:
            client.close()

    return asyncio.get_event_loop().run_until_complete(_runner()) if False else asyncio.run(_runner())


def _get_a_polished_product_from_db():
    async def op(db):
        return await db.products.find_one(
            {"ai_polished_at": {"$exists": True}, "ai_polish_failed": {"$ne": True}},
            {"_id": 0},
        )
    return _db_query(op)


# --- Sanity: import ---------------------------------------------------------
def test_import_product_ai_module():
    import importlib, sys
    sys.path.insert(0, "/app/backend")
    mod = importlib.import_module("services.product_ai")
    assert hasattr(mod, "polish_one")
    assert hasattr(mod, "polish_batch")


# --- Status endpoint --------------------------------------------------------
def test_status_endpoint_shape(admin_h):
    r = requests.get(f"{API}/admin/products/ai-polish/status", headers=admin_h, timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    for k in ("total_active", "polished", "failed", "remaining", "pct_complete"):
        assert k in data, f"missing key {k} in {data}"
    assert data["total_active"] >= 165, f"expected >=165 active, got {data['total_active']}"


def test_status_requires_admin_no_auth():
    r = requests.get(f"{API}/admin/products/ai-polish/status", timeout=15)
    assert r.status_code in (401, 403), f"expected 401/403 unauth, got {r.status_code}"


def test_status_forbidden_for_regular_user(user_h):
    r = requests.get(f"{API}/admin/products/ai-polish/status", headers=user_h, timeout=15)
    assert r.status_code == 403, f"expected 403, got {r.status_code} {r.text[:200]}"


# --- Auth guards on POST ----------------------------------------------------
def test_polish_requires_auth():
    r = requests.post(f"{API}/admin/products/ai-polish", json={"limit": 1}, timeout=15)
    assert r.status_code in (401, 403)


def test_polish_forbidden_regular_user(user_h):
    r = requests.post(f"{API}/admin/products/ai-polish", json={"limit": 1}, headers=user_h, timeout=15)
    assert r.status_code == 403


# --- Real LLM run -----------------------------------------------------------
@pytest.fixture(scope="module")
def first_run(admin_h):
    """Actual LLM polish call with limit=3.
    Uses force=true when all products are already polished so we still exercise the LLM path.
    """
    status = requests.get(f"{API}/admin/products/ai-polish/status", headers=admin_h, timeout=15).json()
    use_force = status.get("remaining", 0) == 0
    r = requests.post(
        f"{API}/admin/products/ai-polish",
        json={"limit": 3, "force": use_force},
        headers=admin_h,
        timeout=120,
    )
    assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text[:500]}"
    body = r.json()
    body["_used_force"] = use_force
    return body


def test_polish_real_llm_scanned_and_polished(first_run):
    data = first_run
    assert data.get("scanned") == 3, f"expected scanned=3, got {data}"
    polished = data.get("polished", 0)
    failures = data.get("failures", 0)
    assert polished + failures == data["scanned"], f"polished+failures != scanned: {data}"
    assert polished >= 1, f"expected polished>=1, got {polished}. Full: {data}"


def _get_a_polished_product(admin_h):
    return _get_a_polished_product_from_db()


def test_polished_product_has_ai_meta(first_run, admin_h):
    p = _get_a_polished_product(admin_h)
    assert p is not None, "no product with ai_polished_at found in DB"
    assert p.get("ai_meta"), "ai_meta missing"
    assert p["ai_meta"].get("polished_title"), "ai_meta.polished_title missing"
    assert p.get("ai_polished_at") is not None


# --- Structural constraints -------------------------------------------------
def test_polished_field_length_constraints(admin_h):
    p = _get_a_polished_product(admin_h)
    assert p is not None
    pt = p.get("polished_title") or ""
    mt = p.get("meta_title") or ""
    md = p.get("meta_description") or ""
    assert 0 < len(pt) <= 70, f"polished_title len={len(pt)}"
    assert len(mt) <= 60, f"meta_title len={len(mt)}"
    assert len(md) <= 155, f"meta_description len={len(md)}"
    pd = (p.get("ai_meta") or {}).get("polished_description") or ""
    # Not strict (LLM may vary), but must be non-empty
    assert len(pd) > 0, "polished_description empty"


# --- Idempotency ------------------------------------------------------------
def test_idempotency_second_run_preserves_first(admin_h, first_run):
    async def snapshot(db):
        docs = await db.products.find(
            {"ai_polished_at": {"$exists": True}, "ai_polish_failed": {"$ne": True}},
            {"_id": 0, "id": 1, "polished_title": 1, "ai_polished_at": 1},
        ).to_list(500)
        return docs

    before = _db_query(snapshot)
    assert before, "no polished rows to compare"
    before_map = {d["id"]: (d.get("polished_title"), d.get("ai_polished_at")) for d in before}

    # Second run — default force=false → should skip already polished rows
    r2 = requests.post(
        f"{API}/admin/products/ai-polish",
        json={"limit": 3},
        headers=admin_h, timeout=180,
    )
    assert r2.status_code == 200, r2.text

    after = _db_query(snapshot)
    after_map = {d["id"]: (d.get("polished_title"), d.get("ai_polished_at")) for d in after}

    for pid, (title, ts) in before_map.items():
        assert pid in after_map, f"product {pid} disappeared"
        a_title, a_ts = after_map[pid]
        assert a_title == title, f"title changed for {pid}: {title!r} -> {a_title!r}"
        assert a_ts == ts, f"ai_polished_at changed for {pid} without force: {ts} -> {a_ts}"


# --- Force flag -------------------------------------------------------------
def test_force_repolishes_row(admin_h):
    async def newest_ts(db):
        doc = await db.products.find_one(
            {"ai_polished_at": {"$exists": True}},
            sort=[("ai_polished_at", -1)],
            projection={"_id": 0, "ai_polished_at": 1},
        )
        return doc.get("ai_polished_at") if doc else None

    before_ts = _db_query(newest_ts)
    assert before_ts is not None

    time.sleep(1.2)

    r = requests.post(
        f"{API}/admin/products/ai-polish",
        json={"limit": 1, "force": True},
        headers=admin_h, timeout=120,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("scanned") == 1, body

    after_ts = _db_query(newest_ts)
    assert after_ts is not None
    assert after_ts > before_ts, f"expected newer ai_polished_at than {before_ts}, got {after_ts}"


# --- Limit validation -------------------------------------------------------
def test_limit_clamped_to_200_in_code():
    """Verify the clamp exists in the router source. Making a real limit=1000
    call is impractical here (would trigger ~200 real LLM calls costing ~$0.12
    and reliably hits the proxy's ~100s timeout → 502). Instead we assert the
    guard exists in the source code path, which is the authoritative clamp."""
    src = open("/app/backend/routers/products.py").read()
    assert "min(int(payload.get(\"limit\", 50)), 200)" in src or "min(int(payload.get('limit', 50)), 200)" in src, \
        "limit clamp to 200 not found in ai-polish route"


# --- Permanence --------------------------------------------------------------
def test_permanence_total_count_unchanged(admin_h):
    # Baseline
    r0 = requests.get(f"{API}/products?page=1&page_size=100", timeout=15)
    assert r0.status_code == 200
    total_before = r0.json().get("total")

    # Force one more polish
    requests.post(
        f"{API}/admin/products/ai-polish",
        json={"limit": 1, "force": True},
        headers=admin_h, timeout=120,
    )

    r1 = requests.get(f"{API}/products?page=1&page_size=100", timeout=15)
    total_after = r1.json().get("total")
    assert total_before == total_after, f"total changed: {total_before} -> {total_after}"


# --- Sanity of existing flows -----------------------------------------------
def test_products_list_ok():
    r = requests.get(f"{API}/products?page=1&page_size=5", timeout=15)
    assert r.status_code == 200
    assert "items" in r.json()


def test_product_by_id_ok():
    r = requests.get(f"{API}/products?page=1&page_size=1", timeout=15)
    items = r.json().get("items", [])
    if not items:
        pytest.skip("no products")
    pid = items[0]["id"]
    r2 = requests.get(f"{API}/products/{pid}", timeout=15)
    assert r2.status_code == 200
    assert r2.json().get("id") == pid


def test_categories_ok():
    r = requests.get(f"{API}/categories", timeout=15)
    assert r.status_code == 200
    body = r.json()
    # accept list or {items:[...]} shape
    cats = body if isinstance(body, list) else body.get("items") or body.get("categories") or []
    assert len(cats) >= 10, f"expected >=10 categories, got {len(cats)}"


def test_listings_ok():
    r = requests.get(f"{API}/listings", timeout=15)
    assert r.status_code == 200
    body = r.json()
    items = body if isinstance(body, list) else body.get("items") or body.get("listings") or []
    assert isinstance(items, list)
