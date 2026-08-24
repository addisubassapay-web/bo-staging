"""Affiliate link models — extracted from server.py."""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field


class AffiliateLink(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    code: str = Field(default_factory=lambda: uuid.uuid4().hex[:10])
    affiliate_user_id: str
    listing_id: Optional[str] = None
    store_id: Optional[str] = None
    clicks: int = 0
    conversions: int = 0
    earnings: float = 0.0
    status: Literal["active", "disabled"] = "active"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AffiliateLinkCreate(BaseModel):
    listing_id: Optional[str] = None
    store_id: Optional[str] = None
