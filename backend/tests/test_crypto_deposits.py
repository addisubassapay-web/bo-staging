"""Tests for the new crypto & manual deposit system + admin approval flow."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fallback to reading frontend/.env
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                break

ADMIN = {"email": "admin@mercari.local", "password": "admin123"}
USER = {"email": "sophia_style@demo.local", "password": "demo1234"}


def _login(email, password):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    tok = r.json().get("access_token") or r.json().get("token")
    assert tok, f"no token in login response: {r.json()}"
    return tok, r.json().get("user") or {}


@pytest.fixture(scope="module")
def admin_headers():
    tok, _ = _login(**ADMIN)
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def user_headers():
    tok, _ = _login(**USER)
    return {"Authorization": f"Bearer {tok}"}


# ---------- Admin settings CRUD ----------
class TestAdminPaymentMethods:
    def test_get_settings_initial(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/admin/settings/payment-methods", headers=admin_headers)
        assert r.status_code == 200
        data = r.json()
        assert "crypto_addresses" in data
        assert "manual_payment_methods" in data
        assert isinstance(data["crypto_addresses"], dict)
        assert isinstance(data["manual_payment_methods"], list)

    def test_put_settings_persists(self, admin_headers):
        payload = {
            "crypto_addresses": {
                "BTC": "bc1qxy2test",
                "ETH": "",
                "USDC": "0xUSDCtest123",
                "USDT": "",
            },
            "manual_payment_methods": [
                {
                    "id": "bank-demo",
                    "name": "Bank Transfer — Demo",
                    "instructions": "Wire to account 12345 at BankDemo. Reference your username.",
                    "active": True,
                }
            ],
        }
        r = requests.put(f"{BASE_URL}/api/admin/settings/payment-methods", headers=admin_headers, json=payload)
        assert r.status_code == 200, r.text
        # verify persistence
        r2 = requests.get(f"{BASE_URL}/api/admin/settings/payment-methods", headers=admin_headers)
        assert r2.status_code == 200
        d = r2.json()
        assert d["crypto_addresses"]["BTC"] == "bc1qxy2test"
        assert d["crypto_addresses"]["USDC"] == "0xUSDCtest123"
        assert any(m["name"] == "Bank Transfer — Demo" for m in d["manual_payment_methods"])


# ---------- User deposit-methods endpoint ----------
class TestUserDepositMethods:
    def test_returns_only_configured(self, user_headers):
        r = requests.get(f"{BASE_URL}/api/wallet/deposit-methods", headers=user_headers)
        assert r.status_code == 200
        data = r.json()
        currencies = [c["currency"] for c in data["crypto"]]
        assert "BTC" in currencies and "USDC" in currencies
        # Empty ETH/USDT should be filtered out
        assert "ETH" not in currencies
        assert "USDT" not in currencies
        btc = next(c for c in data["crypto"] if c["currency"] == "BTC")
        assert btc["address"] == "bc1qxy2test"
        assert any(m["name"] == "Bank Transfer — Demo" for m in data["manual"])

    def test_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/wallet/deposit-methods")
        assert r.status_code in (401, 403)


# ---------- Pending deposit lifecycle ----------
class TestDepositLifecycle:
    def test_full_flow_crypto_approve(self, user_headers, admin_headers):
        # get current balance
        w = requests.get(f"{BASE_URL}/api/wallet", headers=user_headers)
        assert w.status_code == 200, w.text
        before = float(w.json().get("balance", 0))

        # submit crypto deposit
        body = {"amount": 25, "method": "crypto", "currency": "BTC",
                "reference": f"0xtesthash_{int(time.time())}", "note": "test crypto"}
        r = requests.post(f"{BASE_URL}/api/wallet/deposit/pending", headers=user_headers, json=body)
        assert r.status_code == 200, r.text
        dep_id = r.json()["id"]
        assert r.json()["status"] == "pending"

        # user can see it in mine
        r = requests.get(f"{BASE_URL}/api/wallet/deposits/mine", headers=user_headers)
        assert r.status_code == 200
        assert any(d["id"] == dep_id for d in r.json())

        # admin sees in pending list
        r = requests.get(f"{BASE_URL}/api/admin/deposits/pending?status=pending", headers=admin_headers)
        assert r.status_code == 200
        assert any(d["id"] == dep_id for d in r.json())

        # approve
        r = requests.post(f"{BASE_URL}/api/admin/deposits/{dep_id}/approve", headers=admin_headers)
        assert r.status_code == 200, r.text

        # balance credited
        w2 = requests.get(f"{BASE_URL}/api/wallet", headers=user_headers)
        after = float(w2.json().get("balance", 0))
        assert round(after - before, 2) == 25.0, f"expected +25, got before={before} after={after}"

        # cannot double-approve
        r = requests.post(f"{BASE_URL}/api/admin/deposits/{dep_id}/approve", headers=admin_headers)
        assert r.status_code == 400

    def test_manual_deposit_and_reject(self, user_headers, admin_headers):
        body = {"amount": 40, "method": "manual", "method_id": "bank-demo",
                "reference": f"BANKREF-{int(time.time())}", "note": "test manual"}
        r = requests.post(f"{BASE_URL}/api/wallet/deposit/pending", headers=user_headers, json=body)
        assert r.status_code == 200, r.text
        dep_id = r.json()["id"]

        # reject
        r = requests.post(f"{BASE_URL}/api/admin/deposits/{dep_id}/reject",
                          headers=admin_headers, json={"reason": "test reject"})
        assert r.status_code == 200

        # verify status
        r = requests.get(f"{BASE_URL}/api/admin/deposits/pending?status=rejected", headers=admin_headers)
        assert any(d["id"] == dep_id and d["status"] == "rejected" for d in r.json())

    def test_validation_errors(self, user_headers):
        # amount too small
        r = requests.post(f"{BASE_URL}/api/wallet/deposit/pending", headers=user_headers,
                          json={"amount": 0, "method": "crypto", "reference": "x"})
        assert r.status_code == 400
        # bad method
        r = requests.post(f"{BASE_URL}/api/wallet/deposit/pending", headers=user_headers,
                          json={"amount": 10, "method": "paypal", "reference": "x"})
        assert r.status_code == 400
        # missing reference
        r = requests.post(f"{BASE_URL}/api/wallet/deposit/pending", headers=user_headers,
                          json={"amount": 10, "method": "crypto", "reference": ""})
        assert r.status_code == 400

    def test_admin_only_endpoints(self, user_headers):
        for path in ["/api/admin/settings/payment-methods",
                     "/api/admin/deposits/pending"]:
            r = requests.get(f"{BASE_URL}{path}", headers=user_headers)
            assert r.status_code in (401, 403), f"{path} allowed non-admin: {r.status_code}"


# ---------- Withdraw still works ----------
class TestWithdraw:
    def test_withdraw_endpoint(self, user_headers):
        r = requests.post(f"{BASE_URL}/api/wallet/withdraw", headers=user_headers,
                          json={"amount": 5, "account_info": "BTC: bc1qtestext"})
        # accept 200 or 400 (insufficient balance) but not 500/404
        assert r.status_code in (200, 400), r.text
