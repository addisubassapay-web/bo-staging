"""Batch rehost external product images (Amazon, third-party CDNs) into
Cloudflare R2 so the permanent catalog is immune to supplier link-rot.

Follows the same pattern as `product_ai.polish_batch` — small, idempotent
batches driven from an admin endpoint. Each product is marked with
`r2_rehosted_at` once every image URL points at our own R2 bucket, so
subsequent runs skip it (unless `force=True`).
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Any, Dict

from services.r2_storage import rehost_many, r2_enabled, _env  # type: ignore

logger = logging.getLogger(__name__)

# Any URL that already points at our R2 bucket is considered done.
def _r2_host_prefixes() -> tuple[str, ...]:
    prefixes: list[str] = []
    public = _env("R2_PUBLIC_URL")
    if public:
        prefixes.append(public.rstrip("/"))
    acc = _env("R2_ACCOUNT_ID")
    if acc:
        prefixes.append(f"https://pub-{acc}.r2.dev")
    return tuple(prefixes)


def _already_r2(url: str, host_prefixes: tuple[str, ...]) -> bool:
    if not url:
        return True  # skip empties
    return any(url.startswith(p) for p in host_prefixes)


async def rehost_product_batch(
    db,
    *,
    limit: int = 25,
    force: bool = False,
    only_active: bool = True,
) -> Dict[str, Any]:
    """Rehost images for up to `limit` products. Returns per-run stats."""
    if not r2_enabled():
        return {
            "processed": 0,
            "rehosted_images": 0,
            "skipped": 0,
            "errors": 0,
            "r2_enabled": False,
            "message": "R2 not configured — set R2_ACCOUNT_ID / R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY / R2_BUCKET in backend/.env",
        }

    host_prefixes = _r2_host_prefixes()
    query: Dict[str, Any] = {}
    if only_active:
        query["is_active"] = True
    if not force:
        query["r2_rehosted_at"] = {"$exists": False}

    cursor = db.products.find(query, {"_id": 0, "id": 1, "images": 1}).limit(limit)
    products = await cursor.to_list(length=limit)

    processed = rehosted_imgs = skipped = errors = 0
    for p in products:
        images = list(p.get("images") or [])
        if not images:
            # No images to rehost — still mark done so we stop revisiting.
            await db.products.update_one(
                {"id": p["id"]},
                {"$set": {"r2_rehosted_at": datetime.now(timezone.utc)}},
            )
            skipped += 1
            continue

        # Only touch URLs that aren't already on R2 (unless force).
        to_rehost_idx = [
            i for i, u in enumerate(images)
            if force or not _already_r2(u, host_prefixes)
        ]
        if not to_rehost_idx and not force:
            await db.products.update_one(
                {"id": p["id"]},
                {"$set": {"r2_rehosted_at": datetime.now(timezone.utc)}},
            )
            skipped += 1
            continue

        try:
            urls_to_rehost = [images[i] for i in to_rehost_idx]
            new_urls = await rehost_many(urls_to_rehost, prefix="products")
            new_images = list(images)
            for idx, new_url in zip(to_rehost_idx, new_urls):
                new_images[idx] = new_url
                if new_url != images[idx]:
                    rehosted_imgs += 1

            await db.products.update_one(
                {"id": p["id"]},
                {"$set": {
                    "images": new_images,
                    "r2_rehosted_at": datetime.now(timezone.utc),
                }},
            )
            processed += 1
        except Exception as e:
            logger.exception(f"R2 rehost failed for product {p.get('id')}: {e}")
            await db.products.update_one(
                {"id": p["id"]},
                {"$set": {"r2_rehost_failed_at": datetime.now(timezone.utc)}},
            )
            errors += 1

    return {
        "processed": processed,
        "rehosted_images": rehosted_imgs,
        "skipped": skipped,
        "errors": errors,
        "r2_enabled": True,
    }
