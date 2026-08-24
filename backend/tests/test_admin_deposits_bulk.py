"""Bulk approve/reject for admin deposit reviews — Feb 2026."""
from __future__ import annotations

import os
import uuid

import pytest
import requests

API = os.environ.get("E2E_API_URL") or "http://127.0.0.1:8001/api"


def _h(tok): return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{API}/auth/login",
                      json={"email": "admin@mercari.local", "password": "admin123"}, timeout=15)
    return r.json()["token"]


def _register(prefix):
    uid = uuid.uuid4().hex[:8]
    r = requests.post(f"{API}/auth/register",
                      json={"email": f"{prefix}_{uid}@e2e.com", "password": "pass1234", "username": f"{prefix}{uid}"}, timeout=15)
    r.raise_for_status()
    return r.json()["token"]


def _mk_deposit(buyer_tok, amount=25.0):
    r = requests.post(f"{API}/wallet/deposit/pending", headers=_h(buyer_tok),
                      json={"amount": amount, "method": "crypto", "currency": "BTC",
                            "reference": f"ref_{uuid.uuid4().hex[:6]}",
                            "screenshot_url": "https://picsum.photos/300"}, timeout=15)
    return r.json()


def test_bulk_approve_all_succeed(admin_token):
    buyer_tok = _register("bulkA")
    ids = [_mk_deposit(buyer_tok)["id"] for _ in range(3)]
    r = requests.post(f"{API}/admin/deposits/bulk-approve", headers=_h(admin_token),
                      json={"ids": ids}, timeout=20)
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["approved"] == 3
    assert b["total"] == 3
    assert all(item["ok"] for item in b["results"])


def test_bulk_reject_all_succeed(admin_token):
    buyer_tok = _register("bulkR")
    ids = [_mk_deposit(buyer_tok)["id"] for _ in range(2)]
    r = requests.post(f"{API}/admin/deposits/bulk-reject", headers=_h(admin_token),
                      json={"ids": ids, "reason": "test batch reject"}, timeout=20)
    assert r.status_code == 200
    b = r.json()
    assert b["rejected"] == 2
    # After bulk reject, each deposit should have admin_note set.
    for dep_id in ids:
        r2 = requests.get(f"{API}/admin/deposits/pending?status_filter=rejected",
                          headers=_h(admin_token), timeout=15)
        found = next((d for d in r2.json() if d["id"] == dep_id), None)
        assert found and found["admin_note"] == "test batch reject"


def test_bulk_approve_skips_non_pending(admin_token):
    buyer_tok = _register("bulkS")
    ok_id = _mk_deposit(buyer_tok)["id"]
    already = _mk_deposit(buyer_tok)["id"]
    # Manually reject `already` first.
    requests.post(f"{API}/admin/deposits/{already}/reject", headers=_h(admin_token),
                  json={"reason": "pre-reject"}, timeout=15)
    r = requests.post(f"{API}/admin/deposits/bulk-approve", headers=_h(admin_token),
                      json={"ids": [ok_id, already, "nonexistent-id-xyz"]}, timeout=20)
    b = r.json()
    assert b["approved"] == 1  # only the fresh pending one
    kinds = {row["id"]: row for row in b["results"]}
    assert kinds[ok_id]["ok"] is True
    assert kinds[already]["ok"] is False and "already" in kinds[already]["error"]
    assert kinds["nonexistent-id-xyz"]["ok"] is False


def test_bulk_empty_and_cap(admin_token):
    r = requests.post(f"{API}/admin/deposits/bulk-approve", headers=_h(admin_token),
                      json={"ids": []}, timeout=15)
    assert r.status_code == 400
    r = requests.post(f"{API}/admin/deposits/bulk-approve", headers=_h(admin_token),
                      json={"ids": [str(i) for i in range(101)]}, timeout=15)
    assert r.status_code == 400


def test_bulk_requires_admin():
    buyer_tok = _register("bulkX")
    r = requests.post(f"{API}/admin/deposits/bulk-approve", headers=_h(buyer_tok),
                      json={"ids": ["x"]}, timeout=15)
    assert r.status_code in (401, 403)
