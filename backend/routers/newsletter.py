"""
Newsletter router — email capture endpoint.

Stores subscriber emails in db.newsletter_subscribers with a timestamp.
Idempotent: subscribing the same email twice returns 200 with already=true.
Ready to feed a future Resend digest job.
"""
from __future__ import annotations
import re
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr

from .deps import get_db

router = APIRouter()

EMAIL_RX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class NewsletterSubscribe(BaseModel):
    email: EmailStr
    source: str | None = None  # e.g. "footer", "checkout", "homepage_hero"


@router.post("/newsletter/subscribe")
async def subscribe(payload: NewsletterSubscribe):
    email = payload.email.strip().lower()
    if not EMAIL_RX.match(email):
        raise HTTPException(400, "Invalid email address")
    db = get_db()
    existing = await db.newsletter_subscribers.find_one({"email": email}, {"_id": 0})
    if existing:
        return {"ok": True, "already": True, "email": email}
    doc = {
        "email": email,
        "source": (payload.source or "unknown")[:64],
        "subscribed_at": datetime.now(timezone.utc),
        "unsubscribed": False,
    }
    await db.newsletter_subscribers.insert_one(doc)
    return {"ok": True, "already": False, "email": email}


@router.post("/newsletter/unsubscribe")
async def unsubscribe(payload: NewsletterSubscribe):
    email = payload.email.strip().lower()
    db = get_db()
    result = await db.newsletter_subscribers.update_one(
        {"email": email},
        {"$set": {"unsubscribed": True, "unsubscribed_at": datetime.now(timezone.utc)}},
    )
    if result.matched_count == 0:
        raise HTTPException(404, "Email not subscribed")
    return {"ok": True, "email": email}
