"""Email service — Hostinger SMTP with a mock fallback.

Public API: `await send_email(to, subject, html, text=None, tags=[])`.
Reads config from env: SMTP_HOST, SMTP_PORT (465=SSL, 587=STARTTLS), SMTP_USER,
SMTP_PASSWORD, EMAIL_FROM_ADDRESS, EMAIL_FROM_NAME, EMAIL_PROVIDER.
When EMAIL_PROVIDER is unset the send is logged and no network call is made.
"""
from __future__ import annotations
import logging
import os
from email.message import EmailMessage
from typing import Optional, List

import aiosmtplib

logger = logging.getLogger("email")


def _cfg():
    return {
        "provider": os.environ.get("EMAIL_PROVIDER", "").lower(),
        "host": os.environ.get("SMTP_HOST", ""),
        "port": int(os.environ.get("SMTP_PORT", "465") or 465),
        "user": os.environ.get("SMTP_USER", ""),
        "password": os.environ.get("SMTP_PASSWORD", ""),
        "from_addr": os.environ.get("EMAIL_FROM_ADDRESS", ""),
        "from_name": os.environ.get("EMAIL_FROM_NAME", "Merchari-global"),
    }


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
    """Send an email. Returns {ok, provider, message_id?, error?}."""
    c = _cfg()
    if not is_configured():
        logger.info(f"[mock_email] to={to} subject={subject!r} tags={tags or []}")
        return {"ok": True, "provider": "mock", "mocked": True}

    msg = EmailMessage()
    msg["From"] = f'{c["from_name"]} <{c["from_addr"]}>'
    msg["To"] = to
    msg["Subject"] = subject
    if tags:
        msg["X-Merchari-global-Tags"] = ",".join(tags)
    msg.set_content(text or "Please view this email in an HTML-capable client.")
    msg.add_alternative(html, subtype="html")

    try:
        # Port 465 = implicit SSL, 587 = STARTTLS.
        use_tls = c["port"] == 465
        start_tls = c["port"] in (587, 25)
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
        return {"ok": False, "provider": c["provider"], "error": str(e)}
