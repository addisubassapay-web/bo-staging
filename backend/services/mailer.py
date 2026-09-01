"""Email service — Hostinger SMTP + deliverability hygiene.

Public API: `await send_email(to, subject, html, text=None, tags=[],
is_transactional=True, unsubscribe_url=None)`.

Anti-suspension hardening (Sep 2026):
  1. Distinct `From` (branded) and `Reply-To` (support inbox) headers.
  2. List-Unsubscribe + List-Unsubscribe-Post headers on non-transactional
     mail (required by Gmail/Yahoo bulk-sender policy since Feb 2024).
  3. Global token-bucket rate limit — `EMAIL_RATE_LIMIT_PER_SECOND`
     env var caps outbound velocity so a bulk digest can't scream past
     Hostinger's abuse detector.
  4. Suppression-list check — if a `SUPPRESSION_CHECK` callable was
     registered by the app on startup, any recipient it flags is skipped
     without touching SMTP (protects sender reputation on hard-bounces
     and unsubscribes).
  5. In-memory send-outcome ring buffer (`recent_send_outcomes`) so
     `/admin/smtp/health` can spot DATA-stage 554 blocks that handshake
     probes miss.
"""
from __future__ import annotations
import asyncio
import logging
import os
import time
from collections import deque
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Callable, Awaitable, Optional, List

import aiosmtplib

logger = logging.getLogger("email")


class MailerError(RuntimeError):
    """Raised when the mailer cannot deliver an email. Callers should
    catch this and return a 5xx to the client so users see a real error
    instead of a false-positive "code sent" toast."""


class SuppressedRecipient(MailerError):
    """Raised when the recipient is on the suppression list (hard bounce
    or unsubscribed). Callers can catch this specifically to log without
    alerting."""


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
def _cfg():
    return {
        "provider": os.environ.get("EMAIL_PROVIDER", "").lower(),
        "host": os.environ.get("SMTP_HOST", ""),
        "port": int(os.environ.get("SMTP_PORT", "465") or 465),
        "user": os.environ.get("SMTP_USER", ""),
        "password": os.environ.get("SMTP_PASS") or os.environ.get("SMTP_PASSWORD", ""),
        "secure": os.environ.get("SMTP_SECURE", "true").lower() not in ("0", "false", "no"),
        "from_addr": os.environ.get("EMAIL_FROM_ADDRESS", ""),
        "from_name": os.environ.get("EMAIL_FROM_NAME", "BlueOcean"),
        "reply_to": os.environ.get("EMAIL_REPLY_TO", "").strip(),
        "business_address": os.environ.get(
            "EMAIL_BUSINESS_ADDRESS",
            "BlueOcean Smarthub · Reply for a physical mailing address.",
        ),
        # Deliverability limits — 1 email / 2 s by default (0.5/s).
        # Raise gradually only after a clean sending history at Hostinger.
        "rate_per_second": float(os.environ.get("EMAIL_RATE_LIMIT_PER_SECOND", "0.5")),
        # Optional soft cap; not enforced yet — recorded so a future
        # daily reconciliation cron can pause sends near the ceiling.
        "daily_cap": int(os.environ.get("EMAIL_DAILY_CAP", "500")),
    }


def _allow_mock() -> bool:
    return os.environ.get("EMAIL_ALLOW_MOCK", "").lower() in ("1", "true", "yes")


def is_configured() -> bool:
    c = _cfg()
    return bool(c["provider"] and c["host"] and c["user"] and c["password"] and c["from_addr"])


# ---------------------------------------------------------------------------
# Global rate limiter — simple token bucket. One per process; the whole
# app shares a single limiter so background workers can't dodge it.
# ---------------------------------------------------------------------------
_RATE_LOCK = asyncio.Lock()
_LAST_SEND_AT: float = 0.0


async def _rate_gate() -> None:
    """Sleep until the next allowed send slot given
    `EMAIL_RATE_LIMIT_PER_SECOND`. Zero or negative disables the gate."""
    per_sec = _cfg()["rate_per_second"]
    if per_sec <= 0:
        return
    global _LAST_SEND_AT
    min_interval = 1.0 / per_sec
    async with _RATE_LOCK:
        now = time.monotonic()
        wait = _LAST_SEND_AT + min_interval - now
        if wait > 0:
            await asyncio.sleep(wait)
        _LAST_SEND_AT = time.monotonic()


# ---------------------------------------------------------------------------
# Suppression list — pluggable async callable that returns True if the
# given address should be skipped. Registered from app startup so the
# mailer service stays decoupled from Mongo.
# ---------------------------------------------------------------------------
_SUPPRESSION_CHECK: Optional[Callable[[str], Awaitable[bool]]] = None


def register_suppression_check(fn: Callable[[str], Awaitable[bool]]) -> None:
    global _SUPPRESSION_CHECK
    _SUPPRESSION_CHECK = fn


async def _is_suppressed(email: str) -> bool:
    if _SUPPRESSION_CHECK is None:
        return False
    try:
        return await _SUPPRESSION_CHECK(email)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"suppression check errored for {email}: {e}")
        return False


# ---------------------------------------------------------------------------
# Public send API
# ---------------------------------------------------------------------------
async def send_email(
    to: str,
    subject: str,
    html: str,
    text: Optional[str] = None,
    tags: Optional[List[str]] = None,
    is_transactional: bool = True,
    unsubscribe_url: Optional[str] = None,
) -> dict:
    """Send an email. Returns {ok, provider, message_id?, to}. Raises
    MailerError on delivery failure (unless EMAIL_ALLOW_MOCK=1) and
    SuppressedRecipient if the recipient is on the suppression list.

    * is_transactional: True for password resets, OTPs, order receipts,
      welcome, account-locked, deposit-approved. These MUST have no
      unsubscribe link — legally and functionally they're not marketing.
      False for digests, nudges, seed-complete confetti — these get
      List-Unsubscribe headers, a physical address, and a visible
      unsubscribe link (the caller passes `unsubscribe_url`).
    """
    c = _cfg()
    if not is_configured():
        if _allow_mock():
            logger.info(f"[mock_email] to={to} subject={subject!r} tags={tags or []}")
            return {"ok": True, "provider": "mock", "mocked": True}
        raise MailerError(
            "SMTP not configured — set SMTP_HOST/USER/PASSWORD/EMAIL_FROM_ADDRESS/"
            "EMAIL_PROVIDER in backend/.env (or EMAIL_ALLOW_MOCK=1 for dev)."
        )

    # 0) Circuit breaker — if the last 5 real sends have all failed
    # within the last 60s, don't waste another 5-20s SMTP timeout;
    # fail fast so the escrow / notification / digest loops can move
    # on and the API doesn't get starved of the connection pool.
    if _circuit_open():
        _record_send_outcome(False, "circuit_open: skipping SMTP after 5 recent failures")
        raise MailerError(
            "Mailer circuit-breaker open — 5 recent send failures. "
            "Fix SMTP (check /admin/smtp/health) then retry."
        )

    # 1) Suppression check — never send to hard-bounced / unsubscribed addrs.
    if await _is_suppressed(to):
        logger.info(f"[suppressed] skipped send to={to} subject={subject!r}")
        raise SuppressedRecipient(f"Recipient {to} is on the suppression list")

    # 2) Global rate gate.
    await _rate_gate()

    # 3) Compose.
    msg = EmailMessage()
    msg["From"] = f'{c["from_name"]} <{c["from_addr"]}>'
    msg["To"] = to
    msg["Subject"] = subject
    if c["reply_to"]:
        msg["Reply-To"] = c["reply_to"]
    if tags:
        msg["X-BlueOcean-Tags"] = ",".join(tags)
    # 4) List-Unsubscribe headers ONLY for non-transactional sends.
    # Gmail/Yahoo bulk-sender policy (Feb 2024) requires these on any
    # commercial email; adding them to transactional email can trip
    # false-positive spam filters.
    if not is_transactional and unsubscribe_url:
        msg["List-Unsubscribe"] = (
            f"<mailto:{c['reply_to'] or c['from_addr']}?subject=unsubscribe>, "
            f"<{unsubscribe_url}>"
        )
        msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
        msg["Precedence"] = "bulk"

    msg.set_content(text or "Please view this email in an HTML-capable client.")
    msg.add_alternative(html, subtype="html")

    # 5) Send via primary SMTP, with automatic Resend fallback on failure.
    try:
        secure = c["secure"]
        use_tls = secure and c["port"] == 465
        start_tls = secure and c["port"] in (587, 25)
        await aiosmtplib.send(
            msg,
            hostname=c["host"],
            port=c["port"],
            username=c["user"],
            password=c["password"],
            use_tls=use_tls,
            start_tls=start_tls if not use_tls else False,
            timeout=20,
        )
        _record_send_outcome(True, None)
        return {"ok": True, "provider": c["provider"], "to": to}
    except Exception as e:
        smtp_err = str(e)
        logger.error(f"email send failed to={to} subject={subject!r}: {smtp_err}")
        _record_send_outcome(False, smtp_err)
        # Automatic Resend fallback — kicks in on ANY SMTP failure so a
        # 554-outbound-disabled at Hostinger, an auth flake, a timeout,
        # or a transient network drop can never break user-facing flows.
        if _resend_enabled():
            try:
                result = await _send_via_resend(
                    to=to, subject=subject, html=html, text=text,
                    is_transactional=is_transactional,
                    unsubscribe_url=unsubscribe_url,
                    tags=tags,
                )
                _record_send_outcome(True, None)
                logger.info(f"email delivered via Resend fallback to={to} (SMTP failed)")
                return result
            except Exception as re_err:  # noqa: BLE001
                logger.error(f"Resend fallback ALSO failed to={to}: {re_err}")
                _record_send_outcome(False, f"resend_fallback_failed: {re_err}")
        if _allow_mock():
            return {"ok": False, "provider": c["provider"], "error": smtp_err}
        raise MailerError(f"SMTP delivery to {to} failed: {smtp_err}") from e


# ---------------------------------------------------------------------------
# Resend fallback ESP — activates only when the primary SMTP send raises.
# ---------------------------------------------------------------------------
def _resend_enabled() -> bool:
    return (
        os.environ.get("RESEND_ENABLED", "").lower() in ("1", "true", "yes")
        and bool(os.environ.get("RESEND_API_KEY", ""))
    )


async def _send_via_resend(
    to: str,
    subject: str,
    html: str,
    text: Optional[str] = None,
    is_transactional: bool = True,
    unsubscribe_url: Optional[str] = None,
    tags: Optional[List[str]] = None,
) -> dict:
    """Send a single email through Resend's HTTPS API. Sync SDK is
    dispatched to a thread so it can't block the FastAPI event loop.
    Adds Reply-To and (for marketing) List-Unsubscribe headers so parity
    with the SMTP path is preserved."""
    import resend  # local import — keeps startup lean when Resend is off
    api_key = os.environ.get("RESEND_API_KEY", "")
    resend.api_key = api_key
    from_name = os.environ.get("RESEND_FROM_NAME") or os.environ.get("EMAIL_FROM_NAME", "BlueOcean")
    from_addr = os.environ.get("RESEND_FROM_ADDRESS") or os.environ.get("EMAIL_FROM_ADDRESS", "")
    reply_to = os.environ.get("EMAIL_REPLY_TO", "").strip()
    headers: dict = {}
    if not is_transactional and unsubscribe_url:
        headers["List-Unsubscribe"] = (
            f"<mailto:{reply_to or from_addr}?subject=unsubscribe>, "
            f"<{unsubscribe_url}>"
        )
        headers["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    params: dict = {
        "from": f"{from_name} <{from_addr}>",
        "to": [to],
        "subject": subject,
        "html": html,
    }
    if text:
        params["text"] = text
    if reply_to:
        params["reply_to"] = reply_to
    if headers:
        params["headers"] = headers
    if tags:
        # Resend requires unique tag names — give each a positional key.
        params["tags"] = [{"name": f"tag_{i}", "value": str(t)} for i, t in enumerate(tags[:10])]
    result = await asyncio.to_thread(resend.Emails.send, params)
    return {
        "ok": True,
        "provider": "resend",
        "to": to,
        "message_id": (result or {}).get("id"),
    }


# ---------------------------------------------------------------------------
# In-memory outcome tracker for the /admin/smtp/health probe.
# ---------------------------------------------------------------------------
_SEND_HISTORY_MAX = 50
_SEND_HISTORY: "deque[dict]" = deque(maxlen=_SEND_HISTORY_MAX)


def _record_send_outcome(ok: bool, error: Optional[str]) -> None:
    _SEND_HISTORY.append({
        "ok": ok,
        "error": (error or "")[:400],
        "at": datetime.now(timezone.utc),
    })


def recent_send_outcomes(within_seconds: int = 900) -> list[dict]:
    """Return the last N send outcomes newer than `within_seconds` ago."""
    cutoff = datetime.now(timezone.utc).timestamp() - within_seconds
    return [
        {**o, "at": o["at"].isoformat()}
        for o in list(_SEND_HISTORY)
        if o["at"].timestamp() >= cutoff
    ]


def _circuit_open() -> bool:
    """Return True if the last 5 real send outcomes within the last 60s
    are all failures. This blocks the mailer from wasting another 5-20s
    SMTP timeout when we already know delivery is broken, so background
    loops (escrow digests, seller nudges) stop hogging the API's
    connection pool during an outage. Auto-recovers as soon as any send
    succeeds (records replace old failures in the ring buffer) or as
    soon as the failures age out of the 60s window."""
    cutoff = datetime.now(timezone.utc).timestamp() - 60
    recent = [o for o in list(_SEND_HISTORY) if o["at"].timestamp() >= cutoff]
    if len(recent) < 5:
        return False
    tail = recent[-5:]
    return all(not o["ok"] for o in tail)
