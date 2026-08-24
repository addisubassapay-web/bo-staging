"""Notifications router — extracted from server.py.

Endpoints for listing / marking-as-read the current user's notification
inbox. The `notify()` helper (that WRITES notifications from other
services) still lives in server.py and is imported via deps.py.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends

from models.notifications import Notification
from .deps import get_db, get_current_user

router = APIRouter()


@router.get("/notifications", response_model=List[Notification])
async def list_notifications(
    user: dict = Depends(get_current_user),
    limit: int = 50,
    since: Optional[str] = None,
    types: Optional[str] = None,
):
    """List a user's notifications, newest first.

    * `since` — ISO datetime filter (`?since=2026-02-18T10:00:00Z`). Powers
      the wallet toast stream: the client polls with the timestamp of the
      last row it has seen so we only return brand-new rows.
    * `types` — CSV of Notification.type values to narrow the stream
      (e.g. `types=wallet,payout` for money-flow toasts only).
    """
    db = get_db()
    q: dict = {"user_id": user["id"]}
    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
            if since_dt.tzinfo is None:
                since_dt = since_dt.replace(tzinfo=timezone.utc)
            q["created_at"] = {"$gt": since_dt}
        except Exception:
            pass  # ignore malformed timestamps rather than 400 the poll
    if types:
        wanted = [t.strip() for t in types.split(",") if t.strip()]
        if wanted:
            q["type"] = {"$in": wanted}
    docs = await db.notifications.find(q, {"_id": 0}).sort("created_at", -1).to_list(limit)
    return [Notification(**d) for d in docs]


@router.post("/notifications/read-all")
async def mark_all_read(user: dict = Depends(get_current_user)):
    db = get_db()
    await db.notifications.update_many(
        {"user_id": user["id"], "read": False}, {"$set": {"read": True}}
    )
    return {"ok": True}


@router.post("/notifications/{nid}/read")
async def mark_read(nid: str, user: dict = Depends(get_current_user)):
    db = get_db()
    await db.notifications.update_one(
        {"id": nid, "user_id": user["id"]}, {"$set": {"read": True}}
    )
    return {"ok": True}
