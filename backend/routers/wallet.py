"""Wallet routes — progressive extraction from server.py.

Only the simplest, self-contained wallet endpoints live here for now.
The rest (13 total, including everything that touches `ledger`,
`notify`, `compute_seller_badge`, `get_settings`, and `_TICKER_CACHE`)
still live in server.py because they'd drag half of server.py's
private state along with them.

Pattern:
    server.py calls `wire(db=..., ...)` at startup, then
    `app.include_router(router)`. Extracted routes reach for the
    injected refs via the module-level `_state` singleton.

This module intentionally does NOT declare an `APIRouter(prefix="/api")`
— that prefix is added by the main app's include so it matches
`api_router`'s prefix exactly.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query

router = APIRouter(tags=["wallet"])

# Refs injected by server.py at startup. Kept as a mutable dict so
# nothing in this module resolves anything at import time.
_state: Dict[str, Any] = {}

# 15-second in-process cache for the public ticker. Kept module-local
# so it survives across requests but doesn't leak into server.py.
_TICKER_CACHE: Dict[str, Any] = {"at": 0.0, "rows": []}


def wire(*, db) -> None:
    """server.py calls this once during import to inject the DB handle."""
    _state["db"] = db


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _to_aware(dt: Any) -> Optional[datetime]:
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except Exception:
            return None
    if isinstance(dt, datetime) and dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt if isinstance(dt, datetime) else None


@router.get("/wallet/ticker")
async def wallet_ticker(
    limit: int = Query(default=15, ge=1, le=30),
    minutes: int = Query(default=120, ge=5, le=1440),
):
    """Anonymized recent-release feed for the header ticker.

    Returns up to `limit` rows representing frozen→available releases
    within the last `minutes` minutes. Username is masked, listing
    title truncated, positive amounts only. No auth — intentionally
    public social proof.
    """
    db = _state["db"]

    now_ts = _now_utc().timestamp()
    if now_ts - _TICKER_CACHE.get("at", 0) < 15:
        return _TICKER_CACHE.get("rows", [])[:limit]

    cutoff = _now_utc() - timedelta(minutes=minutes)
    docs = await db.wallet_txs.find(
        {
            "type": {"$in": ["sale_released", "dropship_released"]},
            "bucket": {"$ne": "frozen"},
            "amount": {"$gt": 0},
            "created_at": {"$gte": cutoff},
        },
        {"_id": 0, "user_id": 1, "amount": 1, "created_at": 1,
         "description": 1, "related_id": 1},
    ).sort("created_at", -1).limit(limit).to_list(limit)

    user_ids = list({d["user_id"] for d in docs if d.get("user_id")})
    users_by_id: Dict[str, dict] = {}
    if user_ids:
        async for u in db.users.find(
            {"id": {"$in": user_ids}}, {"_id": 0, "id": 1, "username": 1}
        ):
            users_by_id[u["id"]] = u

    def mask(name: Optional[str]) -> str:
        if not name:
            return "someone"
        base = name.split("@")[0]
        return (base[:4] + "…") if len(base) > 4 else base

    rows: List[dict] = []
    now = _now_utc()
    for d in docs:
        u = users_by_id.get(d.get("user_id"), {})
        created = _to_aware(d.get("created_at"))
        ago_min = int((now - created).total_seconds() / 60) if created else 0
        # Strip "Released: " / "Auto-released " prefixes so the line reads clean.
        desc = (d.get("description") or "").split(":", 1)
        title = desc[-1].strip() if len(desc) > 1 else desc[0]
        title = (title[:40] + "…") if len(title) > 40 else title
        rows.append({
            "seller_masked": mask(u.get("username")),
            "amount": round(float(d.get("amount", 0.0)), 2),
            "ago_min": ago_min,
            "listing_title": title,
        })

    _TICKER_CACHE["at"] = now_ts
    _TICKER_CACHE["rows"] = rows
    return rows
