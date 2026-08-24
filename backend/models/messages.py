"""Message / chat models — extracted from server.py."""
from __future__ import annotations
import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field


class Message(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    listing_id: str
    sender_id: str
    sender_name: str
    receiver_id: str
    content: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MessageCreate(BaseModel):
    listing_id: str
    receiver_id: str
    content: str
