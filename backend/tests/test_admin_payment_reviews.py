"""Admin unified Payment Reviews queue.

Endpoint under test: GET /api/admin/payment-reviews
Combines pending top-up deposits, resubmitted top-up deposits, and stuck
escrow orders. Each row carries an SLA badge (fresh/attention/urgent/overdue).
"""
from __future__ import annotations

import os
import uuid

import pytest
import requests

API = os.environ.get("E2E_API_URL") or "http://127.0.0.1:8001/api"


def _h(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def admin_token() -> str:
    r = requests.post(f"{API}/auth/login",
                      json={"email": "admin@mercari.local", "password": "admin123"}, timeout=15)
    r.raise_for_status()
    return r.json()["token"]


def _register(prefix: str) -> tuple[str, dict]:
    uid = uuid.uuid4().hex[:8]
    r = requests.post(f"{API}/auth/register",
                      json={"email": f"{prefix}_{uid}@e2e.com", "password": "pass1234", "username": f"{prefix}{uid}"}, timeout=15)
    r.raise_for_status()
    tok = r.json()["token"]
    me = requests.get(f"{API}/auth/me", headers=_h(tok), timeout=15).json()
    return tok, me


def _make_deposit(buyer_tok: str, amount: float = 30.0) -> dict:
    r = requests.post(f"{API}/wallet/deposit/pending", headers=_h(buyer_tok),
                      json={"amount": amount, "method": "crypto", "currency": "BTC",
                            "reference": f"tx_{uuid.uuid4().hex[:8]}", "screenshot_url": "https://picsum.photos/300"},
                      timeout=15)
    r.raise_for_status()
    return r.json()


def test_non_admin_forbidden():
    buyer_tok, _ = _register("noadmin")
    r = requests.get(f"{API}/admin/payment-reviews", headers=_h(buyer_tok), timeout=15)
    assert r.status_code in (401, 403)


def test_shape_and_counts(admin_token):
    r = requests.get(f"{API}/admin/payment-reviews", headers=_h(admin_token), timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    for key in ("counts", "pending_deposits", "resubmitted_deposits", "stuck_escrow", "generated_at"):
        assert key in body, f"missing {key}"
    counts = body["counts"]
    assert counts["total"] == counts["pending_deposits"] + counts["resubmitted_deposits"] + counts["stuck_escrow"]


def test_pending_deposit_appears_with_sla(admin_token):
    buyer_tok, _ = _register("dep")
    dep = _make_deposit(buyer_tok, amount=42.0)
    r = requests.get(f"{API}/admin/payment-reviews", headers=_h(admin_token), timeout=15)
    body = r.json()
    ids = {d["id"] for d in body["pending_deposits"]}
    assert dep["id"] in ids
    row = next(d for d in body["pending_deposits"] if d["id"] == dep["id"])
    assert row["amount"] == 42.0
    assert row["sla"]["tier"] in ("fresh", "attention", "urgent", "overdue")
    assert row["sla"]["label"]
    assert row["deep_link"].startswith("/admin/deposits/")


def test_resubmitted_appears_in_resubmit_section(admin_token):
    buyer_tok, _ = _register("re")
    dep = _make_deposit(buyer_tok, amount=17.0)
    requests.post(f"{API}/admin/deposits/{dep['id']}/reject", headers=_h(admin_token),
                  json={"reason": "unclear"}, timeout=15).raise_for_status()
    requests.post(f"{API}/wallet/deposits/{dep['id']}/resubmit", headers=_h(buyer_tok),
                  json={"screenshot_url": "https://picsum.photos/303"}, timeout=15).raise_for_status()

    r = requests.get(f"{API}/admin/payment-reviews", headers=_h(admin_token), timeout=15)
    body = r.json()
    # Should now appear in resubmitted_deposits, NOT pending_deposits.
    pending_ids = {d["id"] for d in body["pending_deposits"]}
    resub_ids = {d["id"] for d in body["resubmitted_deposits"]}
    assert dep["id"] not in pending_ids
    assert dep["id"] in resub_ids
    row = next(d for d in body["resubmitted_deposits"] if d["id"] == dep["id"])
    assert row["resubmit_count"] == 1
    assert row["admin_note"] == "" or row["admin_note"] is None or row["admin_note"] == "unclear"
