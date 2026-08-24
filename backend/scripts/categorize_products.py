"""Backfill categories for the permanent product catalog.

Two-pass strategy:

  Pass 1 — Apify breadcrumbs
    Re-fetches the source dataset once, joins by SKU/ASIN, and applies
    `product_category.map_breadcrumb_to_category` to every product that
    has an Amazon breadcrumb chain. This is the highest-quality signal.

  Pass 2 — Title keyword classifier
    Any product still uncategorized after pass 1 is scored by keyword
    against the fallback table. Anything below the minimum confidence
    (i.e., zero keyword hits) is left uncategorized instead of being
    mis-bucketed.

Usage (from /app/backend):
    python scripts/categorize_products.py --dataset g5pLGd2OMRI0rm1gD
    python scripts/categorize_products.py --dataset g5pLGd2OMRI0rm1gD --execute
    python scripts/categorize_products.py --skip-apify --execute  # keyword-only

Runs in dry-run by default. Emits per-category before/after counters.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import UpdateOne

from services.product_category import (
    CANONICAL_CATEGORIES,
    classify_by_title,
    map_breadcrumb_to_category,
)


def _fetch_apify_breadcrumbs(dataset_id: str) -> Dict[str, str]:
    """Return {asin: breadcrumbs_string} for the whole dataset."""
    from apify_client import ApifyClient
    tokens = [os.environ.get("APIFY_TOKEN"), os.environ.get("APIFY_TOKEN_FALLBACK")]
    tokens = [t for t in tokens if t]
    if not tokens:
        raise RuntimeError("No APIFY_TOKEN configured")
    last_err: Optional[Exception] = None
    for tok in tokens:
        try:
            client = ApifyClient(tok)
            items = list(client.dataset(dataset_id).iterate_items())
            out: Dict[str, str] = {}
            for it in items:
                asin = it.get("asin") or it.get("productId") or it.get("sku")
                bc = it.get("breadCrumbs")
                if asin and isinstance(bc, str) and bc:
                    out[str(asin)] = bc
            return out
        except Exception as e:  # noqa: BLE001
            last_err = e
            continue
    raise RuntimeError(f"All Apify tokens failed: {last_err}")


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset",
        default="g5pLGd2OMRI0rm1gD",
        help="Apify dataset id to pull breadcrumbs from (skip with --skip-apify)",
    )
    parser.add_argument("--skip-apify", action="store_true", help="skip pass 1")
    parser.add_argument("--execute", action="store_true", help="commit the changes")
    args = parser.parse_args()

    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    print(f"\nMode: {'EXECUTE' if args.execute else 'DRY-RUN'}\n{'=' * 40}")

    # Before snapshot
    before = Counter()
    async for r in db.products.aggregate([{"$group": {"_id": "$category", "n": {"$sum": 1}}}]):
        before[r["_id"] or ""] = int(r["n"])
    print("\n[before]")
    for c in CANONICAL_CATEGORIES + [""]:
        label = c or "(uncategorized)"
        print(f"    {label:20s} {before.get(c, 0):>6d}")

    # ---- Pass 1: Apify breadcrumbs -------------------------------------
    breadcrumb_map: Dict[str, str] = {}
    if not args.skip_apify:
        print(f"\n[pass 1] Fetching Apify dataset {args.dataset}...")
        breadcrumb_map = _fetch_apify_breadcrumbs(args.dataset)
        print(f"[pass 1] {len(breadcrumb_map)} breadcrumb chains loaded")

    products = await db.products.find(
        {}, {"_id": 0, "id": 1, "sku": 1, "title": 1, "category": 1, "breadcrumbs": 1}
    ).to_list(50_000)

    pass1_hits = 0
    pass2_hits = 0
    still_none = 0
    ops = []
    category_changes: Counter = Counter()

    for p in products:
        new_cat: Optional[str] = None
        new_bc: Optional[str] = p.get("breadcrumbs")

        # Try to enrich breadcrumbs from Apify pull
        if p.get("sku") and breadcrumb_map:
            bc = breadcrumb_map.get(p["sku"])
            if bc and bc != new_bc:
                new_bc = bc

        # Pass 1: breadcrumb classifier
        if new_bc:
            new_cat = map_breadcrumb_to_category(new_bc)
            if new_cat:
                pass1_hits += 1

        # Pass 2: title keyword fallback
        if not new_cat:
            new_cat = classify_by_title(p.get("title"))
            if new_cat:
                pass2_hits += 1

        if not new_cat:
            still_none += 1

        # Build $set only if something actually changes
        set_doc: Dict[str, object] = {}
        if new_cat and new_cat != p.get("category"):
            set_doc["category"] = new_cat
        if new_bc and new_bc != p.get("breadcrumbs"):
            set_doc["breadcrumbs"] = new_bc
        if set_doc:
            category_changes[new_cat or ""] += 1
            ops.append(UpdateOne({"id": p["id"]}, {"$set": set_doc}))

    print(f"\n[pass 1] classified via breadcrumbs: {pass1_hits}")
    print(f"[pass 2] classified via title keywords: {pass2_hits}")
    print(f"[  ??  ] still uncategorized: {still_none}")
    print(f"[write] {len(ops)} products will be updated")

    if args.execute and ops:
        # Chunked bulk_write to keep payloads sane on Atlas.
        for i in range(0, len(ops), 500):
            await db.products.bulk_write(ops[i : i + 500], ordered=False)
        print(f"[write] applied {len(ops)} updates")

    # After snapshot
    if args.execute:
        after = Counter()
        async for r in db.products.aggregate([{"$group": {"_id": "$category", "n": {"$sum": 1}}}]):
            after[r["_id"] or ""] = int(r["n"])
        print("\n[after]")
        for c in CANONICAL_CATEGORIES + [""]:
            label = c or "(uncategorized)"
            delta = after.get(c, 0) - before.get(c, 0)
            arrow = f" ({'+' if delta >= 0 else ''}{delta})" if delta else ""
            print(f"    {label:20s} {after.get(c, 0):>6d}{arrow}")

    print(f"\nDone. Mode: {'EXECUTE' if args.execute else 'dry-run (no changes)'}\n")


if __name__ == "__main__":
    asyncio.run(main())
