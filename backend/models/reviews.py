"""Review models — extracted from server.py."""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


class Review(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    order_id: str
    reviewer_id: str
    reviewer_name: str
    seller_id: str
    listing_id: str
    listing_title: str
    rating: int  # 1..5
    comment: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ReviewCreate(BaseModel):
    order_id: str
    rating: int
    comment: Optional[str] = ""
