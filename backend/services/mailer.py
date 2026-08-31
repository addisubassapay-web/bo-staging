"""Email service — Hostinger SMTP.

Public API: `await send_email(to, subject, html, text=None, tags=[])`.
Reads config from env: SMTP_HOST, SMTP_PORT (465=SSL, 587=STARTTLS), SMTP_USER,
SMTP_PASS (or legacy SMTP_PASSWORD), SMTP_SECURE (true=SSL/STARTTLS wrapper,
false=plaintext), EMAIL_FROM_ADDRESS, EMAIL_FROM_NAME, EMAIL_PROVIDER.

By default the mailer HARD-FAILS if SMTP is not configured or the SMTP call
raises — so misconfigurations surface loudly to callers instead of silently
degrading to a mock. Set `EMAIL_ALLOW_MOCK=1` in dev to opt back into the
old mock-success behaviour.
"""
from __future__ import annotations
import logging
import os
from email.message import EmailMessage
from typing import Optional, List

import aiosmtplib

logger = logging.getLogger("email")


class MailerError(RuntimeError):
    """Raised when the mailer cannot deliver an email. Callers should
    catch this and return a 5xx to the client so users see a real error
    instead of a false-positive "code sent" toast."""


def _cfg():
    return {
        "provider": os.environ.get("EMAIL_PROVIDER", "").lower(),
        "host": os.environ.get("SMTP_HOST", ""),
        "port": int(os.environ.get("SMTP_PORT", "465") or 465),
        "user": os.environ.get("SMTP_USER", ""),
        # Prefer SMTP_PASS (new canonical name) with fallback to SMTP_PASSWORD
        # so existing production envs keep working during rollout.
        "password": os.environ.get("SMTP_PASS") or os.environ.get("SMTP_PASSWORD", ""),
        # SMTP_SECURE controls the transport wrapper. At port 465 the connection
        # starts in SSL; at 587 we upgrade via STARTTLS. `false` opts into
        # plaintext SMTP (dev only). Defaults to true.
        "secure": os.environ.get("SMTP_SECURE", "true").lower() not in ("0", "false", "no"),
        "from_addr": os.environ.get("EMAIL_FROM_ADDRESS", ""),
        "from_name": os.environ.get("EMAIL_FROM_NAME", "BlueOcean"),
    }


def _allow_mock() -> bool:
    return os.environ.get("EMAIL_ALLOW_MOCK", "").lower() in ("1", "true", "yes")


def is_configured() -> bool:
    c = _cfg()
    return bool(c["provider"] and c["host"] and c["user"] and c["password"] and c["from_addr"])


async def send_email(
    to: str,
    subject: str,
    html: str,
    text: Optional[str] = None,
    tags: Optional[List[str]] = None,
) -> dict:
    """Send an email. Returns {ok, provider, message_id?, to}. Raises
    MailerError on any delivery failure (unless EMAIL_ALLOW_MOCK=1)."""
    c = _cfg()
    if not is_configured():
        if _allow_mock():
            logger.info(f"[mock_email] to={to} subject={subject!r} tags={tags or []}")
            return {"ok": True, "provider": "mock", "mocked": True}
        raise MailerError(
            "SMTP not configured — set SMTP_HOST/USER/PASSWORD/EMAIL_FROM_ADDRESS/"
            "EMAIL_PROVIDER in backend/.env (or EMAIL_ALLOW_MOCK=1 for dev)."
        )

    msg = EmailMessage()
    msg["From"] = f'{c["from_name"]} <{c["from_addr"]}>'
    msg["To"] = to
    msg["Subject"] = subject
    if tags:
        msg["X-BlueOcean-Tags"] = ",".join(tags)
    msg.set_content(text or "Please view this email in an HTML-capable client.")
    msg.add_alternative(html, subtype="html")

    try:
        # SMTP_SECURE=true (default) — use SSL on 465, STARTTLS on 587/25.
        # SMTP_SECURE=false — plaintext SMTP (dev/private-network only).
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
        return {"ok": True, "provider": c["provider"], "to": to}
    except Exception as e:
        logger.error(f"email send failed to={to} subject={subject!r}: {e}")
        if _allow_mock():
            # Dev-only escape hatch — never in prod
            return {"ok": False, "provider": c["provider"], "error": str(e)}
        raise MailerError(f"SMTP delivery to {to} failed: {e}") from e
