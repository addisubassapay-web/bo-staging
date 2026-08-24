"""Phase 16 tests: per-category import breakdown + incremental persistence."""
import os
import asyncio
import pytest
import requests
from unittest.mock import MagicMock, patch

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@mercari-global.local"
ADMIN_PASSWORD = "admin123"


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


# ---------- GET /api/admin/sync/status ----------
class TestSyncStatus:
    def test_status_shape(self, admin_headers):
        r = requests.get(f"{API}/admin/sync/status", headers=admin_headers)
        assert r.status_code == 200, r.text
        data = r.json()
        # required keys
        for k in ["source", "sync_running", "per_category", "imported_count", "active_listings"]:
            assert k in data, f"missing key {k}"
        # per_category is plain dict[str, int] with non-negative values
        pc = data["per_category"]
        assert isinstance(pc, dict)
        for slug, count in pc.items():
            assert isinstance(slug, str)
            assert isinstance(count, int)
            assert count >= 0

    def test_status_requires_admin(self):
        r = requests.get(f"{API}/admin/sync/status")
        assert r.status_code in (401, 403)


# ---------- POST /api/admin/sync/apify (no regression) ----------
class TestTriggerSync:
    def test_trigger_returns_started_or_running(self, admin_headers):
        # target=100 is minimum allowed; but we don't actually want to burn credits.
        # Backend spawns background task via asyncio.create_task; server responds instantly.
        r = requests.post(
            f"{API}/admin/sync/apify",
            headers=admin_headers,
            json={"target_count": 100, "replace_existing": False},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("ok") is True
        assert data.get("started") is True or data.get("already_running") is True

    def test_trigger_validates_target(self, admin_headers):
        r = requests.post(
            f"{API}/admin/sync/apify",
            headers=admin_headers,
            json={"target_count": 50},
        )
        assert r.status_code == 400


# ---------- Unit test: incremental per_category persist inside loop ----------
class TestIncrementalPersist:
    """Assert the code path in apify_sync.import_from_apify writes per_category
    to sync_state every 200 successfully-built items."""

    def test_incremental_persist_every_200(self):
        # Import here so pytest collection isn't affected if module fails to load
        from backend import apify_sync as mod  # type: ignore
        # apify_sync lives at /app/backend/apify_sync.py — import differently:
        pass

    def test_incremental_persist_direct(self):
        import importlib.util
        import sys
        spec = importlib.util.spec_from_file_location(
            "apify_sync_mod", "/app/backend/apify_sync.py"
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules["apify_sync_mod"] = mod
        spec.loader.exec_module(mod)

        # Build a fake db object with async collection methods
        class FakeCollection:
            def __init__(self):
                self.updates = []  # list of (filter, update)
                self.deleted = 0
                self.inserted_batches = []

            async def find(self, *a, **kw):  # not used directly; overridden below
                raise NotImplementedError

            async def delete_many(self, flt):
                self.deleted += 1
                class R: deleted_count = 0
                return R()

            async def insert_many(self, docs):
                self.inserted_batches.append(len(docs))

            async def update_one(self, flt, upd, upsert=False):
                self.updates.append((flt, upd))
                class R: pass
                return R()

            async def count_documents(self, flt):
                return 0

        class AsyncListCursor:
            def __init__(self, items):
                self._items = items
            async def to_list(self, n):
                return self._items[:n]

        class CatsColl:
            def find(self, *a, **kw):
                cats = [
                    {"id": "c-women", "slug": "women", "name": "Women"},
                    {"id": "c-men", "slug": "men", "name": "Men"},
                    {"id": "c-electronics", "slug": "electronics", "name": "Electronics"},
                    {"id": "c-other", "slug": "other", "name": "Other"},
                ]
                return AsyncListCursor(cats)

        class UsersColl:
            def find(self, *a, **kw):
                users = [{"id": f"u{i}", "username": f"user{i}"} for i in range(5)]
                return AsyncListCursor(users)

        listings = FakeCollection()
        favorites = FakeCollection()
        cart_items = FakeCollection()
        sync_state = FakeCollection()

        db = MagicMock()
        db.categories = CatsColl()
        db.users = UsersColl()
        db.listings = listings
        db.favorites = favorites
        db.cart_items = cart_items
        db.sync_state = sync_state

        # Fake apify client
        fake_run = MagicMock()
        fake_run.status = "SUCCEEDED"
        fake_run.default_dataset_id = "ds-test"
        fake_actor = MagicMock()
        fake_actor.call = MagicMock(return_value=fake_run)

        # Build 400 fake items
        fake_items = []
        for i in range(400):
            fake_items.append({
                "asin": f"B0{i:07d}",
                "title": f"Test Product {i}",
                "price": {"value": 19.99 + i * 0.01},
                "url": f"https://amazon.com/dp/B{i}",
                "thumbnailImage": "https://example.com/img.jpg",
                "breadCrumbs": "Electronics > Gadgets" if i % 2 == 0 else "Women > Fashion",
            })

        fake_dataset = MagicMock()
        fake_dataset.iterate_items = MagicMock(return_value=iter(fake_items))

        fake_client = MagicMock()
        fake_client.actor = MagicMock(return_value=fake_actor)
        fake_client.dataset = MagicMock(return_value=fake_dataset)

        with patch.object(mod, "_get_client", return_value=fake_client):
            result = asyncio.get_event_loop().run_until_complete(
                mod.import_from_apify(db, target_count=400, replace_existing=True)
            )

        assert result["ok"] is True, result
        assert result["imported"] == 400
        # Now verify incremental persist happened: we expect updates at idx 200 and 400
        # (as well as initial start-state update, and final completion update).
        set_updates = [u for (_flt, u) in sync_state.updates if "$set" in u]
        # Find updates that mention "Classifying items"
        classifying = [
            u["$set"] for u in set_updates
            if isinstance(u["$set"].get("message"), str)
            and "Classifying items" in u["$set"]["message"]
        ]
        assert len(classifying) >= 2, (
            f"Expected >=2 incremental 'Classifying items' updates for 400 items, "
            f"got {len(classifying)}. Updates: {[u.get('message') for u in set_updates]}"
        )
        # Each should carry a per_category dict of non-negative ints
        for u in classifying:
            pc = u.get("per_category")
            assert isinstance(pc, dict) and len(pc) > 0
            for k, v in pc.items():
                assert isinstance(k, str) and isinstance(v, int) and v >= 0

        # Final update should have sync_running=False and per_category set
        final = set_updates[-1]["$set"]
        assert final.get("sync_running") is False
        assert isinstance(final.get("per_category"), dict) and len(final["per_category"]) > 0
