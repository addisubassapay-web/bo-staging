"""Phase 1 Trust & Payments backend tests.

pytest.ini uses -n 2 --dist loadscope which pins a class to a single worker.
So the full e2e verification -> seller apply -> admin review journey is kept
in ONE class (TestPhase1E2E) sharing a class-scoped user fixture.

Independent sanity tests live in their own classes.
"""
import os
import time
import uuid
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    from pathlib import Path
    for line in Path("/app/frontend/.env").read_text().splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
            break

API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@mercari.local"
ADMIN_PASSWORD = "admin123"


def _post(path, json=None, token=None, expect=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = requests.post(f"{API}{path}", json=json or {}, headers=headers, timeout=30)
    if expect is not None:
        assert r.status_code == expect, f"POST {path} expected {expect} got {r.status_code}: {r.text}"
    return r


def _get(path, token=None, params=None, expect=None):
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = requests.get(f"{API}{path}", headers=headers, params=params, timeout=30)
    if expect is not None:
        assert r.status_code == expect, f"GET {path} expected {expect} got {r.status_code}: {r.text}"
    return r


def _put(path, json=None, token=None, expect=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = requests.put(f"{API}{path}", json=json or {}, headers=headers, timeout=30)
    if expect is not None:
        assert r.status_code == expect, f"PUT {path} expected {expect} got {r.status_code}: {r.text}"
    return r


def _admin_token():
    r = _post("/auth/login", {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, expect=200)
    return r.json()["token"]


def _other_category_id():
    r = _get("/categories", expect=200)
    for c in r.json():
        if c.get("slug") == "other":
            return c["id"]
    return r.json()[0]["id"]


# ============================================================
# Sanity / existing flows (independent, safe to parallelize)
# ============================================================
class TestSanityExistingFlows:
    def test_admin_login(self):
        r = _post("/auth/login", {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, expect=200)
        assert "token" in r.json()

    def test_login_demo_user(self):
        # sophia was verified during dev; test another to confirm login still works
        r = _post("/auth/login", {"email": "urban_finds@demo.local", "password": "demo1234"}, expect=200)
        assert "token" in r.json()

    def test_categories_list(self):
        r = _get("/categories", expect=200)
        assert isinstance(r.json(), list) and len(r.json()) > 0

    def test_listings_list(self):
        r = _get("/listings", expect=200)
        assert isinstance(r.json(), list)

    def test_sync_status_public(self):
        r = _get("/sync/status", expect=200)
        assert isinstance(r.json(), dict)

    def test_admin_stats_has_pending_seller_apps(self):
        r = _get("/admin/stats", token=_admin_token(), expect=200)
        data = r.json()
        assert "pending_seller_apps" in data
        assert isinstance(data["pending_seller_apps"], int)

    def test_favorites_and_cart(self):
        tok = _admin_token()
        assert _get("/favorites", token=tok).status_code == 200
        assert _get("/cart", token=tok).status_code == 200


# ============================================================
# Phase 1 full end-to-end journey — one class = one worker
# ============================================================
class TestPhase1E2E:
    @pytest.fixture(scope="class")
    def ctx(self):
        ts = int(time.time())
        email = f"e2e_phase1_{ts}_{uuid.uuid4().hex[:6]}@example.com"
        username = f"e2e{ts}{uuid.uuid4().hex[:4]}"
        r = _post("/auth/register",
                  {"email": email, "username": username, "password": "pass1234"}, expect=200)
        data = r.json()
        return {
            "email": email, "username": username, "password": "pass1234",
            "token": data["token"], "id": data["user"]["id"],
            "admin_token": _admin_token(),
        }

    # -------- Email verification --------
    def test_01_email_send_returns_mock_token(self, ctx):
        r = _post("/verify/email/send", {}, token=ctx["token"], expect=200)
        d = r.json()
        assert d.get("dev_mock") is True
        assert d.get("token")
        ctx["email_token"] = d["token"]

    def test_02_email_confirm_invalid_400(self, ctx):
        r = _post("/verify/email/confirm", {"token": "invalid_xyz"}, token=ctx["token"])
        assert r.status_code == 400

    def test_03_email_confirm_valid(self, ctx):
        r = _post("/verify/email/confirm", {"token": ctx["email_token"]},
                  token=ctx["token"], expect=200)
        assert r.json().get("email_verified") is True
        me = _get("/auth/me", token=ctx["token"], expect=200).json()
        assert me.get("email_verified") is True

    def test_04_email_confirm_reused_400(self, ctx):
        r = _post("/verify/email/confirm", {"token": ctx["email_token"]}, token=ctx["token"])
        assert r.status_code == 400

    def test_05_email_send_already_verified(self, ctx):
        r = _post("/verify/email/send", {}, token=ctx["token"], expect=200)
        assert r.json().get("already_verified") is True

    # -------- Phone verification --------
    def test_06_phone_send_short_rejected(self, ctx):
        r = _post("/verify/phone/send", {"phone": "123"}, token=ctx["token"])
        assert r.status_code == 400

    def test_07_phone_send_mock_code(self, ctx):
        r = _post("/verify/phone/send", {"phone": "+15551234567"},
                  token=ctx["token"], expect=200)
        d = r.json()
        assert d.get("dev_mock") is True
        assert d.get("code") and len(d["code"]) == 6 and d["code"].isdigit()
        assert d.get("phone") == "+15551234567"
        ctx["phone_code"] = d["code"]
        ctx["phone"] = "+15551234567"

    def test_08_phone_confirm_wrong_400(self, ctx):
        wrong = "000000" if ctx["phone_code"] != "000000" else "111111"
        r = _post("/verify/phone/confirm",
                  {"phone": ctx["phone"], "code": wrong}, token=ctx["token"])
        assert r.status_code == 400

    def test_09_phone_confirm_correct(self, ctx):
        r = _post("/verify/phone/confirm",
                  {"phone": ctx["phone"], "code": ctx["phone_code"]},
                  token=ctx["token"], expect=200)
        d = r.json()
        assert d.get("phone_verified") is True
        assert d.get("phone") == ctx["phone"]
        me = _get("/auth/me", token=ctx["token"], expect=200).json()
        assert me.get("phone_verified") is True and me.get("phone") == ctx["phone"]

    # -------- Seller apply gating --------
    def test_10_apply_blocks_unverified_user(self):
        ts = int(time.time())
        email = f"e2e_block_{ts}_{uuid.uuid4().hex[:6]}@example.com"
        username = f"blk{ts}{uuid.uuid4().hex[:4]}"
        r = _post("/auth/register",
                  {"email": email, "username": username, "password": "pass1234"}, expect=200)
        tok = r.json()["token"]
        r2 = _post("/seller/apply", {"legal_name": "T", "tax_id": "1234"}, token=tok)
        assert r2.status_code == 400
        assert "email" in r2.text.lower()

    def test_11_apply_success_and_tax_id_masked(self, ctx):
        payload = {
            "legal_name": "Jane Doe", "business_name": "Doe Vintage",
            "business_type": "individual", "tax_id": "987654321",
            "country": "US", "address_line1": "1 Test St", "city": "Testville",
            "state": "CA", "postal_code": "94000", "phone": ctx["phone"],
            "payout_method": "stripe_connect",
        }
        r = _post("/seller/apply", payload, token=ctx["token"], expect=200)
        d = r.json()
        assert d["status"] == "pending"
        assert d["tax_id"] == "****4321"
        assert d["user_id"] == ctx["id"]
        ctx["seller_app_id"] = d["id"]
        me = _get("/auth/me", token=ctx["token"], expect=200).json()
        assert me.get("seller_status") == "pending"

    def test_12_get_my_application(self, ctx):
        r = _get("/seller/application", token=ctx["token"], expect=200)
        d = r.json()
        assert d is not None and d["id"] == ctx["seller_app_id"]

    def test_13_duplicate_pending_blocked(self, ctx):
        r = _post("/seller/apply", {"legal_name": "Dup", "tax_id": "1111"}, token=ctx["token"])
        assert r.status_code == 400

    # -------- Stripe Connect mock --------
    def test_14_stripe_onboard_mock(self, ctx):
        r = _post("/stripe/connect/onboard", {}, token=ctx["token"], expect=200)
        d = r.json()
        assert d.get("stripe_account_id", "").startswith("acct_mock_")
        assert d.get("stripe_status") == "active"
        assert d.get("dev_mock") is True
        ctx["acct_id"] = d["stripe_account_id"]

    def test_15_stripe_onboard_idempotent(self, ctx):
        r = _post("/stripe/connect/onboard", {}, token=ctx["token"], expect=200)
        d = r.json()
        assert d.get("already_active") is True
        assert d.get("stripe_account_id") == ctx["acct_id"]

    def test_16_stripe_status(self, ctx):
        r = _get("/stripe/connect/status", token=ctx["token"], expect=200)
        d = r.json()
        assert d.get("stripe_status") == "active"
        assert d.get("stripe_account_id") == ctx["acct_id"]

    # -------- Admin queue --------
    def test_17_admin_list_apps_contains_current(self, ctx):
        r = _get("/admin/seller-applications", token=ctx["admin_token"], expect=200)
        assert ctx["seller_app_id"] in [a["id"] for a in r.json()]

    def test_18_admin_endpoint_forbids_non_admin(self, ctx):
        r = _get("/admin/seller-applications", token=ctx["token"])
        assert r.status_code == 403

    def test_19_admin_filter_pending(self, ctx):
        r = _get("/admin/seller-applications", token=ctx["admin_token"],
                 params={"status_filter": "pending"}, expect=200)
        assert all(a["status"] == "pending" for a in r.json())
        assert ctx["seller_app_id"] in [a["id"] for a in r.json()]

    def test_20_listing_gate_blocks_pending_user(self, ctx):
        cat_id = _other_category_id()
        payload = {
            "title": "Blocked", "description": "x", "price": 10.0,
            "category_id": cat_id, "condition": "good",
            "images": ["https://example.com/a.jpg"],
        }
        r = _post("/listings", payload, token=ctx["token"])
        assert r.status_code == 403, r.text

    def test_21_admin_approve_flips_user(self, ctx):
        r = _put(f"/admin/seller-applications/{ctx['seller_app_id']}",
                 {"status": "approved", "admin_notes": "Looks good"},
                 token=ctx["admin_token"], expect=200)
        assert r.json().get("status") == "approved"
        me = _get("/auth/me", token=ctx["token"], expect=200).json()
        assert me.get("seller_status") == "approved"

    def test_22_listing_creation_after_approval(self, ctx):
        cat_id = _other_category_id()
        payload = {
            "title": "Approved Listing TEST", "description": "x", "price": 15.0,
            "category_id": cat_id, "condition": "good",
            "images": ["https://example.com/a.jpg"],
        }
        r = _post("/listings", payload, token=ctx["token"], expect=200)
        assert r.json()["title"] == "Approved Listing TEST"

    def test_23_notification_created_on_approval(self, ctx):
        r = _get("/notifications", token=ctx["token"], expect=200)
        titles = [n.get("title", "").lower() for n in r.json()]
        assert any("approved" in t for t in titles)

    def test_24_admin_can_bypass_listing_gate(self, ctx):
        cat_id = _other_category_id()
        payload = {
            "title": "Admin Direct TEST", "description": "x", "price": 5.0,
            "category_id": cat_id, "condition": "good",
            "images": ["https://example.com/a.jpg"],
        }
        r = _post("/listings", payload, token=ctx["admin_token"], expect=200)
        assert r.json()["title"] == "Admin Direct TEST"

    # -------- Reject flow (separate user) --------
    def test_25_reject_flow(self, ctx):
        ts = int(time.time())
        email = f"e2e_reject_{ts}_{uuid.uuid4().hex[:6]}@example.com"
        username = f"rej{ts}{uuid.uuid4().hex[:4]}"
        r = _post("/auth/register",
                  {"email": email, "username": username, "password": "pass1234"}, expect=200)
        tok = r.json()["token"]
        et = _post("/verify/email/send", {}, token=tok, expect=200).json()["token"]
        _post("/verify/email/confirm", {"token": et}, token=tok, expect=200)
        pc = _post("/verify/phone/send", {"phone": "+15559990000"},
                   token=tok, expect=200).json()["code"]
        _post("/verify/phone/confirm", {"phone": "+15559990000", "code": pc},
              token=tok, expect=200)
        app = _post("/seller/apply", {"legal_name": "R", "tax_id": "5555"},
                    token=tok, expect=200).json()
        r2 = _put(f"/admin/seller-applications/{app['id']}",
                  {"status": "rejected", "admin_notes": "Incomplete info"},
                  token=ctx["admin_token"], expect=200)
        assert r2.json()["status"] == "rejected"
        me = _get("/auth/me", token=tok, expect=200).json()
        assert me["seller_status"] == "rejected"
