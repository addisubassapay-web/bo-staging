"""
E2E test for the buyer→seller pickup→delivery flow (Jan 2026).

Flow:
  buyer places order → POST /api/orders
  seller accepts     → POST /api/orders/{id}/pickup
  buyer confirms     → POST /api/orders/{id}/confirm-delivery

Verifies fulfillment_status transitions and that seller frozen earnings
are released to available on delivery confirmation.
Also does a light regression on admin/orders + admin/seller-applications.
"""
import os
import time
import uuid
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@mercari.local"
ADMIN_PASSWORD = "admin123"


def _register(session, prefix):
    ts = int(time.time() * 1000)
    email = f"e2e_{prefix}_{ts}_{uuid.uuid4().hex[:6]}@example.com"
    username = f"e2e{prefix}{ts}{uuid.uuid4().hex[:4]}"
    payload = {"email": email, "username": username, "password": "pass1234", "name": f"E2E {prefix}"}
    r = session.post(f"{API}/auth/register", json=payload, timeout=30)
    assert r.status_code in (200, 201), f"register failed: {r.status_code} {r.text[:400]}"
    data = r.json()
    token = data.get("access_token") or data.get("token") or (data.get("user") or {}).get("access_token")
    user = data.get("user") or data
    assert token, f"no token in register response: {data}"
    return token, user, email


def _client(token=None):
    s = requests.Session()
    s.headers["Content-Type"] = "application/json"
    if token:
        s.headers["Authorization"] = f"Bearer {token}"
    return s


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text[:300]}"
    tok = r.json().get("access_token") or r.json().get("token")
    assert tok
    return tok


def test_admin_login_and_regression(admin_token):
    """Regression: admin/orders + admin/seller-applications return 200."""
    s = _client(admin_token)
    r1 = s.get(f"{API}/admin/orders", timeout=30)
    assert r1.status_code == 200, f"/admin/orders → {r1.status_code} {r1.text[:200]}"
    r2 = s.get(f"{API}/admin/seller-applications", timeout=30)
    assert r2.status_code == 200, f"/admin/seller-applications → {r2.status_code} {r2.text[:200]}"


@pytest.fixture(scope="module")
def e2e_context(admin_token):
    """Set up buyer + use admin as the seller (admin bypasses seller verification)."""
    # Buyer
    buyer_token, buyer, _ = _register(requests.Session(), "buyer")
    buyer_id = buyer["id"]

    admin = _client(admin_token)
    # Get admin's own user record for id
    r = admin.get(f"{API}/auth/me", timeout=15)
    assert r.status_code == 200, f"admin /me failed: {r.status_code} {r.text[:200]}"
    admin_user = r.json()
    seller_id = admin_user["id"]

    # Top up buyer wallet so they can afford the order.
    r = admin.post(
        f"{API}/admin/users/{buyer_id}/wallet-adjust",
        json={"delta": 500.0, "description": "e2e buyer seed", "bucket": "available"},
        timeout=30,
    )
    assert r.status_code in (200, 201), f"wallet-adjust buyer failed: {r.status_code} {r.text[:300]}"

    # Also credit admin/seller some available balance so pickup wholesale can debit.
    r = admin.post(
        f"{API}/admin/users/{seller_id}/wallet-adjust",
        json={"delta": 500.0, "description": "e2e seller seed", "bucket": "available"},
        timeout=30,
    )
    assert r.status_code in (200, 201), f"wallet-adjust seller failed: {r.status_code} {r.text[:300]}"

    # Fetch first category to use its id
    cats = requests.get(f"{API}/categories", timeout=15).json()
    assert isinstance(cats, list) and cats, f"no categories: {cats}"
    cat_id = cats[0].get("id") or cats[0].get("_id")
    listing_payload = {
        "title": f"TEST_E2E_LISTING_{uuid.uuid4().hex[:6]}",
        "description": "E2E test listing",
        "price": 20.0,
        "category_id": cat_id,
        "condition": "new",
        "images": ["https://picsum.photos/300"],
        "shipping_paid_by": "seller",
    }
    r = admin.post(f"{API}/listings", json=listing_payload, timeout=30)
    assert r.status_code in (200, 201), f"create listing failed: {r.status_code} {r.text[:400]}"
    listing = r.json()
    listing_id = listing["id"]

    return {
        "buyer_token": buyer_token, "seller_token": admin_token,
        "buyer_id": buyer_id, "seller_id": seller_id,
        "listing_id": listing_id, "admin": admin,
    }


def test_full_pickup_deliver_flow(e2e_context):
    ctx = e2e_context
    buyer = _client(ctx["buyer_token"])
    seller = _client(ctx["seller_token"])
    admin = ctx["admin"]

    # 1. Buyer places order
    order_payload = {
        "listing_id": ctx["listing_id"],
        "quantity": 1,
        "shipping_address": {
            "full_name": "E2E Buyer", "street": "1 Test St", "city": "Testville",
            "state": "TS", "zip": "00000", "country": "USA",
        },
        "payment_method": "wallet",
    }
    r = buyer.post(f"{API}/orders", json=order_payload, timeout=30)
    assert r.status_code in (200, 201), f"place order failed: {r.status_code} {r.text[:400]}"
    order = r.json()
    oid = order["id"]
    assert order.get("fulfillment_status") == "pending_pickup"
    assert order.get("pickup_deadline")

    # 2. Seller accepts (pickup)
    r = seller.post(f"{API}/orders/{oid}/pickup", json={}, timeout=30)
    assert r.status_code == 200, f"pickup failed: {r.status_code} {r.text[:400]}"
    picked = r.json()
    assert picked.get("fulfillment_status") == "picked", f"expected picked, got {picked.get('fulfillment_status')}"
    assert picked.get("picked_up_at")

    # Verify seller wallet has frozen (escrow) balance
    r = seller.get(f"{API}/wallet", timeout=15)
    assert r.status_code == 200
    wallet_after_pick = r.json()
    frozen_before_release = float(wallet_after_pick.get("frozen_balance") or 0.0)
    assert frozen_before_release > 0, f"expected non-zero frozen, got {frozen_before_release}"

    # 3. Buyer confirms delivery
    r = buyer.post(f"{API}/orders/{oid}/confirm-delivery", json={}, timeout=30)
    assert r.status_code == 200, f"confirm-delivery failed: {r.status_code} {r.text[:400]}"
    delivered = r.json()
    assert delivered.get("status") == "delivered"
    assert delivered.get("shipping_status") == "delivered"
    assert delivered.get("delivery_confirmed_at")
    assert delivered.get("funds_released") is True

    # 4. Verify seller frozen balance decreased (funds released to available)
    r = seller.get(f"{API}/wallet", timeout=15)
    assert r.status_code == 200
    wallet_after_release = r.json()
    frozen_after = float(wallet_after_release.get("frozen_balance") or 0.0)
    assert frozen_after < frozen_before_release, (
        f"frozen should decrease after release: before={frozen_before_release} after={frozen_after}"
    )

    # 5. GET /api/orders returns this order for buyer (as buyer)
    r = buyer.get(f"{API}/orders", timeout=15)
    assert r.status_code == 200
    buyer_orders = r.json()
    ids = [o["id"] for o in (buyer_orders if isinstance(buyer_orders, list) else buyer_orders.get("orders", []))]
    assert oid in ids, "Order not visible to buyer via GET /orders"

    # 6. GET /api/orders?role=seller returns this order for seller too
    r = seller.get(f"{API}/orders?role=seller", timeout=15)
    assert r.status_code == 200
    seller_orders = r.json()
    ids = [o["id"] for o in (seller_orders if isinstance(seller_orders, list) else seller_orders.get("orders", []))]
    assert oid in ids, "Order not visible to seller via GET /orders?role=seller"

    # 7. Confirm-delivery is idempotent
    r = buyer.post(f"{API}/orders/{oid}/confirm-delivery", json={}, timeout=15)
    assert r.status_code == 200, f"idempotent confirm-delivery failed: {r.status_code}"
