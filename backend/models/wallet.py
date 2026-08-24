"""Extracted from server.py — shared models for wallet/deposits/withdrawals.

server.py still imports these back so nothing else has to change.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class WalletTransaction(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    type: Literal[
        "sale", "sale_frozen", "sale_released", "affiliate", "referral",
        "dropship", "dropship_frozen", "dropship_released", "withdrawal",
        "adjustment", "bonus", "refund", "deposit", "purchase", "wholesale_debit",
    ]
    amount: float  # positive = credit, negative = debit
    balance_after: float
    description: str = ""
    related_id: Optional[str] = None
    status: Literal["completed", "pending"] = "completed"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    # Bucket the row belongs to — either affects wallet_balance (available)
    # or wallet_frozen_balance (frozen). Populated by ledger.apply_entry so
    # frontends can render the two buckets separately and reconcile is
    # unambiguous.
    bucket: Optional[Literal["available", "frozen"]] = None
    # Populated on Reinvest-advance credit rows so the UI can render an
    # expandable trail of which orders each advance funded.
    funded_orders: List[str] = Field(default_factory=list)


class WithdrawalRequest(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    user_name: str
    amount: float
    method: str = "bank_transfer"  # mocked
    account_info: str = ""
    status: Literal["pending", "approved", "rejected", "paid"] = "pending"
    notes: Optional[str] = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    processed_at: Optional[datetime] = None


class WithdrawalRequestCreate(BaseModel):
    amount: float
    method: str = "bank_transfer"
    account_info: str = ""


class DepositRequest(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    user_name: str
    amount: float
    method: Literal["crypto", "manual"] = "crypto"
    currency: Optional[str] = None
    reference: str = ""  # tx hash for crypto, or bank reference / payment id for manual
    note: str = ""
    screenshot_url: Optional[str] = None
    status: Literal["pending", "approved", "rejected"] = "pending"
    admin_note: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    processed_at: Optional[datetime] = None
    # Populated when the buyer re-submits after a rejection.
    resubmitted_at: Optional[datetime] = None
    resubmit_count: int = 0


class DepositRequestCreate(BaseModel):
    amount: float
    method: Literal["crypto", "manual"] = "crypto"
    currency: Optional[str] = None
    reference: str = ""
    note: Optional[str] = ""
    screenshot_url: Optional[str] = None
