"""Disputes / returns models — extracted from server.py."""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


DISPUTE_REASONS = ("not_as_described", "damaged", "not_received", "counterfeit", "other")
DISPUTE_STATUSES = ("open", "reviewing", "refunded", "rejected")


class Dispute(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    order_id: str
    buyer_id: str
    buyer_name: str
    seller_id: str
    listing_id: str
    listing_title: str
    listing_image: Optional[str] = None
    amount: float
    reason: Literal["not_as_described", "damaged", "not_received", "counterfeit", "other"]
    description: str
    photos: List[str] = []  # list of /api/files/<id> URLs
    status: Literal["open", "reviewing", "refunded", "rejected"] = "open"
    admin_notes: str = ""
    resolution: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: Optional[datetime] = None


class DisputeCreate(BaseModel):
    order_id: str
    reason: Literal["not_as_described", "damaged", "not_received", "counterfeit", "other"]
    description: str
    photos: List[str] = []


class DisputeResolveIn(BaseModel):
    action: Literal["refund", "reject", "review"]
    admin_notes: Optional[str] = ""
    resolution: Optional[str] = ""


class DisputeMessage(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    dispute_id: str
    sender_id: str
    sender_name: str
    sender_role: Literal["buyer", "seller", "admin"]
    body: str
    photos: List[str] = []
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DisputeMessageCreate(BaseModel):
    body: str = ""
    photos: List[str] = []
