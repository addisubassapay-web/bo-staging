"""Deliverability plumbing — suppression list, bounce webhook, and public
unsubscribe endpoint.

Suppression list (`db.suppression_list`):
  { email, reason: "hard_bounce" | "unsubscribe" | "complaint" | "manual",
    source: str, added_at: datetime, meta: dict }

Every send in `services.mailer` calls the registered async suppression
check before touching SMTP; a hit skips the send and raises
`SuppressedRecipient` — protects sender reputation and keeps Hostinger's
abuse detector happy.
"""
from __future__ import annotations
import base64
import hmac
import hashlib
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, EmailStr

from .deps import get_db, require_admin

router = APIRouter()


# ---------------------------------------------------------------------------
# Unsubscribe token — deterministic HMAC over email so a signed URL in an
# outbound email keeps working forever without storing a token per user.
# ---------------------------------------------------------------------------
def _secret() -> str:
    # Fall back to JWT_SECRET so operators don't have to configure yet
    # another env var; the audience is the same (self-signed to self).
    return (
        os.environ.get("UNSUBSCRIBE_SECRET")
        or os.environ.get("JWT_SECRET")
        or os.environ.get("SECRET_KEY")
        or "blueocean-fallback-unsub-secret"
    )


def sign_email(email: str) -> str:
    email = (email or "").strip().lower()
    sig = hmac.new(_secret().encode(), email.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(sig).decode().rstrip("=")


def verify_email(email: str, token: str) -> bool:
    return hmac.compare_digest(sign_email(email), token or "")


def unsubscribe_url(email: str) -> str:
    """Absolute URL suitable for a List-Unsubscribe header and for the
    footer link in marketing emails."""
    origin = os.environ.get("FRONTEND_ORIGIN", "").rstrip("/") or ""
    return f"{origin}/api/unsubscribe?email={email}&token={sign_email(email)}"


# ---------------------------------------------------------------------------
# Suppression helpers
# ---------------------------------------------------------------------------
async def is_suppressed(email: str) -> bool:
    if not email:
        return False
    doc = await get_db().suppression_list.find_one(
        {"email": email.strip().lower()}, {"_id": 0, "email": 1}
    )
    return bool(doc)


async def add_suppression(
    email: str,
    reason: str,
    source: str = "webhook",
    meta: Optional[dict] = None,
) -> dict:
    email = (email or "").strip().lower()
    if not email or "@" not in email:
        raise ValueError("invalid email")
    doc = {
        "email": email,
        "reason": reason,
        "source": source,
        "meta": meta or {},
        "added_at": datetime.now(timezone.utc),
    }
    # upsert on email so bounces + manual repeats don't create duplicates
    await get_db().suppression_list.update_one(
        {"email": email},
        {"$set": doc},
        upsert=True,
    )
    return doc


async def remove_suppression(email: str) -> int:
    r = await get_db().suppression_list.delete_one({"email": (email or "").strip().lower()})
    return int(r.deleted_count)


# ---------------------------------------------------------------------------
# Public unsubscribe endpoint (List-Unsubscribe One-Click)
# ---------------------------------------------------------------------------
_UNSUB_HTML = """<!doctype html><html><head><meta charset='utf-8'>
<title>Unsubscribed · BlueOcean</title>
<style>body{{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:#F8FAFC;color:#0F172A;padding:60px 20px;text-align:center}}
.card{{max-width:420px;margin:0 auto;background:#fff;border:1px solid #E5E7EB;border-radius:16px;padding:32px 24px}}
h1{{margin:0 0 8px;font-size:22px}}p{{color:#475569;font-size:14px;line-height:1.6}}
.pill{{display:inline-block;background:#EEF2FF;color:#5459E8;padding:4px 12px;border-radius:999px;font-size:12px;font-weight:700;margin-bottom:16px}}
a{{color:#5459E8;text-decoration:none}}</style></head><body>
<div class='card'>
<div class='pill'>{status}</div>
<h1>{title}</h1>
<p>{body}</p>
<p style='margin-top:24px'><a href='{origin}'>Return to BlueOcean</a></p>
</div></body></html>"""


def _render_page(status: str, title: str, body: str) -> HTMLResponse:
    origin = os.environ.get("FRONTEND_ORIGIN", "/").rstrip("/") or "/"
    return HTMLResponse(_UNSUB_HTML.format(status=status, title=title, body=body, origin=origin))


@router.get("/unsubscribe", response_class=HTMLResponse)
async def unsubscribe_get(email: str = "", token: str = ""):
    if not email or "@" not in email or not verify_email(email, token):
        return _render_page("Link expired", "That unsubscribe link is invalid",
                            "The link may have been copied wrong, or the security token expired. "
                            "Reply to any BlueOcean email and we'll remove you manually.")
    await add_suppression(email, reason="unsubscribe", source="link_click")
    return _render_page("Unsubscribed", "You're off the list",
                        f"<b>{email}</b> won't receive any more BlueOcean marketing or nudge emails. "
                        "Transactional emails (verification codes, password resets, order receipts) "
                        "still come through — those are required to run your account.")


@router.post("/unsubscribe")
async def unsubscribe_post(payload: dict = Body(...)):
    """One-Click POST target for List-Unsubscribe-Post (RFC 8058)."""
    email = (payload.get("email") or "").strip().lower()
    token = (payload.get("token") or "").strip()
    if not email or not verify_email(email, token):
        raise HTTPException(400, "invalid unsubscribe token")
    await add_suppression(email, reason="unsubscribe", source="one_click")
    return {"ok": True, "email": email}


# ---------------------------------------------------------------------------
# Bounce webhook — accepts a generic payload from any bounce processor
# (Resend/SendGrid/Postmark/Mailgun/custom cron parser). Idempotent.
# Protect it with a shared secret so anyone with the URL can't poison
# the suppression list.
# ---------------------------------------------------------------------------
class BounceReport(BaseModel):
    email: EmailStr
    reason: str = "hard_bounce"  # hard_bounce | soft_bounce | complaint
    provider: Optional[str] = None
    diagnostic: Optional[str] = None


def _bounce_secret() -> str:
    return (
        os.environ.get("BOUNCE_WEBHOOK_SECRET")
        or os.environ.get("APIFY_WEBHOOK_SECRET")  # reuse if not explicitly set
        or ""
    )


async def _check_bounce_secret(request: Request):
    provided = (
        request.headers.get("X-Webhook-Secret")
        or (request.headers.get("Authorization") or "").replace("Bearer ", "").strip()
        or request.query_params.get("secret", "")
    )
    if not _bounce_secret() or not hmac.compare_digest(provided, _bounce_secret()):
        raise HTTPException(401, "invalid bounce webhook secret")


@router.post("/webhooks/mail/bounce")
async def ingest_bounce(
    request: Request,
    report: BounceReport = Body(...),
    _auth: None = Depends(_check_bounce_secret),
):
    """Add the recipient to the suppression list. Soft bounces are
    recorded but only escalate to a full suppression after we've seen
    three of them for the same address in the last 14 days."""
    email = report.email.lower()
    if report.reason == "soft_bounce":
        # Count recent soft bounces via email_log; if >=3 in 14 days,
        # promote to hard.
        try:
            from datetime import timedelta
            cutoff = datetime.now(timezone.utc) - timedelta(days=14)
            n = await get_db().email_bounce_log.count_documents(
                {"email": email, "reason": "soft_bounce", "at": {"$gte": cutoff}}
            )
        except Exception:
            n = 0
        await get_db().email_bounce_log.insert_one({
            "email": email, "reason": "soft_bounce",
            "provider": report.provider, "diagnostic": report.diagnostic,
            "at": datetime.now(timezone.utc),
        })
        if n + 1 < 3:
            return {"ok": True, "action": "logged", "soft_bounce_count": n + 1}
        # promote
        await add_suppression(email, reason="hard_bounce",
                              source=f"{report.provider or 'webhook'}:auto-promote",
                              meta={"diagnostic": report.diagnostic})
        return {"ok": True, "action": "promoted_to_suppression"}

    await add_suppression(email, reason=report.reason,
                          source=report.provider or "webhook",
                          meta={"diagnostic": report.diagnostic})
    return {"ok": True, "action": "suppressed"}


# ---------------------------------------------------------------------------
# Admin: read/write suppression list
# ---------------------------------------------------------------------------
@router.get("/admin/suppression-list")
async def admin_list_suppression(limit: int = 500, q: str = "", _admin: dict = Depends(require_admin)):
    """List suppressed addresses. Admin-only enforcement is applied by
    the include_router prefix + a require_admin dependency wired in
    server.py to keep this router import-safe (no circular imports)."""
    query: dict = {}
    if q:
        query["email"] = {"$regex": q.lower(), "$options": "i"}
    rows = await get_db().suppression_list.find(query, {"_id": 0}).sort("added_at", -1).to_list(limit)
    return {"items": rows, "count": len(rows)}


@router.post("/admin/suppression-list/add")
async def admin_add_suppression(payload: dict = Body(...), _admin: dict = Depends(require_admin)):
    doc = await add_suppression(
        payload.get("email", ""),
        reason=payload.get("reason", "manual"),
        source="admin",
        meta=payload.get("meta"),
    )
    return {"ok": True, "email": doc["email"]}


@router.post("/admin/suppression-list/remove")
async def admin_remove_suppression(payload: dict = Body(...), _admin: dict = Depends(require_admin)):
    n = await remove_suppression(payload.get("email", ""))
    return {"ok": True, "removed": n}


@router.get("/admin/mail/delivery-log")
async def admin_mail_delivery_log(
    limit: int = 100,
    kind: str = "",
    status: str = "",
    q: str = "",
    _admin: dict = Depends(require_admin),
):
    """Return the most recent email sends with provider, status, kind,
    and message_id. Filter by kind (auth/receipts/marketing/…), by
    status (sent/failed), or by recipient/subject substring."""
    query: dict = {}
    if kind:
        query["kind"] = kind
    if status:
        query["status"] = status
    if q:
        query["$or"] = [
            {"to": {"$regex": q, "$options": "i"}},
            {"subject": {"$regex": q, "$options": "i"}},
        ]
    rows = await get_db().email_delivery_log.find(query, {"_id": 0}).sort("at", -1).to_list(max(1, min(500, limit)))
    # Aggregate a small stat summary so the admin UI can show totals.
    from datetime import datetime as _dt, timezone as _tz, timedelta as _td
    since_24h = _dt.now(_tz.utc) - _td(hours=24)
    agg = await get_db().email_delivery_log.aggregate([
        {"$match": {"at": {"$gte": since_24h}}},
        {"$group": {"_id": {"provider": "$provider", "status": "$status"}, "n": {"$sum": 1}}},
    ]).to_list(50)
    breakdown = {}
    for row in agg:
        prov = row["_id"].get("provider") or "?"
        stat = row["_id"].get("status") or "?"
        breakdown.setdefault(prov, {})[stat] = row["n"]
    return {"items": rows, "count": len(rows), "last_24h_breakdown": breakdown}


# ---------------------------------------------------------------------------
# IMAP receive endpoints — read-only inbox view + one-shot bounce processor.
# Both admin-only so the mailbox contents never leak to unauthenticated users.
# ---------------------------------------------------------------------------
@router.get("/admin/mail/inbox")
async def admin_mail_inbox(limit: int = 25, unseen_only: bool = False,
                           _admin: dict = Depends(require_admin)):
    from services import imap_receiver
    if not imap_receiver.is_configured():
        raise HTTPException(400, "IMAP not configured — set IMAP_HOST/USER/PASSWORD in backend/.env")
    try:
        rows = await imap_receiver.fetch_inbox(limit=max(1, min(100, limit)), unseen_only=unseen_only)
        return {"items": rows, "count": len(rows)}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(503, f"IMAP fetch failed: {e}")


@router.post("/admin/mail/process-bounces")
async def admin_mail_process_bounces(payload: dict = Body(default={}),
                                     _admin: dict = Depends(require_admin)):
    """Pull the last N messages from IMAP, add hard-bounce addresses to
    the suppression list. Idempotent (upsert). Returns counts."""
    from services import imap_receiver
    if not imap_receiver.is_configured():
        raise HTTPException(400, "IMAP not configured — set IMAP_HOST/USER/PASSWORD in backend/.env")
    limit = int(payload.get("limit") or 50)
    try:
        return await imap_receiver.process_bounces(limit=max(1, min(200, limit)))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(503, f"IMAP bounce scan failed: {e}")
