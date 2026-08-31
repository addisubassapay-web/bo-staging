"""Onboarding nudge job — emails sellers stuck at step 2 (no payout method)
after 24 hours since their store was created. Idempotent: each user is only
nudged once, tracked in `onboarding_nudges` collection.

Runnable in two ways:
  1) POST /api/admin/tasks/nudge-onboarding-payouts  (admin JWT)
  2) POST /api/tasks/nudge-onboarding-payouts?token=<CRON_TOKEN>  (cron)

Returns {sent, skipped, tried} so the operator can verify progress.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from services import mailer
from .deps import get_db, require_admin

logger = logging.getLogger(__name__)
router = APIRouter()

NUDGE_KIND = "onboarding_payout_v1"
NUDGE_WINDOW_HOURS = 24


def _cron_token() -> str:
    return os.environ.get("CRON_TASK_TOKEN", "")


def _build_email_html(username: str, dashboard_url: str) -> str:
    return f"""
    <div style="font-family:system-ui,Segoe UI,Arial,sans-serif;max-width:520px;margin:0 auto;color:#111">
      <h2 style="color:#5459E8;margin:0 0 12px">One tap to start earning</h2>
      <p>Hi {username or 'there'},</p>
      <p>Your BlueOcean store is live — but we can't send you any earnings until you connect a payout method. It takes 60 seconds.</p>
      <p style="text-align:center;margin:24px 0">
        <a href="{dashboard_url}" style="display:inline-block;background:#5459E8;color:#fff;text-decoration:none;padding:14px 28px;border-radius:999px;font-weight:700">
          Connect payout method
        </a>
      </p>
      <p style="color:#666;font-size:13px">Once your payout is on file, buyers can complete purchases and your first payout is auto-scheduled.</p>
      <p style="color:#666;font-size:12px;margin-top:20px">— BlueOcean Trust &amp; Safety</p>
    </div>
    """


async def _run_nudge_job() -> dict:
    """Find sellers with a store older than 24h and no payout, send one nudge
    email each, and record it so we never nudge the same user twice."""
    db = get_db()
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=NUDGE_WINDOW_HOURS)
    frontend = (os.environ.get("FRONTEND_ORIGIN") or "").rstrip("/")
    payout_link = f"{frontend}/wallet?tab=payout" if frontend else "/wallet?tab=payout"

    tried = sent = skipped = 0
    cursor = db.stores.find(
        {"created_at": {"$lt": cutoff}},
        {"_id": 0, "user_id": 1, "created_at": 1},
    )
    async for store in cursor:
        tried += 1
        user_id = store.get("user_id")
        if not user_id:
            skipped += 1
            continue

        # Idempotency: skip if we've already sent this nudge to this user.
        exists = await db.onboarding_nudges.find_one(
            {"user_id": user_id, "kind": NUDGE_KIND}, {"_id": 1}
        )
        if exists:
            skipped += 1
            continue

        user = await db.users.find_one(
            {"id": user_id},
            {"_id": 0, "email": 1, "username": 1, "payout_method": 1, "crypto_addresses": 1, "is_active": 1},
        )
        if not user or not user.get("is_active", True) or not user.get("email"):
            skipped += 1
            continue

        # Already connected a payout → nothing to nudge.
        if user.get("payout_method") or user.get("crypto_addresses"):
            skipped += 1
            continue

        try:
            await mailer.send_email(
                to=user["email"],
                subject="Finish setting up your BlueOcean store (60 sec)",
                html=_build_email_html(user.get("username", ""), payout_link),
                tags=["onboarding_nudge", NUDGE_KIND],
            )
            await db.onboarding_nudges.insert_one({
                "user_id": user_id,
                "kind": NUDGE_KIND,
                "sent_at": now,
                "email": user["email"],
            })
            sent += 1
        except Exception as e:
            logger.warning(f"onboarding nudge failed for {user_id}: {e}")
            skipped += 1

    return {"tried": tried, "sent": sent, "skipped": skipped, "kind": NUDGE_KIND}


@router.post("/admin/tasks/nudge-onboarding-payouts")
async def admin_nudge_onboarding(user: dict = Depends(require_admin)):
    """Admin JWT-gated entry point. Returns the same shape as the cron route."""
    return await _run_nudge_job()


@router.post("/tasks/nudge-onboarding-payouts")
async def cron_nudge_onboarding(token: str = Query(...)):
    """Cron entry point. Requires CRON_TASK_TOKEN env match to run.
    Add it to backend/.env then hit this endpoint from any scheduler."""
    expected = _cron_token()
    if not expected or token != expected:
        raise HTTPException(401, "Invalid cron token")
    return await _run_nudge_job()
