"""Legacy email-template module.

All templates now live in `services.mailer_templates` — this module is a
thin backward-compat shim so the ~13 existing call sites (including inline
`_shell(...)` builders in server.py) keep working without a full sweep.

Historic callers that unpacked `(subject, html)` still work: we simply drop
the plain-text third element from the mailer_templates tuple.
"""
from __future__ import annotations

from services.mailer_templates import (
    BRAND_NAME,
    FRONTEND,
    _shell,
    verify_email as _vt,
    otp_email as _ot,
    password_reset as _pr,
    onboarding_payout_nudge as _op,
    onboarding_zero_listing_nudge as _oz,
    welcome as _we,
    order_confirmation as _oc,
    deposit_approved as _dp,
    account_locked as _al,
    catalog_seed_complete as _cs,
)

# Legacy accent constant — updated to the new indigo brand primary so any
# rare caller that reads it (e.g. dashboards / metadata) gets the right hue.
BRAND_ACCENT = "#5459E8"


def _drop_text(t):
    """Callers that unpack `subject, html = tpl(...)` cannot handle the new
    three-tuple. Trim the text plain-text element for them."""
    subject, html, _text = t
    return subject, html


# ---------------------------------------------------------------------------
# Legacy 2-tuple API — every function forwards to mailer_templates.
# New callers should import from services.mailer_templates instead so they
# get the plain-text version alongside HTML.
# ---------------------------------------------------------------------------
def password_reset(reset_url: str, username: str | None = None):
    return _drop_text(_pr(username or "", reset_url))


def welcome(username: str):
    return _drop_text(_we(username))


def order_confirmation(buyer_name: str, order_id: str, listing_title: str, amount_str: str):
    return _drop_text(_oc(buyer_name, order_id, listing_title, amount_str))


def deposit_approved(username: str, amount_str: str):
    return _drop_text(_dp(username, amount_str))


def account_locked(username: str, unlock_url: str):
    return _drop_text(_al(username, unlock_url))


def catalog_seed_complete(username: str, provider: str, query: str, pages: int,
                          products_total: int, products_published: int,
                          duration_seconds: int, credits_spent: int):
    return _drop_text(_cs(username, provider, query, pages, products_total,
                          products_published, duration_seconds, credits_spent))


__all__ = [
    "BRAND_NAME", "BRAND_ACCENT", "FRONTEND", "_shell",
    "password_reset", "welcome", "order_confirmation",
    "deposit_approved", "account_locked", "catalog_seed_complete",
]
