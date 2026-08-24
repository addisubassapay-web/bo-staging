"""Search analytics — log every /api/products/suggest query so we can grow
the fuzzy-correction vocabulary and stock what shoppers can't find.

Stored in `search_events`. Two indexes make the admin dashboards snappy:
  - `created_at` desc (recency)
  - `query`, `result_count` (aggregations for "top zero-result" panel)

Nothing here blocks the response — the log write is fire-and-forget via
`asyncio.create_task`.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("search_analytics")


async def log_search(
    db,
    query: str,
    result_count: int,
    corrected: Optional[str] = None,
    took_ms: int = 0,
) -> None:
    """Never raises — logged and swallowed."""
    try:
        await db.search_events.insert_one({
            "query": (query or "").strip().lower()[:120],
            "raw_query": query,
            "corrected": corrected,
            "result_count": int(result_count),
            "took_ms": int(took_ms),
            "zero_result": result_count == 0 and not corrected,
            "created_at": datetime.now(timezone.utc),
        })
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[search-analytics] log failed: {e}")


def fire_and_forget(db, query: str, result_count: int, corrected: Optional[str], took_ms: int) -> None:
    """Schedule the log write without awaiting it — callers stay snappy."""
    try:
        asyncio.create_task(log_search(db, query, result_count, corrected, took_ms))
    except RuntimeError:
        # No running loop (unlikely in FastAPI request context) — swallow.
        pass
