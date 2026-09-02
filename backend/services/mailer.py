"""Email service — professional-grade multi-provider stack.

Design (Sep 2026):
  * PRIMARY = Resend (modern REST ESP, higher deliverability, message-id
    tracking). Enabled via RESEND_ENABLED=true + RESEND_API_KEY.
  * FALLBACK = Hostinger SMTP (or any classic SMTP host). Kicks in
    automatically when the primary raises.
  * PER-KIND FROM identity — auth / receipts / marketing / seller /
    support / system. Each kind reads EMAIL_FROM_<KIND>_ADDRESS and
    EMAIL_FROM_<KIND>_NAME from env, falling back to the global
    EMAIL_FROM_ADDRESS / EMAIL_FROM_NAME. This mirrors how real ESPs
    isolate sending reputations by purpose.
  * DELIVERY LOG — every send is upserted into db.email_delivery_log
    with {id, to, subject, kind, provider, message_id, status,
    error, idempotency_key, at}. Admins can audit any email from
    /admin/mail/delivery-log.
  * IDEMPOTENCY — callers may pass idempotency_key; the same key inside
    a 60-second window returns the previous result without re-sending.
  * SUPPRESSION LIST — every send consults the registered check first;
    a hit raises SuppressedRecipient and never touches any provider.
  * RATE LIMITER — global token bucket at EMAIL_RATE_LIMIT_PER_SECOND.
  * CIRCUIT BREAKER — after 5 real failures in 60s, sends fail-fast
    with MailerError so background loops stop hammering.

Public API:
  await send_email(to, subject, html, text=None, tags=None,
                   email_kind="system", is_transactional=True,
                   unsubscribe_url=None, idempotency_key=None)
    -> {ok, provider, to, message_id?, kind, idempotent?}
"""
from __future__ import annotations
import asyncio
import logging
import os
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Awaitable, Callable, List, Optional

import aiosmtplib

logger = logging.getLogger("email")


class MailerError(RuntimeError):
    """Raised when the mailer cannot deliver an email."""


class SuppressedRecipient(MailerError):
    """Raised when the recipient is on the suppression list."""


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------
KNOWN_KINDS = ("auth", "receipts", "marketing", "seller", "support", "system")


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
        "rate_per_second": float(os.environ.get("EMAIL_RATE_LIMIT_PER_SECOND", "0.5")),
        "daily_cap": int(os.environ.get("EMAIL_DAILY_CAP", "500")),
    }


def _kind_identity(kind: str) -> dict:
    """Return {name, address, reply_to} for a given send-kind. Falls
    back to global EMAIL_FROM_* if per-kind vars are missing so nothing
    breaks when only some kinds are configured."""
    kind = (kind or "system").lower()
    if kind not in KNOWN_KINDS:
        kind = "system"
    global_cfg = _cfg()
    upper = kind.upper()
    return {
        "kind": kind,
        "name": os.environ.get(f"EMAIL_FROM_{upper}_NAME") or global_cfg["from_name"],
        "address": (
            os.environ.get(f"EMAIL_FROM_{upper}_ADDRESS")
            or global_cfg["from_addr"]
        ),
        "reply_to": (
            os.environ.get(f"EMAIL_REPLY_TO_{upper}")
            or global_cfg["reply_to"]
        ),
    }


def _allow_mock() -> bool:
    return os.environ.get("EMAIL_ALLOW_MOCK", "").lower() in ("1", "true", "yes")


def _resend_enabled() -> bool:
    return (
        os.environ.get("RESEND_ENABLED", "").lower() in ("1", "true", "yes")
        and bool(os.environ.get("RESEND_API_KEY", ""))
    )


def is_configured() -> bool:
    c = _cfg()
    smtp_ok = bool(c["host"] and c["user"] and c["password"] and c["from_addr"])
    return smtp_ok or _resend_enabled()


# ---------------------------------------------------------------------------
# Rate limiter (global token bucket, one per process)
# ---------------------------------------------------------------------------
_RATE_LOCK = asyncio.Lock()
_LAST_SEND_AT: float = 0.0


async def _rate_gate() -> None:
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
# Suppression list plumbing
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
    except Exception as e:
        logger.warning(f"suppression check errored for {email}: {e}")
        return False


# ---------------------------------------------------------------------------
# Delivery log plumbing (pluggable — server.py wires the Mongo writer)
# ---------------------------------------------------------------------------
_DELIVERY_WRITER: Optional[Callable[[dict], Awaitable[None]]] = None
_IDEMPOTENCY_LOOKUP: Optional[Callable[[str], Awaitable[Optional[dict]]]] = None


def register_delivery_writer(fn: Callable[[dict], Awaitable[None]]) -> None:
    global _DELIVERY_WRITER
    _DELIVERY_WRITER = fn


def register_idempotency_lookup(fn: Callable[[str], Awaitable[Optional[dict]]]) -> None:
    global _IDEMPOTENCY_LOOKUP
    _IDEMPOTENCY_LOOKUP = fn


async def _log_delivery(entry: dict) -> None:
    if _DELIVERY_WRITER is None:
        return
    try:
        await _DELIVERY_WRITER(entry)
    except Exception as e:
        logger.warning(f"delivery log write failed: {e}")


async def _idempotency_hit(key: str) -> Optional[dict]:
    if not key or _IDEMPOTENCY_LOOKUP is None:
        return None
    try:
        return await _IDEMPOTENCY_LOOKUP(key)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Send-outcome ring buffer for /admin/smtp/health
# ---------------------------------------------------------------------------
_SEND_HISTORY_MAX = 50
_SEND_HISTORY: "deque[dict]" = deque(maxlen=_SEND_HISTORY_MAX)


def _record_send_outcome(ok: bool, error: Optional[str]) -> None:
    _SEND_HISTORY.append({
        "ok": ok, "error": (error or "")[:400],
        "at": datetime.now(timezone.utc),
    })


def recent_send_outcomes(within_seconds: int = 900) -> list[dict]:
    cutoff = datetime.now(timezone.utc).timestamp() - within_seconds
    return [
        {**o, "at": o["at"].isoformat()}
        for o in list(_SEND_HISTORY)
        if o["at"].timestamp() >= cutoff
    ]


def _circuit_open() -> bool:
    cutoff = datetime.now(timezone.utc).timestamp() - 60
    recent = [o for o in list(_SEND_HISTORY) if o["at"].timestamp() >= cutoff]
    if len(recent) < 5:
        return False
    return all(not o["ok"] for o in recent[-5:])


# ---------------------------------------------------------------------------
# Public send API
# ---------------------------------------------------------------------------
async def send_email(
    to: str,
    subject: str,
    html: str,
    text: Optional[str] = None,
    tags: Optional[List[str]] = None,
    email_kind: str = "system",
    is_transactional: bool = True,
    unsubscribe_url: Optional[str] = None,
    idempotency_key: Optional[str] = None,
) -> dict:
    """Primary send entrypoint. Tries Resend first (when enabled), then
    falls back to SMTP. Every attempt is logged to db.email_delivery_log.
    Callers may pass an idempotency_key to short-circuit duplicate sends
    within a 60s window."""
    if not is_configured() and not _allow_mock():
        raise MailerError(
            "No mailer configured — set RESEND_API_KEY+RESEND_ENABLED or "
            "SMTP_HOST/USER/PASSWORD/EMAIL_FROM_ADDRESS in backend/.env."
        )

    # Idempotency check — return prior result if same key seen recently.
    if idempotency_key:
        prior = await _idempotency_hit(idempotency_key)
        if prior:
            return {
                **{k: prior.get(k) for k in ("ok", "provider", "to", "message_id", "kind")},
                "idempotent": True,
            }

    if _circuit_open():
        _record_send_outcome(False, "circuit_open")
        raise MailerError(
            "Mailer circuit-breaker open — 5 recent failures. Check "
            "/admin/smtp/health and /admin/mail/delivery-log."
        )

    if await _is_suppressed(to):
        raise SuppressedRecipient(f"Recipient {to} is on the suppression list")

    await _rate_gate()

    identity = _kind_identity(email_kind)
    entry_base = {
        "id": str(uuid.uuid4()),
        "to": to,
        "subject": subject[:400],
        "kind": identity["kind"],
        "tags": (tags or [])[:10],
        "is_transactional": is_transactional,
        "idempotency_key": idempotency_key,
        "at": datetime.now(timezone.utc),
    }

    # ---------- try Resend first (professional-grade primary) ----------
    if _resend_enabled():
        try:
            result = await _send_via_resend(
                to=to, subject=subject, html=html, text=text,
                identity=identity, is_transactional=is_transactional,
                unsubscribe_url=unsubscribe_url, tags=tags,
            )
            _record_send_outcome(True, None)
            await _log_delivery({**entry_base, "provider": "resend",
                                 "message_id": result.get("message_id"),
                                 "status": "sent", "error": None})
            return {**result, "kind": identity["kind"]}
        except Exception as re_err:
            resend_msg = str(re_err)
            logger.warning(f"Resend primary failed to={to}: {resend_msg} — trying SMTP")
            _record_send_outcome(False, f"resend_primary: {resend_msg}")

    # ---------- SMTP path (fallback, or primary when Resend disabled) ----------
    c = _cfg()
    if not (c["host"] and c["user"] and c["password"]):
        # No SMTP configured — last resort is mock mode, or hard fail
        if _allow_mock():
            await _log_delivery({**entry_base, "provider": "mock",
                                 "status": "sent", "error": None})
            return {"ok": True, "provider": "mock", "to": to,
                    "kind": identity["kind"], "mocked": True}
        raise MailerError("Resend failed and SMTP not configured.")

    msg = EmailMessage()
    msg["From"] = f'{identity["name"]} <{identity["address"]}>'
    msg["To"] = to
    msg["Subject"] = subject
    if identity["reply_to"]:
        msg["Reply-To"] = identity["reply_to"]
    if tags:
        msg["X-BlueOcean-Tags"] = ",".join(tags)
    msg["X-BlueOcean-Kind"] = identity["kind"]
    if not is_transactional and unsubscribe_url:
        msg["List-Unsubscribe"] = (
            f"<mailto:{identity['reply_to'] or identity['address']}?subject=unsubscribe>, "
            f"<{unsubscribe_url}>"
        )
        msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
        msg["Precedence"] = "bulk"
    msg.set_content(text or "Please view this email in an HTML-capable client.")
    msg.add_alternative(html, subtype="html")

    try:
        secure = c["secure"]
        use_tls = secure and c["port"] == 465
        start_tls = secure and c["port"] in (587, 25)
        await aiosmtplib.send(
            msg, hostname=c["host"], port=c["port"],
            username=c["user"], password=c["password"],
            use_tls=use_tls,
            start_tls=start_tls if not use_tls else False,
            timeout=20,
        )
        _record_send_outcome(True, None)
        await _log_delivery({**entry_base, "provider": c["provider"] or "smtp",
                             "status": "sent", "error": None})
        return {"ok": True, "provider": c["provider"] or "smtp",
                "to": to, "kind": identity["kind"]}
    except Exception as e:
        smtp_err = str(e)
        logger.error(f"SMTP send failed to={to} subject={subject!r} kind={identity['kind']}: {smtp_err}")
        _record_send_outcome(False, smtp_err)
        await _log_delivery({**entry_base, "provider": c["provider"] or "smtp",
                             "status": "failed", "error": smtp_err[:400]})
        if _allow_mock():
            return {"ok": False, "provider": c["provider"], "error": smtp_err,
                    "kind": identity["kind"]}
        raise MailerError(f"All email providers failed for {to}: {smtp_err}") from e


# ---------------------------------------------------------------------------
# Resend send helper
# ---------------------------------------------------------------------------
async def _send_via_resend(
    to: str, subject: str, html: str, text: Optional[str],
    identity: dict, is_transactional: bool,
    unsubscribe_url: Optional[str], tags: Optional[List[str]],
) -> dict:
    import resend
    resend.api_key = os.environ.get("RESEND_API_KEY", "")
    # Prefer per-kind from address, but if it's the branded domain and
    # Resend hasn't verified that domain yet, fall back to the account's
    # RESEND_FROM_ADDRESS (typically onboarding@resend.dev).
    from_addr = (
        os.environ.get("RESEND_FROM_ADDRESS")
        if os.environ.get("RESEND_USE_FALLBACK_FROM", "").lower() in ("1", "true", "yes")
        else identity["address"] or os.environ.get("RESEND_FROM_ADDRESS", "")
    )
    from_name = identity["name"] or os.environ.get("RESEND_FROM_NAME", "BlueOcean")
    headers: dict = {"X-BlueOcean-Kind": identity["kind"]}
    if not is_transactional and unsubscribe_url:
        headers["List-Unsubscribe"] = (
            f"<mailto:{identity['reply_to'] or from_addr}?subject=unsubscribe>, "
            f"<{unsubscribe_url}>"
        )
        headers["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    params: dict = {
        "from": f"{from_name} <{from_addr}>",
        "to": [to], "subject": subject, "html": html,
        "headers": headers,
    }
    if text:
        params["text"] = text
    if identity["reply_to"]:
        params["reply_to"] = identity["reply_to"]
    if tags:
        params["tags"] = [{"name": f"tag_{i}", "value": str(t)} for i, t in enumerate(tags[:10])]
    result = await asyncio.to_thread(resend.Emails.send, params)
    return {
        "ok": True, "provider": "resend", "to": to,
        "message_id": (result or {}).get("id"),
    }
