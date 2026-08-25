"""Verify services.queue is importable even when arq/redis are missing.

Also asserts REDIS_URL is not hardcoded in backend/.env and that the
API pod boots (server import + /api/ health).
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest
import requests

BACKEND_DIR = Path(__file__).resolve().parent.parent
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://marketplace-dropship.preview.emergentagent.com").rstrip("/")


def _run(code: str):
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(BACKEND_DIR),
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_queue_importable_without_arq():
    """Simulate a pod where arq is not installed; module must still import."""
    code = (
        "import sys\n"
        "class _NoArq:\n"
        "    def find_spec(self, name, path=None, target=None):\n"
        "        if name=='arq' or name.startswith('arq.'):\n"
        "            raise ImportError('simulated missing arq')\n"
        "        return None\n"
        "sys.meta_path.insert(0, _NoArq())\n"
        "for k in list(sys.modules):\n"
        "    if k=='arq' or k.startswith('arq.'):\n"
        "        del sys.modules[k]\n"
        "import services.queue as q\n"
        "print('ARQ=', q._ARQ_AVAILABLE)\n"
        "print('WS=', hasattr(q,'WorkerSettings'))\n"
    )
    p = _run(code)
    assert p.returncode == 0, f"stderr: {p.stderr}"
    assert "ARQ= False" in p.stdout
    assert "WS= False" in p.stdout


def test_queue_importable_with_arq_locally():
    """On preview pod arq IS installed."""
    p = _run("import services.queue as q; print('ARQ=', q._ARQ_AVAILABLE); print('WS=', hasattr(q,'WorkerSettings'))")
    assert p.returncode == 0, p.stderr
    assert "ARQ= True" in p.stdout
    assert "WS= True" in p.stdout


def test_enqueue_helpers_raise_runtime_error_without_arq():
    code = (
        "import sys, asyncio\n"
        "class _NoArq:\n"
        "    def find_spec(self, name, path=None, target=None):\n"
        "        if name=='arq' or name.startswith('arq.'):\n"
        "            raise ImportError()\n"
        "        return None\n"
        "sys.meta_path.insert(0, _NoArq())\n"
        "for k in list(sys.modules):\n"
        "    if k=='arq' or k.startswith('arq.'):\n"
        "        del sys.modules[k]\n"
        "import services.queue as q\n"
        "for fn in (q.enqueue_scrape, q.enqueue_category):\n"
        "    try:\n"
        "        asyncio.run(fn('x'))\n"
        "        print('NO_RAISE')\n"
        "    except RuntimeError as e:\n"
        "        assert 'Queue unavailable' in str(e), str(e)\n"
        "        print('OK', fn.__name__)\n"
    )
    p = _run(code)
    assert p.returncode == 0, p.stderr
    assert "OK enqueue_scrape" in p.stdout
    assert "OK enqueue_category" in p.stdout
    assert "NO_RAISE" not in p.stdout


def test_no_redis_url_hardcoded_in_env():
    env = (BACKEND_DIR / ".env").read_text()
    assert "REDIS_URL=" not in env, "REDIS_URL should be removed from .env"


def test_no_unguarded_workersettings_import():
    """No module outside services/queue.py should `from services.queue import WorkerSettings`."""
    import subprocess as sp
    r = sp.run(
        ["grep", "-rn", "from services.queue import", "/app/backend", "--include=*.py"],
        capture_output=True, text=True,
    )
    # Only self-reference (services/queue.py) or comments are OK.
    for line in r.stdout.strip().splitlines():
        if "WorkerSettings" in line or " cron" in line:
            assert "services/queue.py" in line, f"Unguarded import: {line}"


def test_server_module_imports():
    p = _run("import server; print('OK')")
    assert p.returncode == 0, p.stderr
    assert "OK" in p.stdout


# ---- Regression: live API ----
def test_api_health():
    r = requests.get(f"{BASE_URL}/api/", timeout=15)
    assert r.status_code == 200, r.text
    assert isinstance(r.json(), dict)


def test_products_endpoint():
    r = requests.get(f"{BASE_URL}/api/products?page_size=3", timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    total = data.get("total") or data.get("count") or 0
    items = data.get("items") or data.get("products") or data.get("results") or []
    assert total >= 4000, f"expected >=4000 products, got {total}"
    assert len(items) == 3, f"expected 3 items, got {len(items)}"


def test_listings_no_test_title_leak():
    r = requests.get(f"{BASE_URL}/api/listings?sort=newest&limit=20", timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    items = data if isinstance(data, list) else (data.get("items") or data.get("listings") or [])
    assert len(items) == 20, f"expected 20 items, got {len(items)}"
    leaks = [it for it in items if "test" in (it.get("title") or "").lower()]
    assert len(leaks) == 0, f"test-title leaks: {[l.get('title') for l in leaks]}"
