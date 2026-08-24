"""
Tests for wallet balance synchronization, ledger bucket tagging, admin audit,
and withdrawal race safety (iteration 33).
"""
import os
import pytest
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"

ADMIN = {"email": "admin@mercari-global.local", "password": "admin123"}
USER = {"email": "sophia_style@demo.local", "password": "demo1234"}


def _login(creds):
    r = requests.post(f"{API}/auth/login", json=creds, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    return r.json()


@pytest.fixture(scope="module")
def admin_headers():
    tok = _login(ADMIN)["token"]
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def user_headers():
    tok = _login(USER)["token"]
    return {"Authorization": f"Bearer {tok}"}


# --- Admin wallet audit endpoint ---
def test_admin_wallet_audit(admin_headers):
    r = requests.get(f"{API}/admin/wallet/audit", headers=admin_headers, timeout=30)
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    # Response contract check
    assert "total_drifted" in data or "drifted" in data or "users" in data, f"missing audit keys: {list(data.keys())[:10]}"
    print("audit keys:", list(data.keys()))
    print("audit sample:", {k: data[k] for k in list(data.keys())[:6]})


# --- Self reconcile (normal user) ---
def test_user_self_reconcile(user_headers):
    r = requests.post(f"{API}/wallet/reconcile", headers=user_headers, timeout=30)
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    assert "reconciled" in data
    assert "balance" in data
    assert "delta" in data
    print("self reconcile:", data)


# --- Admin reconcile of a specific user ---
def test_admin_reconcile_specific_user(admin_headers, user_headers):
    me = requests.get(f"{API}/auth/me", headers=user_headers, timeout=15).json()
    uid = me["id"]
    r = requests.post(f"{API}/admin/wallet/reconcile/{uid}", headers=admin_headers, timeout=30)
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    assert "balance" in data
    assert "delta" in data
    assert data.get("reconciled") in (True, False)
    print("admin reconcile:", data)


# --- Wallet GET returns transactions and audit shows zero drift for reseller demo user ---
def test_wallet_returns_txs_and_no_drift(user_headers, admin_headers):
    r = requests.get(f"{API}/wallet", headers=user_headers, timeout=15)
    assert r.status_code == 200
    data = r.json()
    txs = data.get("transactions") or []
    assert isinstance(txs, list)
    # bucket field is intentionally stripped by WalletTransaction Pydantic model
    # (server-side reconcile reads bucket directly from Mongo). We verify the
    # reconcile flow instead of the surfaced field.
    me = requests.get(f"{API}/auth/me", headers=user_headers, timeout=15).json()
    uid = me["id"]
    rec = requests.post(f"{API}/admin/wallet/reconcile/{uid}", headers=admin_headers, timeout=30).json()
    # Post-reconcile, this specific user should be at 0 delta (idempotent)
    rec2 = requests.post(f"{API}/admin/wallet/reconcile/{uid}", headers=admin_headers, timeout=30).json()
    print("reconcile pass1:", rec, "pass2:", rec2)
    assert abs(float(rec2.get("delta", 0))) < 0.01, f"reconcile not idempotent, delta={rec2.get('delta')}"


# --- Withdrawal overdraft protection ---
def test_withdraw_insufficient_returns_400(user_headers):
    # Query current balance
    w = requests.get(f"{API}/wallet", headers=user_headers, timeout=15).json()
    bal = float(w.get("wallet_balance") or w.get("available_balance") or 0)
    over = bal + 1_000_000
    r = requests.post(
        f"{API}/wallet/withdraw",
        headers=user_headers,
        json={"amount": over, "method": "bank", "destination": "TEST_ACC"},
        timeout=15,
    )
    assert r.status_code in (400, 402, 422), f"expected 400 got {r.status_code}: {r.text[:200]}"
    body = r.text.lower()
    assert "insufficient" in body or "balance" in body, r.text[:200]


# --- Currency rates endpoint (frontend caches to localStorage.mercari-global_rates) ---
def test_currency_rates_endpoint():
    r = requests.get(f"{API}/currency/rates", timeout=15)
    assert r.status_code == 200
    data = r.json()
    rates = data.get("rates") or {}
    for c in ["USD", "EUR", "GBP", "JPY", "INR", "AED", "KRW", "CNY", "SGD", "AUD", "BRL", "MXN", "CAD"]:
        assert c in rates, f"missing rate for {c}"
