"""Iteration 75 — Verify PWA install prompt & nav-menu logo fix.

User bug: PWA "Add to Home Screen" prompt showed old logo. Fix swapped
`/logo-mark.png` -> `/logo-mark.svg?v=11` in PWAInstallPrompt.jsx &
GlobalNavMenu.jsx. index.html icon cache-busters bumped to ?v=12.
Service worker bumped to v12-logo-final.
"""
import os
import re
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv

load_dotenv(Path("/app/frontend/.env"))
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL not set"
BUILD_DIR = Path("/app/frontend/build")
PUBLIC_DIR = Path("/app/frontend/public")

RASTER_PNGS = [
    "favicon.png",
    "icon-192.png",
    "icon-512.png",
    "icon-1024.png",
    "logo-mark.png",
    "logo-mark-96.png",
    "logo-mark-192.png",
]


# ---------- Built JS bundle checks (P0 fix verification) ----------
class TestBuiltBundleLogoFix:
    def _bundle(self):
        js_files = list((BUILD_DIR / "static" / "js").glob("main.*.js"))
        assert js_files, "no main.*.js bundle in build/"
        return js_files[0].read_text()

    def test_bundle_contains_svg_with_cache_buster(self):
        assert "logo-mark.svg?v=11" in self._bundle(), \
            "built bundle missing /logo-mark.svg?v=11 (PWA prompt & nav-menu fix)"

    def test_bundle_no_stale_raw_png_reference(self):
        content = self._bundle()
        # Any bare "/logo-mark.png" without ?v= would be stale.
        # Note: manifest-declared logo-mark-96.png is fine (different name)
        matches = re.findall(r'["\'/]logo-mark\.png(?!\?v=)', content)
        assert not matches, f"found stale /logo-mark.png references in bundle: {matches}"


# ---------- Source-file assertions (defense-in-depth) ----------
class TestSourceFileSwaps:
    def test_pwa_install_prompt_uses_svg(self):
        src = Path("/app/frontend/src/components/PWAInstallPrompt.jsx").read_text()
        assert "/logo-mark.svg?v=11" in src
        assert "/logo-mark.png" not in src

    def test_global_nav_menu_uses_svg(self):
        src = Path("/app/frontend/src/components/GlobalNavMenu.jsx").read_text()
        assert "/logo-mark.svg?v=11" in src
        assert "/logo-mark.png" not in src


# ---------- Served SVG shape check ----------
class TestServedSvg:
    def test_svg_200_and_type(self):
        r = requests.get(f"{BASE_URL}/logo-mark.svg", timeout=15)
        assert r.status_code == 200
        assert "image/svg+xml" in r.headers.get("Content-Type", "").lower()

    def test_svg_contains_new_shopping_bag_shape(self):
        r = requests.get(f"{BASE_URL}/logo-mark.svg", timeout=15)
        body = r.text
        assert "M36 50" in body, "SVG missing shopping-bag path 'M36 50'"
        assert re.search(r'circle\s+cx="92"\s+cy="28"', body), \
            "SVG missing accent-dot circle cx=92 cy=28"


# ---------- index.html cache-buster ?v=12 everywhere ----------
class TestIndexHtmlCacheBusters:
    def _html(self):
        return requests.get(f"{BASE_URL}/index.html", timeout=15).text

    def test_index_200(self):
        r = requests.get(f"{BASE_URL}/index.html", timeout=15)
        assert r.status_code == 200

    def test_all_icons_have_v12(self):
        html = self._html()
        refs = re.findall(
            r'(?:href|content)="[^"]*(?:favicon|icon-\d+|logo-mark[^"]*|og-banner|twitter-image|apple-touch-icon)[^"]*\.(?:png|svg)[^"]*"',
            html,
        )
        assert refs, "no icon references found in index.html"
        missing = [r for r in refs if "?v=12" not in r]
        assert not missing, f"refs missing ?v=12: {missing}"

    def test_no_stale_v10_or_v11(self):
        html = self._html()
        # index.html itself should not have ?v=10 or ?v=11 for icons
        stale10 = re.findall(r'[^"]*\?v=10[^"]*', html)
        stale11 = re.findall(r'[^"]*\?v=11[^"]*', html)
        assert not stale10, f"stale ?v=10 refs in index.html: {stale10}"
        assert not stale11, f"stale ?v=11 refs in index.html: {stale11}"


# ---------- manifest.json ----------
class TestManifest:
    def test_manifest_icons(self):
        r = requests.get(f"{BASE_URL}/manifest.json", timeout=15)
        assert r.status_code == 200
        icons = r.json().get("icons", [])
        srcs = [i["src"] for i in icons]
        for expected in [
            "logo-mark.svg",
            "logo-mark-96.png",
            "icon-192.png",
            "icon-512.png",
            "icon-1024.png",
        ]:
            assert expected in srcs, f"manifest missing {expected}"

    @pytest.mark.parametrize(
        "fname,ctype",
        [
            ("logo-mark.svg", "image/svg+xml"),
            ("logo-mark-96.png", "image/png"),
            ("icon-192.png", "image/png"),
            ("icon-512.png", "image/png"),
            ("icon-1024.png", "image/png"),
        ],
    )
    def test_manifest_icon_files_served(self, fname, ctype):
        r = requests.get(f"{BASE_URL}/{fname}", timeout=15)
        assert r.status_code == 200
        assert ctype in r.headers.get("Content-Type", "").lower()


# ---------- Service worker ----------
class TestServiceWorker:
    def test_sw_version_v12(self):
        r = requests.get(f"{BASE_URL}/service-worker.js", timeout=15)
        assert r.status_code == 200
        assert "v12-logo-final" in r.text, \
            "service-worker VERSION not bumped to v12-logo-final"


# ---------- PNG mtimes post-rebrand ----------
class TestPngMtimes:
    # Aug 30 2026 UTC = 1756512000
    CUTOFF = 1756512000

    @pytest.mark.parametrize("fname", RASTER_PNGS)
    def test_png_mtime_after_cutoff(self, fname):
        p = PUBLIC_DIR / fname
        assert p.exists(), f"{fname} missing on disk"
        assert p.stat().st_mtime > self.CUTOFF, \
            f"{fname} mtime {p.stat().st_mtime} is pre-rebrand"
