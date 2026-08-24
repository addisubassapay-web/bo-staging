"""Regression: vocab refresh + extracted /wallet/ticker route.

Guards:
  - Admin can trigger `/admin/search/vocab-refresh` and the response
    reports a plausible vocab size (>= our canonical seed of 10).
  - The extracted `/wallet/ticker` in `routers/wallet.py` continues to
    serve without auth and returns a well-formed row shape.
"""
from __future__ import annotations

import os
from pathlib import Path

import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    for line in Path("/app/frontend/.env").read_text().splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            BASE_URL = line.split("=", 1)[1].strip().strip('"').rstrip("/")
            break
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@mercari.local"
ADMIN_PASSWORD = "admin123"


def _admin_token() -> str:
    r = requests.post(
        f"{API}/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    return r.json()["token"]


def test_vocab_refresh_requires_admin():
    r = requests.post(f"{API}/admin/search/vocab-refresh", timeout=15)
    assert r.status_code in (401, 403), r.text


def test_vocab_refresh_returns_size():
    r = requests.post(
        f"{API}/admin/search/vocab-refresh",
        headers={"Authorization": f"Bearer {_admin_token()}"},
        timeout=30,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["ok"] is True
    # 10 canonical categories are always seeded — anything below that
    # means the harvester regressed
    assert data["vocab_size"] >= 10


def test_wallet_ticker_extracted_route_still_public():
    """The /wallet/ticker route was lifted out of server.py into
    routers/wallet.py — the include_router wiring must keep the public
    endpoint reachable and returning the documented shape."""
    r = requests.get(f"{API}/wallet/ticker?limit=5&minutes=1440", timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert isinstance(data, list)
    for row in data:
        # Every row must have the ticker's documented keys
        assert set(row.keys()) >= {"seller_masked", "amount", "ago_min", "listing_title"}
        assert row["seller_masked"].endswith("…") or row["seller_masked"] in ("someone",) or len(row["seller_masked"]) <= 5
        assert isinstance(row["amount"], (int, float))
        assert row["amount"] >= 0
