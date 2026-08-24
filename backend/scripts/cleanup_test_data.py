"""One-shot cleanup: purge test users, their cascaded data, test listings,
test products from the permanent catalog, and orphaned R2 image objects.

Runs in DRY-RUN mode by default. Pass --execute to actually delete.
Every doc that will be deleted is snapshot-backed to /app/backend/cleanup_backups/{tag}/
BEFORE deletion so any collection can be restored if we made a mistake.

Usage:
    python scripts/cleanup_test_data.py             # dry-run
    python scripts/cleanup_test_data.py --execute   # destructive
    python scripts/cleanup_test_data.py --execute --skip-r2
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Set

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from motor.motor_asyncio import AsyncIOMotorClient

BACKUP_ROOT = Path(__file__).resolve().parent.parent / "cleanup_backups"

DEMO_SELLERS = ["sophia_style", "urban_finds", "vintage_maven", "tech_haven", "cozy_home"]

PUBLIC_DOMAINS = (
    "@gmail.com", "@yahoo.com", "@hotmail.com", "@outlook.com",
    "@icloud.com", "@aol.com", "@proton.me", "@protonmail.com",
    "@live.com", "@msn.com", "@ymail.com",
)

TEST_TITLE_RE = re.compile(
    r"^(TEST_|Follow Notif Test|FOLLOW NOTIF TEST|TEST_pay|TEST_SOPHIA|Sync Test|Async|Force queue|Async-Fix|Bulk Test|Async Bulk)",
    re.IGNORECASE,
)
TEST_SKU_RE = re.compile(r"^B00(TEST|SYNC|ASY|FORCE|BIG)")

# Test dataset IDs that we want to purge from the ingest history.
TEST_APIFY_DATASETS = {"g5pLGd2OMRI0rm1gD", "nonexistent-dataset-for-test"}

# Collections that carry a user id we need to cascade-delete for test users.
USER_ID_FIELDS: Dict[str, List[str]] = {
    "wallet_txs": ["user_id"],
    "notifications": ["user_id"],
    "cart_items": ["user_id"],
    "favorites": ["user_id"],
    "verification_tokens": ["user_id"],
    "otp_tokens": ["user_id"],
    "email_otps": ["user_id"],
    "password_resets": ["user_id"],
    "seller_applications": ["user_id"],
    "recently_viewed": ["user_id"],
    "files": ["user_id"],
    "deposits": ["user_id"],
    "pending_deposits": ["user_id"],
    "withdrawals": ["user_id"],
    "payment_transactions": ["user_id"],
    "stripe_pending_orders": ["user_id"],
    "support_tickets": ["user_id"],
    "login_throttle": ["user_id"],
    "saved_seeds": ["owner_id"],
    "scraper_jobs": ["owner_id"],
    "scraper_batches": ["owner_id"],
    "scraper_super_batches": ["owner_id"],
    "store_follows": ["user_id"],
    "store_discoveries": ["user_id"],
    "dispute_messages": ["user_id", "author_id"],
    "disputes": ["buyer_id", "seller_id"],
    "messages": ["from_user_id", "to_user_id"],
    "reviews": ["reviewer_id", "reviewee_id"],
    "affiliate_links": ["user_id"],
    "shelves": ["owner_id"],
}


def is_real_user(u: dict) -> bool:
    """Real accounts we KEEP. Everything else is treated as a test artefact."""
    if u.get("role") == "admin":
        return True
    if u.get("username") in DEMO_SELLERS:
        return True
    email = (u.get("email") or "").lower()
    username = (u.get("username") or "").lower()
    if email.endswith("@demo.local"):
        return True
    # Explicit test prefixes → delete
    if email.startswith("e2e_") or username.startswith("e2e_"):
        return False
    if email.startswith("lockout_test_"):
        return False
    if email.endswith("@example.com") or email.endswith("@test.local"):
        return False
    if "test_" in email:
        return False
    # Public / real-looking domain → keep
    if any(email.endswith(d) for d in PUBLIC_DOMAINS):
        return True
    # Anything else (unknown domain) → keep to be safe (never delete a real user).
    return True


def _json_default(o: Any):
    if isinstance(o, datetime):
        return o.isoformat()
    try:
        return str(o)
    except Exception:
        return repr(o)


def _serialize(doc: Dict[str, Any]) -> Dict[str, Any]:
    if "_id" in doc:
        doc = {**doc, "_id": str(doc["_id"])}
    return doc


async def _backup(db, tag: str, coll: str, filt: Dict[str, Any]) -> int:
    docs = await db[coll].find(filt).to_list(length=2_000_000)
    if not docs:
        return 0
    out_dir = BACKUP_ROOT / tag
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{coll}.json").write_text(
        json.dumps([_serialize(d) for d in docs], indent=2, default=_json_default)
    )
    return len(docs)


def _r2_key(url: str) -> str:
    if not isinstance(url, str) or not url.startswith("http"):
        return ""
    pub_base = os.environ.get("R2_PUBLIC_URL") or ""
    if pub_base and url.startswith(pub_base.rstrip("/")):
        return url[len(pub_base.rstrip("/")) + 1:]
    marker = ".r2.dev/"
    idx = url.find(marker)
    if idx >= 0:
        remainder = url[idx + len(marker):]
        bucket = os.environ.get("R2_BUCKET", "")
        if bucket and remainder.startswith(f"{bucket}/"):
            return remainder[len(bucket) + 1:]
        return remainder
    return ""


async def gather_r2_referenced_keys(db) -> Set[str]:
    referenced: Set[str] = set()

    async def scan(coll: str, projection: Dict[str, int], picker):
        async for doc in db[coll].find({}, {"_id": 0, **projection}):
            for u in picker(doc):
                key = _r2_key(u or "")
                if key:
                    referenced.add(key)

    await scan("products", {"images": 1}, lambda d: d.get("images") or [])
    await scan("listings", {"images": 1}, lambda d: d.get("images") or [])
    await scan("users", {"avatar": 1}, lambda d: [d.get("avatar")])
    await scan("stores", {"logo": 1, "banner": 1}, lambda d: [d.get("logo"), d.get("banner")])
    return referenced


async def sweep_r2_orphans(db, execute: bool) -> Dict[str, Any]:
    from services.r2_storage import r2_enabled, _r2_client, _env
    if not r2_enabled():
        return {"skipped": "R2 not configured"}

    referenced = await gather_r2_referenced_keys(db)
    client = _r2_client()
    bucket = _env("R2_BUCKET")

    orphan_keys: List[str] = []
    total = 0
    total_bytes = 0
    orphan_bytes = 0

    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket):
        for obj in page.get("Contents", []):
            total += 1
            total_bytes += obj["Size"]
            if obj["Key"] not in referenced:
                orphan_keys.append(obj["Key"])
                orphan_bytes += obj["Size"]

    deleted = 0
    if execute and orphan_keys:
        for i in range(0, len(orphan_keys), 1000):
            batch = orphan_keys[i : i + 1000]
            client.delete_objects(
                Bucket=bucket,
                Delete={"Objects": [{"Key": k} for k in batch]},
            )
            deleted += len(batch)

    return {
        "referenced_keys": len(referenced),
        "total_objects": total,
        "total_mb": round(total_bytes / 1024 / 1024, 2),
        "orphan_objects": len(orphan_keys),
        "orphan_mb": round(orphan_bytes / 1024 / 1024, 2),
        "deleted": deleted,
    }


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", help="actually delete")
    parser.add_argument("--skip-r2", action="store_true")
    args = parser.parse_args()

    execute = args.execute
    tag = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + ("_execute" if execute else "_dryrun")

    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    print(f"\n{'=' * 60}\nMode: {'EXECUTE' if execute else 'DRY-RUN'}\nBackup tag: {tag}\n{'=' * 60}\n")

    users = await db.users.find({}, {"_id": 0}).to_list(5000)
    real_users = [u for u in users if is_real_user(u)]
    test_users = [u for u in users if not is_real_user(u)]
    test_ids: List[str] = [u["id"] for u in test_users if u.get("id")]

    print(f"[users] keep {len(real_users)} · delete {len(test_users)}")

    # Print sample of what will be deleted so an operator can sanity-check.
    for u in test_users[:5]:
        print(f"    - {u.get('email'):40s}  role={u.get('role')}  username={u.get('username')}")
    if len(test_users) > 5:
        print(f"    ... and {len(test_users) - 5} more")

    # ---- Backup EVERY doc slated for deletion ----------------------------
    print(f"\n[backup] Writing snapshots to {BACKUP_ROOT / tag}/ ...")
    total_backed = 0
    total_backed += await _backup(db, tag, "users", {"id": {"$in": test_ids}})
    total_backed += await _backup(db, tag, "listings", {
        "$or": [
            {"title": {"$regex": TEST_TITLE_RE}},
            {"seller_id": {"$in": test_ids}},
        ]
    })
    total_backed += await _backup(db, tag, "products", {"sku": {"$regex": TEST_SKU_RE}})
    total_backed += await _backup(db, tag, "stores", {"owner_id": {"$in": test_ids}})
    total_backed += await _backup(db, tag, "orders", {
        "$or": [
            {"buyer_id": {"$in": test_ids}},
            {"seller_id": {"$in": test_ids}},
        ]
    })
    for coll, fields in USER_ID_FIELDS.items():
        or_clauses = [{f: {"$in": test_ids}} for f in fields]
        try:
            total_backed += await _backup(db, tag, coll, {"$or": or_clauses})
        except Exception as e:
            print(f"    ! backup of {coll} skipped: {e}")
    total_backed += await _backup(db, tag, "apify_ingest_state", {
        "$or": [
            {"dataset_id": {"$in": list(TEST_APIFY_DATASETS)}},
            {"kind": "items"},  # every regression-test bulk push
        ]
    })
    print(f"[backup] {total_backed} docs saved.\n")

    # ---- Plan / delete ---------------------------------------------------
    plan: Dict[str, int] = {}

    async def _run(coll: str, filt: Dict[str, Any]):
        cnt = await db[coll].count_documents(filt)
        plan[coll] = plan.get(coll, 0) + cnt
        if execute and cnt:
            await db[coll].delete_many(filt)

    # 1) Test products
    await _run("products", {"sku": {"$regex": TEST_SKU_RE}})
    # 2) Test-titled listings (belt-and-braces even if seller kept)
    await _run("listings", {"title": {"$regex": TEST_TITLE_RE}})

    if test_ids:
        # 3) Listings owned by test users
        await _run("listings", {"seller_id": {"$in": test_ids}})
        # 4) Stores owned by test users
        await _run("stores", {"owner_id": {"$in": test_ids}})
        # 5) Orders involving test users
        await _run("orders", {"$or": [
            {"buyer_id": {"$in": test_ids}},
            {"seller_id": {"$in": test_ids}},
        ]})
        # 6) Cascade every user-scoped collection
        for coll, fields in USER_ID_FIELDS.items():
            or_clauses = [{f: {"$in": test_ids}} for f in fields]
            try:
                await _run(coll, {"$or": or_clauses})
            except Exception as e:
                print(f"    ! sweep of {coll} skipped: {e}")
        # 7) Users themselves — last
        await _run("users", {"id": {"$in": test_ids}})

    # 8) apify_ingest_state — purge test/regression rows
    await _run("apify_ingest_state", {
        "$or": [
            {"dataset_id": {"$in": list(TEST_APIFY_DATASETS)}},
            {"kind": "items"},
        ]
    })

    print("[plan] rows matched per collection:")
    for coll in sorted(plan.keys()):
        if plan[coll]:
            print(f"    {coll:26s} {plan[coll]:>6d}")

    # ---- R2 orphan sweep -------------------------------------------------
    if not args.skip_r2:
        print("\n[r2] scanning bucket for orphaned images ...")
        r2_report = await sweep_r2_orphans(db, execute)
        print("[r2] " + json.dumps(r2_report, indent=2))

    # ---- Verify ----------------------------------------------------------
    print("\n[verify] surviving totals:")
    for coll in ("listings", "products", "users", "stores", "orders"):
        total = await db[coll].count_documents({})
        active_hint = ""
        if coll == "listings":
            active = await db[coll].count_documents({"status": "active"})
            active_hint = f"   (active: {active})"
        if coll == "products":
            active = await db[coll].count_documents({"is_active": True})
            active_hint = f"   (active: {active})"
        print(f"    {coll:26s} {total:>6d}{active_hint}")

    print(f"\nDone. Mode: {'EXECUTE (changes committed)' if execute else 'dry-run (no changes made)'}\n")


if __name__ == "__main__":
    asyncio.run(main())
