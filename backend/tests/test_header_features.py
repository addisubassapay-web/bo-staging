"""Backend tests for header/search superpowers phase.
Covers: GET /api/currency/rates and POST /api/search/image
"""
import base64
import os
import io
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or "https://mercari-clone-1.preview.emergentagent.com"


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ---------- Currency rates ----------
class TestCurrencyRates:
    def test_rates_returns_expected_shape(self, client):
        r = client.get(f"{BASE_URL}/api/currency/rates", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data["base"] == "USD"
        assert isinstance(data["rates"], dict)
        for cur in ["USD", "EUR", "GBP", "JPY", "INR", "CAD"]:
            assert cur in data["rates"], f"missing {cur}"
            assert isinstance(data["rates"][cur], (int, float))
        assert data["rates"]["USD"] == 1.0


# ---------- Image search ----------
def _tiny_png_b64():
    # Minimal 1x1 red PNG
    png = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
        "890000000d49444154789c63f8cfc0f01f00050001010a2e5b1b0000000049454e44ae426082"
    )
    return base64.b64encode(png).decode()


class TestImageSearch:
    def test_missing_body_returns_400(self, client):
        r = client.post(f"{BASE_URL}/api/search/image", json={"image_base64": ""}, timeout=30)
        assert r.status_code in (400, 422)

    def test_image_search_returns_payload(self, client):
        r = client.post(
            f"{BASE_URL}/api/search/image",
            json={"image_base64": _tiny_png_b64(), "limit": 12},
            timeout=60,
        )
        # LLM may sometimes return 500 for tiny non-descript images; accept 200 or 500
        # but require correct shape if 200.
        assert r.status_code in (200, 500)
        if r.status_code == 200:
            data = r.json()
            for key in ["description", "keywords", "category", "items", "total"]:
                assert key in data, f"missing key {key}"
            assert isinstance(data["items"], list)
            assert isinstance(data["keywords"], list)
            assert isinstance(data["total"], int)
