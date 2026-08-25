"""
Apify Actor Run operational endpoints — proxy to Apify's REST API.

These wrap the per-run APIs (get run, input, log, dataset items, abort,
resurrect) so admins can monitor and control runs from our dashboard without
handing out the raw Apify token.

Auth: all endpoints require admin (via `require_admin`). The Apify token is
read server-side from `APIFY_TOKEN` (falls back to `APIFY_TOKEN_FALLBACK` on
authorization failure) — never sent to the client.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from routers.deps import require_admin

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/apify", tags=["apify-runs"])

APIFY_BASE = "https://api.apify.com/v2"
TIMEOUT = httpx.Timeout(20.0, connect=10.0)


def _tokens() -> List[str]:
    toks: List[str] = []
    primary = os.environ.get("APIFY_TOKEN")
    fallback = os.environ.get("APIFY_TOKEN_FALLBACK")
    if primary:
        toks.append(primary)
    if fallback and fallback != primary:
        toks.append(fallback)
    if not toks:
        raise HTTPException(503, "APIFY_TOKEN not configured on server")
    return toks


async def _apify_request(
    method: str,
    path: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    expect_json: bool = True,
) -> Any:
    """Call Apify REST with automatic token fallback on 401/403."""
    url = f"{APIFY_BASE}{path}"
    last_exc: Optional[Exception] = None
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        for idx, tok in enumerate(_tokens()):
            merged = dict(params or {})
            merged["token"] = tok
            try:
                resp = await client.request(method, url, params=merged)
                if resp.status_code in (401, 403):
                    logger.warning(f"Apify token #{idx} rejected on {path} ({resp.status_code})")
                    last_exc = HTTPException(resp.status_code, "Apify authorization failed")
                    continue
                if resp.status_code == 404:
                    raise HTTPException(404, f"Apify resource not found: {path}")
                if resp.status_code >= 400:
                    raise HTTPException(
                        resp.status_code,
                        f"Apify error: {resp.text[:300] if resp.text else 'unknown'}",
                    )
                if not expect_json or not resp.content:
                    return resp.text
                return resp.json()
            except HTTPException:
                raise
            except Exception as e:
                logger.exception(f"Apify request failed on {path} with token #{idx}")
                last_exc = e
                continue
    raise last_exc or HTTPException(502, "Apify request failed on all tokens")


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------
@router.get("/runs")
async def list_recent_runs(
    _admin: dict = Depends(require_admin),
    limit: int = Query(20, ge=1, le=100),
    desc: bool = Query(True),
):
    """List the account's recent actor runs (newest first by default)."""
    data = await _apify_request(
        "GET", "/actor-runs", params={"limit": limit, "desc": "true" if desc else "false"}
    )
    return data.get("data", data)


@router.get("/runs/{run_id}")
async def get_run(run_id: str, _admin: dict = Depends(require_admin)):
    """Return the full details of a specific actor run."""
    data = await _apify_request("GET", f"/actor-runs/{run_id}")
    return data.get("data", data)


@router.get("/runs/{run_id}/input")
async def get_run_input(run_id: str, _admin: dict = Depends(require_admin)):
    """Return the INPUT record from the run's default key-value store."""
    run = await _apify_request("GET", f"/actor-runs/{run_id}")
    run_data = run.get("data", run)
    kv_store_id = run_data.get("defaultKeyValueStoreId")
    if not kv_store_id:
        raise HTTPException(404, "Run has no default key-value store")
    return await _apify_request(
        "GET", f"/key-value-stores/{kv_store_id}/records/INPUT"
    )


@router.get("/runs/{run_id}/log")
async def get_run_log(
    run_id: str,
    _admin: dict = Depends(require_admin),
    tail_bytes: int = Query(20000, ge=1000, le=500000),
):
    """Return the raw log text of a run (tail-trimmed to keep the response small)."""
    text = await _apify_request("GET", f"/logs/{run_id}", expect_json=False)
    if isinstance(text, str) and len(text) > tail_bytes:
        text = "…[log truncated]…\n" + text[-tail_bytes:]
    return {"run_id": run_id, "log": text or ""}


@router.get("/datasets/{dataset_id}/items")
async def get_dataset_items(
    dataset_id: str,
    _admin: dict = Depends(require_admin),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    clean: bool = Query(True),
):
    """Return items from an Apify dataset. Useful for previewing a run's output."""
    return await _apify_request(
        "GET",
        f"/datasets/{dataset_id}/items",
        params={
            "limit": limit,
            "offset": offset,
            "clean": "true" if clean else "false",
            "format": "json",
        },
    )


@router.post("/runs/{run_id}/import")
async def import_run_to_catalog(
    run_id: str,
    category: str = Query(..., min_length=1, max_length=60,
                          description="Canonical category to force on every imported item (e.g. 'Computer')"),
    subcategory: Optional[str] = Query(None, min_length=1, max_length=60,
                                       description="Subcategory chip (e.g. 'Laptop') — stored as the second breadcrumb segment"),
    max_items: int = Query(5000, ge=1, le=20000,
                           description="Safety cap on how many dataset items to pull"),
    _admin: dict = Depends(require_admin),
):
    """Permanently import every item from an Apify actor run into the
    `products` catalog under the caller-supplied `category` / `subcategory`.

    Why this exists: Apify's monthly quota only counts NEW runs, not reads
    from an already-finished dataset. This lets us pull a run's output
    long after the actor stopped and label it under whatever taxonomy the
    admin picks — regardless of what Amazon's own breadcrumbs said.

    De-dupe: reuses the standard webhook upsert (`sku` first, then
    `source_url`). Re-running is safe.
    """
    from routers.deps import get_db
    from routers.products import _normalize_product
    from services.webhook_ingest import _upsert_chunk, CHUNK

    # 1) resolve the run's default dataset id.
    run = await _apify_request("GET", f"/actor-runs/{run_id}")
    run_data = run.get("data", run) if isinstance(run, dict) else {}
    dataset_id = run_data.get("defaultDatasetId")
    if not dataset_id:
        raise HTTPException(404, "Run has no default dataset id")

    # 2) paginate the dataset (Apify caps at ~1000 items per request).
    all_items: List[Dict[str, Any]] = []
    page_size = 1000
    offset = 0
    while len(all_items) < max_items:
        take = min(page_size, max_items - len(all_items))
        page = await _apify_request(
            "GET",
            f"/datasets/{dataset_id}/items",
            params={"limit": take, "offset": offset, "clean": "true", "format": "json"},
        )
        if not isinstance(page, list) or not page:
            break
        all_items.extend(page)
        if len(page) < take:
            break
        offset += take

    # 3) normalize + force the caller's category/breadcrumbs onto every doc.
    override_bc = f"{category} > {subcategory}" if subcategory else category
    normalized: List[Dict[str, Any]] = []
    skipped = 0
    for raw in all_items:
        norm = _normalize_product(raw)
        if not norm:
            skipped += 1
            continue
        norm["category"] = category
        norm["breadcrumbs"] = override_bc
        normalized.append(norm)

    # 4) chunked upsert (reuses the webhook ingest path).
    db = get_db()
    created = 0
    updated = 0
    reactivated = 0
    for i in range(0, len(normalized), CHUNK):
        counts = await _upsert_chunk(db, normalized[i:i + CHUNK])
        created += counts["created"]
        updated += counts["updated"]
        reactivated += counts.get("reactivated", 0)

    # 5) mirror into `listings` so the /search page picks it up too.
    mirror_stats = None
    try:
        from services.listing_mirror import mirror_products_to_listings
        mirror_stats = await mirror_products_to_listings(db)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[apify-import] mirror step failed (non-fatal): {e}")

    logger.info(
        f"[apify-import] run={run_id} dataset={dataset_id} received={len(all_items)} "
        f"created={created} updated={updated} skipped={skipped} category={category!r}"
    )
    return {
        "run_id": run_id,
        "dataset_id": dataset_id,
        "category": category,
        "subcategory": subcategory,
        "breadcrumbs": override_bc,
        "received": len(all_items),
        "skipped": skipped,
        "created": created,
        "updated": updated,
        "reactivated": reactivated,
        "mirror": mirror_stats,
    }


@router.post("/runs/{run_id}/abort")
async def abort_run(run_id: str, _admin: dict = Depends(require_admin)):
    """Abort a currently-running actor run."""
    data = await _apify_request("POST", f"/actor-runs/{run_id}/abort")
    logger.info(f"[apify] run {run_id} aborted by admin")
    return data.get("data", data)


@router.post("/runs/{run_id}/resurrect")
async def resurrect_run(run_id: str, _admin: dict = Depends(require_admin)):
    """Resurrect a finished or aborted actor run (Apify re-runs it in place)."""
    data = await _apify_request("POST", f"/actor-runs/{run_id}/resurrect")
    logger.info(f"[apify] run {run_id} resurrected by admin")
    return data.get("data", data)
