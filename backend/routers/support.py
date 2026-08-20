"""
Customer support tickets router.

Powers the floating support widget on every page:
- `channel='chat'`  → users hold an in-app back-and-forth with the admin team.
- `channel='email'` → single message is emailed to SUPPORT_EMAIL via Hostinger SMTP.

Every ticket carries an ordered `messages` array so the widget can render a
threaded transcript for chat tickets. Email tickets also record the outgoing
message for the admin dashboard's audit trail.

Auth model:
- Logged-in users automatically attach their user_id + email + username.
- Guests may open an email ticket by supplying their own email in the body.
- Admins list/reply/close via the /api/admin/support/* subroutes.
"""
from __future__ import annotations

import os
import uuid
import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .deps import get_db, get_current_user, get_current_user_optional, require_admin

logger = logging.getLogger(__name__)
router = APIRouter()


def _now() -> datetime:
    return datetime.now(timezone.utc)


class SupportMessage(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    sender: str  # 'user' | 'admin' | 'system'
    sender_name: Optional[str] = None
    text: str
    created_at: datetime = Field(default_factory=_now)


class SupportTicket(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: Optional[str] = None       # None for guest email tickets
    user_email: str
    user_name: str
    channel: str  # 'chat' | 'email'
    subject: str
    status: str = "open"                 # open | pending | closed
    unread_by_user: bool = False          # admin replied but user hasn't opened
    unread_by_admin: bool = True          # user posted, admin hasn't read
    messages: List[SupportMessage] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class _CreatePayload(BaseModel):
    channel: str
    subject: Optional[str] = None
    message: str
    guest_email: Optional[str] = None    # only used for guest email tickets
    guest_name: Optional[str] = None


def _support_recipient() -> str:
    return (
        os.environ.get("SUPPORT_EMAIL")
        or os.environ.get("SMTP_USER")
        or "support@example.com"
    )


async def _email_ticket(ticket: dict, message_text: str):
    """Forward the initial email-channel message to the support inbox."""
    from services import mailer
    to = _support_recipient()
    subject = f"[Support · {ticket['channel']}] {ticket.get('subject') or 'New support message'}"
    html = f"""
    <div style="font-family:system-ui,Segoe UI,Arial,sans-serif;max-width:640px;margin:0 auto;color:#111">
      <h2 style="color:#FF211F">New support request</h2>
      <p style="color:#555">
        <b>From:</b> {ticket['user_name']} &lt;{ticket['user_email']}&gt;<br/>
        <b>Channel:</b> {ticket['channel']}<br/>
        <b>Ticket ID:</b> <code>{ticket['id']}</code>
      </p>
      <div style="background:#f7f7f7;border-left:3px solid #FF211F;padding:12px 16px;margin:16px 0;white-space:pre-wrap">{message_text}</div>
      <p style="font-size:12px;color:#888">Reply directly on the admin dashboard → Support tickets, or by emailing the user.</p>
    </div>
    """
    try:
        return await mailer.send_email(to=to, subject=subject, html=html, tags=["support_ticket"])
    except Exception as e:
        logger.error(f"support email failed: {e}")
        return {"ok": False, "error": str(e)}


@router.post("/support/tickets")
async def create_ticket(
    payload: _CreatePayload = Body(...),
    user: Optional[dict] = Depends(get_current_user_optional),
):
    """Open a new support ticket (chat or email channel)."""
    db = get_db()
    channel = (payload.channel or "").lower().strip()
    if channel not in ("chat", "email"):
        raise HTTPException(400, "channel must be 'chat' or 'email'")
    msg = (payload.message or "").strip()
    if not msg:
        raise HTTPException(400, "message is required")
    if len(msg) > 4000:
        raise HTTPException(400, "message too long (max 4000 chars)")

    if user:
        user_id = user["id"]
        user_email = user["email"]
        user_name = user.get("username") or user["email"].split("@")[0]
    else:
        # Guest ticket — always via email channel; chat requires auth.
        email = (payload.guest_email or "").strip().lower()
        if channel == "chat":
            raise HTTPException(401, "Log in to start a chat with support")
        if "@" not in email or len(email) > 200:
            raise HTTPException(400, "Valid guest_email required")
        user_id = None
        user_email = email
        user_name = (payload.guest_name or email.split("@")[0])[:60]

    subject = (payload.subject or msg[:60] or "Support request").strip()[:120]

    first_msg = SupportMessage(sender="user", sender_name=user_name, text=msg)
    ticket = SupportTicket(
        user_id=user_id,
        user_email=user_email,
        user_name=user_name,
        channel=channel,
        subject=subject,
        messages=[first_msg],
    )
    doc = ticket.model_dump()
    await db.support_tickets.insert_one(doc)

    email_result = None
    if channel == "email":
        email_result = await _email_ticket(doc, msg)

    return {
        "ok": True,
        "ticket_id": ticket.id,
        "channel": channel,
        "status": ticket.status,
        "email_sent": bool(email_result and email_result.get("ok")) if email_result else None,
    }


@router.get("/support/tickets/my")
async def my_tickets(user: dict = Depends(get_current_user)):
    """List the current user's support tickets (newest first)."""
    db = get_db()
    docs = await db.support_tickets.find(
        {"user_id": user["id"]}, {"_id": 0},
    ).sort("updated_at", -1).to_list(50)
    return {"items": docs, "count": len(docs)}


@router.get("/support/tickets/{ticket_id}")
async def get_ticket(ticket_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    doc = await db.support_tickets.find_one({"id": ticket_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Ticket not found")
    if doc.get("user_id") != user["id"] and user.get("role") != "admin":
        raise HTTPException(403, "Not allowed")
    # Mark as read by the recipient side
    if user.get("role") == "admin":
        await db.support_tickets.update_one({"id": ticket_id}, {"$set": {"unread_by_admin": False}})
    else:
        await db.support_tickets.update_one({"id": ticket_id}, {"$set": {"unread_by_user": False}})
    return doc


@router.post("/support/tickets/{ticket_id}/messages")
async def post_message(
    ticket_id: str,
    payload: dict = Body(...),
    user: dict = Depends(get_current_user),
):
    """Append a message to a ticket. Users → admins ; admins → users."""
    db = get_db()
    text = (payload.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "text is required")
    if len(text) > 4000:
        raise HTTPException(400, "text too long (max 4000 chars)")

    doc = await db.support_tickets.find_one({"id": ticket_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Ticket not found")

    is_admin = user.get("role") == "admin"
    if doc.get("user_id") != user["id"] and not is_admin:
        raise HTTPException(403, "Not allowed")
    if doc.get("status") == "closed":
        raise HTTPException(400, "Ticket is closed. Open a new ticket to reply.")

    sender = "admin" if is_admin else "user"
    msg = SupportMessage(sender=sender, sender_name=user.get("username"), text=text).model_dump()
    updates = {
        "$push": {"messages": msg},
        "$set": {
            "updated_at": _now(),
            "status": "open",
            "unread_by_user": is_admin,
            "unread_by_admin": not is_admin,
        },
    }
    await db.support_tickets.update_one({"id": ticket_id}, updates)

    # Notify the counter-party in-app + optional email
    if is_admin and doc.get("user_id"):
        from server import notify  # local import to avoid circular at load
        await notify(
            doc["user_id"], "system", "Support replied to your ticket",
            text[:180], f"/support?ticket={ticket_id}",
        )
    return {"ok": True, "message": msg}


@router.post("/support/tickets/{ticket_id}/close")
async def close_ticket(ticket_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    doc = await db.support_tickets.find_one({"id": ticket_id}, {"_id": 0, "user_id": 1})
    if not doc:
        raise HTTPException(404, "Ticket not found")
    if doc.get("user_id") != user["id"] and user.get("role") != "admin":
        raise HTTPException(403, "Not allowed")
    await db.support_tickets.update_one(
        {"id": ticket_id},
        {"$set": {"status": "closed", "updated_at": _now()}},
    )
    return {"ok": True}


# ---------- ADMIN ROUTES ---------- #
@router.get("/admin/support/tickets")
async def admin_list_tickets(
    status_filter: Optional[str] = Query(None, alias="status"),
    channel: Optional[str] = None,
    _admin: dict = Depends(require_admin),
):
    db = get_db()
    q: dict = {}
    if status_filter and status_filter in ("open", "pending", "closed"):
        q["status"] = status_filter
    if channel and channel in ("chat", "email"):
        q["channel"] = channel
    docs = await db.support_tickets.find(q, {"_id": 0}).sort("updated_at", -1).to_list(500)
    unread = sum(1 for d in docs if d.get("unread_by_admin"))
    return {"items": docs, "count": len(docs), "unread_by_admin": unread}


@router.get("/admin/support/unread-count")
async def admin_unread_count(_admin: dict = Depends(require_admin)):
    db = get_db()
    n = await db.support_tickets.count_documents({"unread_by_admin": True, "status": {"$ne": "closed"}})
    return {"unread": n}


@router.get("/support/unread-count")
async def user_unread_count(user: dict = Depends(get_current_user)):
    db = get_db()
    n = await db.support_tickets.count_documents({
        "user_id": user["id"], "unread_by_user": True, "status": {"$ne": "closed"},
    })
    return {"unread": n}
