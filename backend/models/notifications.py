"""Notification model — extracted from server.py."""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


NOTIFICATION_TYPES = (
    "order", "sale", "message", "review", "payout",
    "system", "dispute", "shipping", "wallet", "verification",
)


class Notification(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    type: str = "system"
    title: str
    body: str = ""
    link: Optional[str] = None
    read: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
