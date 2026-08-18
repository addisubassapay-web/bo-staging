"""Per-user Zyte quotas.

We charge every Zyte call as 1 credit against the calling user's monthly
budget. Category (productList) calls count as 1 regardless of how many
products come back — that's what makes them so cost-effective.

Data model:
    settings.zyte_monthly_cap_per_user  # global default, e.g. 500
    users.zyte_monthly_cap              # per-user override (optional)
    zyte_usage: {user_id, month: 'YYYY-MM', used: int, updated_at}
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional


def _current_month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


async def _global_cap(db) -> int:
    s = await db.settings.find_one({"id": "global"}, {"_id": 0, "zyte_monthly_cap_per_user": 1})
    if s and isinstance(s.get("zyte_monthly_cap_per_user"), (int, float)):
        return int(s["zyte_monthly_cap_per_user"])
    return 500  # sensible default for a $100 Zyte tier


async def get_user_cap(db, user: dict) -> int:
    """Return the effective monthly cap for this user (override or global)."""
    if isinstance(user.get("zyte_monthly_cap"), (int, float)) and user["zyte_monthly_cap"] > 0:
        return int(user["zyte_monthly_cap"])
    return await _global_cap(db)


async def get_usage(db, user_id: str, month: Optional[str] = None) -> int:
    m = month or _current_month()
    doc = await db.zyte_usage.find_one({"user_id": user_id, "month": m}, {"_id": 0, "used": 1})
    return int((doc or {}).get("used", 0))


async def get_status(db, user: dict) -> dict:
    used = await get_usage(db, user["id"])
    cap = await get_user_cap(db, user)
    return {
        "month": _current_month(),
        "used": used,
        "cap": cap,
        "remaining": max(0, cap - used),
        "override_active": bool(user.get("zyte_monthly_cap")),
    }


async def assert_can_spend(db, user: dict, cost: int = 1) -> None:
    """Raise HTTPException 429 if the user's budget can't cover `cost`."""
    from fastapi import HTTPException
    used = await get_usage(db, user["id"])
    cap = await get_user_cap(db, user)
    if used + cost > cap:
        raise HTTPException(
            status_code=429,
            detail=(f"Zyte quota exceeded — {used}/{cap} credits used this month. "
                    f"Contact an admin to raise your limit."),
        )


async def record_spend(db, user_id: str, cost: int = 1) -> None:
    """Atomically increment usage. Called from arq worker AFTER a successful
    Zyte call so we never charge for a failed API round-trip."""
    m = _current_month()
    await db.zyte_usage.update_one(
        {"user_id": user_id, "month": m},
        {"$inc": {"used": int(cost)},
         "$set": {"updated_at": datetime.now(timezone.utc)},
         "$setOnInsert": {"user_id": user_id, "month": m}},
        upsert=True,
    )


async def admin_all_usage(db, month: Optional[str] = None) -> list[dict]:
    """List of {user_id, email, used, cap} rows for a given month."""
    m = month or _current_month()
    rows = await db.zyte_usage.find({"month": m}, {"_id": 0}).sort("used", -1).to_list(1000)
    if not rows:
        return []
    ids = [r["user_id"] for r in rows]
    users_cursor = db.users.find({"id": {"$in": ids}}, {"_id": 0, "id": 1, "email": 1, "zyte_monthly_cap": 1})
    users = {u["id"]: u async for u in users_cursor}
    global_cap = await _global_cap(db)
    out = []
    for r in rows:
        u = users.get(r["user_id"]) or {}
        cap = int(u.get("zyte_monthly_cap") or global_cap)
        out.append({
            "user_id": r["user_id"],
            "email": u.get("email"),
            "month": r["month"],
            "used": int(r.get("used", 0)),
            "cap": cap,
            "override_active": bool(u.get("zyte_monthly_cap")),
            "updated_at": r.get("updated_at"),
        })
    return out
