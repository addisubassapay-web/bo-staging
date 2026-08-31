"""Iteration 74 — Verify new BlueOcean logo assets are served publicly."""
import hashlib
import os
import re
from pathlib import Path

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
PUBLIC_DIR = Path("/app/frontend/public")

ICON_FILES = [
    ("favicon.png", 2500),
    ("icon-192.png", 5000),
    ("icon-512.png", 20000),
    ("icon-1024.png", 40000),
    ("logo-mark.png", 3000),
    ("logo-mark-96.png", 3000),
    ("logo-mark-192.png", 5000),
]


class TestLocalIconFiles:
    """Verify PNG files on disk are the regenerated post-rebrand versions."""

    @pytest.mark.parametrize("fname,_min_size", ICON_FILES)
    def test_local_file_exists_and_recent(self, fname, _min_size):
        p = PUBLIC_DIR / fname
        assert p.exists(), f"{fname} missing"
        # After Aug 30 2026 = 1756512000 (Aug 30 2026 UTC)
        # Files are dated Aug 31 (regenerated) - simply require newer than SVG (Aug 30)
        svg_mtime = (PUBLIC_DIR / "logo-mark.svg").stat().st_mtime
        assert p.stat().st_mtime >= svg_mtime, f"{fname} older than logo-mark.svg source"

    @pytest.mark.parametrize("fname,min_size", ICON_FILES)
    def test_local_file_size_reasonable(self, fname, min_size):
        p = PUBLIC_DIR / fname
        assert p.stat().st_size >= min_size, (
            f"{fname} size {p.stat().st_size} smaller than expected min {min_size}"
        )

    @pytest.mark.parametrize("fname,_min_size", ICON_FILES)
    def test_local_file_is_png(self, fname, _min_size):
        # PNG magic bytes
        data = (PUBLIC_DIR / fname).read_bytes()[:8]
        assert data[:8] == b"\x89PNG\r\n\x1a\n", f"{fname} is not a valid PNG"


class TestPublicServedAssets:
    """Verify assets are reachable via REACT_APP_BACKEND_URL and match local bytes."""

    @pytest.mark.parametrize("fname,_min_size", ICON_FILES)
    def test_asset_http_200_and_content_type(self, fname, _min_size):
        assert BASE_URL, "REACT_APP_BACKEND_URL not set"
        r = requests.get(f"{BASE_URL}/{fname}", timeout=15)
        assert r.status_code == 200, f"{fname} returned {r.status_code}"
        ctype = r.headers.get("Content-Type", "")
        assert "image/png" in ctype.lower(), f"{fname} wrong content-type: {ctype}"

    @pytest.mark.parametrize("fname,_min_size", ICON_FILES)
    def test_served_bytes_match_local(self, fname, _min_size):
        r = requests.get(f"{BASE_URL}/{fname}", timeout=15)
        assert r.status_code == 200
        local_bytes = (PUBLIC_DIR / fname).read_bytes()
        remote_hash = hashlib.sha256(r.content).hexdigest()
        local_hash = hashlib.sha256(local_bytes).hexdigest()
        assert remote_hash == local_hash, (
            f"{fname}: served bytes differ from local. "
            f"local_size={len(local_bytes)} remote_size={len(r.content)}"
        )

    def test_logo_mark_svg_served(self):
        r = requests.get(f"{BASE_URL}/logo-mark.svg", timeout=15)
        assert r.status_code == 200
        assert "svg" in r.headers.get("Content-Type", "").lower()
        assert b"<svg" in r.content
        # Verify BlueOcean indigo present in served SVG
        assert b"5459E8" in r.content or b"5459e8" in r.content


class TestManifest:
    def test_manifest_served(self):
        r = requests.get(f"{BASE_URL}/manifest.json", timeout=15)
        assert r.status_code == 200
        m = r.json()
        icons = m.get("icons", [])
        assert len(icons) == 5, f"expected 5 icon entries, got {len(icons)}"
        srcs = [i["src"] for i in icons]
        assert "logo-mark.svg" in srcs
        assert "logo-mark-96.png" in srcs
        assert "icon-192.png" in srcs
        assert "icon-512.png" in srcs
        assert "icon-1024.png" in srcs

    def test_manifest_maskable_purpose(self):
        r = requests.get(f"{BASE_URL}/manifest.json", timeout=15)
        m = r.json()
        by_src = {i["src"]: i for i in m["icons"]}
        assert "maskable" in by_src["icon-192.png"]["purpose"]
        assert "maskable" in by_src["icon-512.png"]["purpose"]

    def test_manifest_no_old_96x101(self):
        r = requests.get(f"{BASE_URL}/manifest.json", timeout=15)
        assert "96x101" not in r.text


class TestIndexHtml:
    def test_index_served(self):
        r = requests.get(f"{BASE_URL}/index.html", timeout=15)
        assert r.status_code == 200
        self._html = r.text
        return r.text

    def _fetch(self):
        return requests.get(f"{BASE_URL}/index.html", timeout=15).text

    def test_og_image_icon_1024(self):
        html = self._fetch()
        assert re.search(r'og:image"\s+content="[^"]*icon-1024\.png\?v=10"', html), (
            "og:image not pointing to icon-1024.png?v=10"
        )
        assert re.search(r'twitter:image"\s+content="[^"]*icon-1024\.png\?v=10"', html)

    def test_og_image_width_1024(self):
        html = self._fetch()
        assert re.search(r'og:image:width"\s+content="1024"', html)

    def test_apple_touch_icons_present(self):
        html = self._fetch()
        assert 'rel="apple-touch-icon"' in html
        # A 512 apple-touch is expected
        assert re.search(r'apple-touch-icon"\s+sizes="512x512"', html)
        # 192 present (either explicit or default)
        assert "icon-192.png" in html

    def test_mask_icon_present(self):
        html = self._fetch()
        assert re.search(r'rel="mask-icon"[^>]*color="#5459E8"', html)

    def test_cache_buster_v10_on_all_icons(self):
        html = self._fetch()
        # Find all icon link href and og/twitter image references
        pngs = re.findall(r'(?:href|content)="[^"]*(?:favicon|icon-\d+|logo-mark[^"]*)\.(?:png|svg)[^"]*"', html)
        assert pngs, "no icon references found"
        missing = [p for p in pngs if "?v=10" not in p]
        assert not missing, f"missing ?v=10 cache-buster on: {missing}"


class TestServiceWorker:
    def test_sw_served(self):
        r = requests.get(f"{BASE_URL}/service-worker.js", timeout=15)
        assert r.status_code == 200
        assert "v11-new-logo-icons" in r.text, "service-worker VERSION not bumped to v11-new-logo-icons"
