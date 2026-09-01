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

ZERO_LISTING_KIND = "zero_listing_v1"
ZERO_LISTING_WINDOW_HOURS = 72


def _cron_token() -> str:
    return os.environ.get("CRON_TASK_TOKEN", "")


def _build_email_html(username: str, dashboard_url: str) -> str:
    # Legacy shim kept for tests that pin the old signature. Prefer the
    # shared services.mailer_templates.onboarding_payout_nudge helper.
    from services import mailer_templates
    _subject, html, _text = mailer_templates.onboarding_payout_nudge(username, dashboard_url)
    return html


def _build_zero_listing_html(username: str, sell_url: str) -> str:
    from services import mailer_templates
    _subject, html, _text = mailer_templates.onboarding_zero_listing_nudge(username, sell_url)
    return html


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
            from services import mailer_templates
            from routers.mailops import unsubscribe_url
            unsub = unsubscribe_url(user["email"])
            subject, html, text = mailer_templates.onboarding_payout_nudge(
                user.get("username", ""), payout_link, unsubscribe_url=unsub,
            )
            await mailer.send_email(
                to=user["email"],
                subject=subject, html=html, text=text,
                tags=["onboarding_nudge", NUDGE_KIND],
                is_transactional=False,
                unsubscribe_url=unsub,
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


# ---------------------------------------------------------------------------
# 72-hour follow-up: sellers who still have zero listings.
# ---------------------------------------------------------------------------
def _build_zero_listing_html_inline(username: str, sell_url: str) -> str:
    # Removed inline template — kept here as a no-op reference. See
    # services.mailer_templates.onboarding_zero_listing_nudge for the real one.
    del username, sell_url
    return ""


async def _run_zero_listing_nudge_job() -> dict:
    """Find sellers whose store is >72h old and who still have zero listings,
    send one nudge each, record in the same onboarding_nudges ledger."""
    db = get_db()
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=ZERO_LISTING_WINDOW_HOURS)
    frontend = (os.environ.get("FRONTEND_ORIGIN") or "").rstrip("/")
    sell_url = f"{frontend}/sell" if frontend else "/sell"

    tried = sent = skipped = 0
    cursor = db.stores.find(
        {"created_at": {"$lt": cutoff}},
        {"_id": 0, "user_id": 1, "id": 1},
    )
    async for store in cursor:
        tried += 1
        user_id = store.get("user_id")
        if not user_id:
            skipped += 1
            continue

        exists = await db.onboarding_nudges.find_one(
            {"user_id": user_id, "kind": ZERO_LISTING_KIND}, {"_id": 1}
        )
        if exists:
            skipped += 1
            continue

        # Zero-listing gate: skip anyone who has any listing (any status).
        has_listing = await db.listings.find_one(
            {"seller_id": user_id}, {"_id": 1}
        )
        if has_listing:
            skipped += 1
            continue

        user = await db.users.find_one(
            {"id": user_id},
            {"_id": 0, "email": 1, "username": 1, "is_active": 1},
        )
        if not user or not user.get("is_active", True) or not user.get("email"):
            skipped += 1
            continue

        try:
            from services import mailer_templates
            from routers.mailops import unsubscribe_url
            unsub = unsubscribe_url(user["email"])
            subject, html, text = mailer_templates.onboarding_zero_listing_nudge(
                user.get("username", ""), sell_url, unsubscribe_url=unsub,
            )
            await mailer.send_email(
                to=user["email"],
                subject=subject, html=html, text=text,
                tags=["onboarding_nudge", ZERO_LISTING_KIND],
                is_transactional=False,
                unsubscribe_url=unsub,
            )
            await db.onboarding_nudges.insert_one({
                "user_id": user_id,
                "kind": ZERO_LISTING_KIND,
                "sent_at": now,
                "email": user["email"],
            })
            sent += 1
        except Exception as e:
            logger.warning(f"zero-listing nudge failed for {user_id}: {e}")
            skipped += 1

    return {"tried": tried, "sent": sent, "skipped": skipped, "kind": ZERO_LISTING_KIND}


@router.post("/admin/tasks/nudge-zero-listings")
async def admin_nudge_zero_listings(user: dict = Depends(require_admin)):
    return await _run_zero_listing_nudge_job()


@router.post("/tasks/nudge-zero-listings")
async def cron_nudge_zero_listings(token: str = Query(...)):
    expected = _cron_token()
    if not expected or token != expected:
        raise HTTPException(401, "Invalid cron token")
    return await _run_zero_listing_nudge_job()
