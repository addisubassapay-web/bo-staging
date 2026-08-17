"""
Unified transaction ledger service.

Every code path that changes a user's wallet balance MUST go through
`apply_entry()`. This guarantees:
  * Atomic update — uses `$inc` with an optional guard so debits can't
    overdraw the available balance.
  * Wallet transaction record is always written alongside the balance
    mutation. No orphaned balance changes.
  * Consistent tx_type vocabulary across deposits, purchases, refunds,
    sale releases, affiliate/referral bonuses, wholesale debits and
    reseller earnings sync.

Public API:
  - apply_entry(...)           → single atomic credit/debit
  - deposit_approved(...)      → wraps apply_entry with deposit semantics
  - purchase_debit(...)        → atomic debit with require_available=True
  - refund_credit(...)         → refund a paid order back to the buyer
  - release_frozen(...)        → move frozen → available
  - reconcile_reseller(...)    → recompute a reseller's ledger from orders

Callers pass the live `db` handle. The service NEVER imports server.py to
avoid circular imports.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional, Literal, Dict, Any

TxType = Literal[
    "deposit",            # admin-approved crypto/manual deposit
    "purchase",           # buyer paid for an order from wallet
    "refund",             # order refunded back to buyer
    "sale_frozen",        # seller earnings put into escrow
    "sale_released",      # escrow moved into available balance
    "wholesale_debit",    # reseller charged wholesale cost on a dropship sale
    "affiliate",          # affiliate commission
    "referral",           # multi-level referral bonus
    "withdrawal",         # cash-out
    "adjustment",         # generic (used by legacy paths / admin corrections)
]


async def apply_entry(
    db,
    *,
    user_id: str,
    delta: float,
    tx_type: TxType,
    description: str,
    related_id: Optional[str] = None,
    frozen: bool = False,
    require_available: bool = False,
) -> Dict[str, Any]:
    """Apply a signed balance change atomically. Returns the wallet_tx dict.

    - `delta` > 0 → credit; `delta` < 0 → debit.
    - `frozen=True` routes the change into `wallet_frozen_balance` instead
      of `wallet_balance`. Debits from frozen balance are supported.
    - `require_available=True` (debits only) refuses the operation if the
      user's available balance is < |delta|. Raises `InsufficientFunds`.
    """
    delta = round(float(delta), 2)
    if delta == 0:
        return {"skipped": True}

    field = "wallet_frozen_balance" if frozen else "wallet_balance"

    if delta < 0 and require_available:
        result = await db.users.update_one(
            {"id": user_id, field: {"$gte": abs(delta)}},
            {"$inc": {field: delta}},
        )
        if result.modified_count != 1:
            raise InsufficientFunds(f"User {user_id} lacks {abs(delta):.2f} in {field}")
    else:
        result = await db.users.update_one({"id": user_id}, {"$inc": {field: delta}})
        if result.matched_count != 1:
            raise LedgerError(f"User {user_id} not found")

    # Read balance AFTER the atomic $inc for a truthful tx snapshot.
    user_after = await db.users.find_one(
        {"id": user_id}, {"_id": 0, "wallet_balance": 1, "wallet_frozen_balance": 1}
    ) or {}
    balance_after = round(float(user_after.get(field, 0.0)), 2)

    tx = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "type": tx_type,
        "amount": delta,
        "balance_after": balance_after,
        "description": description,
        "related_id": related_id,
        "status": "pending" if frozen and delta > 0 else "completed",
        "created_at": datetime.now(timezone.utc),
    }
    await db.wallet_txs.insert_one(tx)
    return tx


# ---------- higher-level helpers (thin wrappers) ---------- #

async def deposit_approved(db, *, user_id: str, amount: float, deposit_id: str,
                            label: str) -> Dict[str, Any]:
    return await apply_entry(
        db,
        user_id=user_id,
        delta=abs(amount),
        tx_type="deposit",
        description=f"Deposit approved — {label}",
        related_id=deposit_id,
    )


async def purchase_debit(db, *, user_id: str, amount: float, order_id: str,
                          description: str) -> Dict[str, Any]:
    return await apply_entry(
        db,
        user_id=user_id,
        delta=-abs(amount),
        tx_type="purchase",
        description=description,
        related_id=order_id,
        require_available=True,
    )


async def refund_credit(db, *, user_id: str, amount: float, order_id: str,
                         description: str) -> Dict[str, Any]:
    return await apply_entry(
        db,
        user_id=user_id,
        delta=abs(amount),
        tx_type="refund",
        description=description,
        related_id=order_id,
    )


async def release_frozen(db, *, user_id: str, amount: float, order_id: Optional[str],
                          description: str) -> Dict[str, Any]:
    """Move `amount` from frozen → available for a single user."""
    amt = round(float(amount), 2)
    if amt <= 0:
        return {"skipped": True}
    user = await db.users.find_one({"id": user_id}, {"_id": 0, "wallet_frozen_balance": 1})
    if not user:
        raise LedgerError(f"User {user_id} not found")
    take = min(round(float(user.get("wallet_frozen_balance", 0.0)), 2), amt)
    if take <= 0:
        return {"skipped": True}
    # Debit frozen bucket
    await apply_entry(
        db,
        user_id=user_id,
        delta=-take,
        tx_type="sale_released",
        description=f"[frozen→available] {description}",
        related_id=order_id,
        frozen=True,
    )
    # Credit available bucket
    return await apply_entry(
        db,
        user_id=user_id,
        delta=take,
        tx_type="sale_released",
        description=description,
        related_id=order_id,
    )


async def reconcile_reseller(db, *, user_id: str) -> Dict[str, Any]:
    """Sync a reseller's wallet_balance to the sum of their ledger entries.
    Used as a self-heal when an external process (e.g. price update on a
    dropship source listing) needs to re-derive earnings. Returns the delta
    applied and the new balance.
    """
    pipeline = [
        {"$match": {"user_id": user_id}},
        {"$group": {
            "_id": None,
            "available": {"$sum": {"$cond": [
                {"$in": ["$type", ["deposit", "purchase", "refund", "sale_released",
                                    "wholesale_debit", "affiliate", "referral",
                                    "withdrawal", "adjustment"]]},
                "$amount", 0]}},
        }},
    ]
    rows = await db.wallet_txs.aggregate(pipeline).to_list(1)
    expected = round(float(rows[0]["available"]) if rows else 0.0, 2)

    user = await db.users.find_one({"id": user_id}, {"_id": 0, "wallet_balance": 1})
    current = round(float((user or {}).get("wallet_balance", 0.0)), 2)
    delta = round(expected - current, 2)
    if delta == 0:
        return {"user_id": user_id, "delta": 0.0, "balance": current, "reconciled": False}
    await apply_entry(
        db,
        user_id=user_id,
        delta=delta,
        tx_type="adjustment",
        description=f"Reseller earnings sync ({'+' if delta > 0 else ''}{delta:.2f})",
    )
    return {"user_id": user_id, "delta": delta, "balance": expected, "reconciled": True}


class LedgerError(Exception):
    """Generic ledger failure."""


class InsufficientFunds(LedgerError):
    """Raised when require_available=True and the balance is too low."""
