"""IMAP receive service — read-only bounce ingest + admin inbox viewer.

Safest defaults:
  - imaplib.IMAP4_SSL on port 993 (SSL from the first byte)
  - Credentials read only from env, never logged
  - Runs in an asyncio.to_thread wrapper so the sync IMAP client can't
    block the FastAPI event loop
  - Read-only fetch: does NOT delete, move, or mark messages as read
  - Body decode is defensive (safe fallback on unknown charsets)

Public API:
  - fetch_inbox(limit=25, unseen_only=False) -> list[dict]
      Returns the most recent messages as {uid, from, to, subject, date,
      snippet, is_bounce}. Never blocks; safe to call from a request.
  - process_bounces(limit=50) -> dict
      Scans the last `limit` messages, extracts hard-bounce addresses
      from Mailer-Daemon reports, adds them to the suppression list, and
      returns {scanned, added}. Idempotent — the suppression list is
      upserted so re-runs never duplicate.
"""
from __future__ import annotations
import asyncio
import email
import imaplib
import logging
import os
import re
from email.header import decode_header, make_header
from email.message import Message
from typing import Optional

logger = logging.getLogger("imap")


def _cfg() -> dict:
    return {
        "host": os.environ.get("IMAP_HOST", ""),
        "port": int(os.environ.get("IMAP_PORT", "993") or 993),
        "user": os.environ.get("IMAP_USER", ""),
        "password": os.environ.get("IMAP_PASSWORD", ""),
        "mailbox": os.environ.get("IMAP_MAILBOX", "INBOX"),
    }


def is_configured() -> bool:
    c = _cfg()
    return bool(c["host"] and c["user"] and c["password"])


# ---------------------------------------------------------------------------
# Header/body decode helpers (sync — used inside asyncio.to_thread)
# ---------------------------------------------------------------------------
def _decode_header(raw: Optional[str]) -> str:
    if not raw:
        return ""
    try:
        return str(make_header(decode_header(raw)))
    except Exception:
        return raw


def _extract_body(msg: Message) -> str:
    """Prefer text/plain; fall back to text/html stripped of tags."""
    body = ""
    try:
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain" and not part.get_filename():
                    body = part.get_payload(decode=True) or b""
                    charset = part.get_content_charset() or "utf-8"
                    body = body.decode(charset, errors="replace")
                    break
            if not body:
                for part in msg.walk():
                    if part.get_content_type() == "text/html" and not part.get_filename():
                        payload = part.get_payload(decode=True) or b""
                        charset = part.get_content_charset() or "utf-8"
                        body = re.sub(r"<[^>]+>", "", payload.decode(charset, errors="replace"))
                        break
        else:
            payload = msg.get_payload(decode=True) or b""
            charset = msg.get_content_charset() or "utf-8"
            body = payload.decode(charset, errors="replace")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"body decode failed: {e}")
    return body[:20_000]  # hard cap


_MAILER_DAEMON_SUBJECTS = re.compile(
    r"(mail delivery|delivery status notification|undeliver|failure notice|returned mail|address rejected)",
    re.IGNORECASE,
)
_BOUNCE_ADDR = re.compile(r"(?:Final-Recipient|Original-Recipient|To|Failed Recipient)[:\s]+(?:rfc822;\s*)?([\w.+-]+@[\w-]+\.[\w.-]+)", re.IGNORECASE)
_HARD_BOUNCE_CODES = re.compile(r"\b5\.[1-7]\.[0-9]+\b|user unknown|no such user|does not exist|mailbox unavailable")


def _is_bounce(msg: Message, body: str) -> bool:
    sender = (msg.get("From") or "").lower()
    subj = msg.get("Subject") or ""
    if "mailer-daemon" in sender or "postmaster" in sender:
        return True
    if _MAILER_DAEMON_SUBJECTS.search(subj):
        return True
    return False


def _extract_bounced_addresses(msg: Message, body: str) -> list[str]:
    """Pull failed-recipient addresses from an RFC 3464 delivery status
    report or from the message body of a Mailer-Daemon reply."""
    found: set[str] = set()
    for match in _BOUNCE_ADDR.finditer(body or ""):
        addr = match.group(1).strip().lower()
        if "@" in addr and "mailer-daemon" not in addr and "postmaster" not in addr:
            found.add(addr)
    # Also walk any message/delivery-status parts
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "message/delivery-status":
                for match in _BOUNCE_ADDR.finditer(str(part)):
                    addr = match.group(1).strip().lower()
                    if "@" in addr:
                        found.add(addr)
    return list(found)


# ---------------------------------------------------------------------------
# Sync IMAP core — always called via asyncio.to_thread
# ---------------------------------------------------------------------------
def _sync_fetch(limit: int, unseen_only: bool) -> list[dict]:
    c = _cfg()
    if not is_configured():
        raise RuntimeError("IMAP not configured — set IMAP_HOST/USER/PASSWORD in backend/.env")
    out: list[dict] = []
    with imaplib.IMAP4_SSL(c["host"], c["port"], timeout=15) as srv:
        srv.login(c["user"], c["password"])
        # Read-only so we don't accidentally mark things as seen
        srv.select(c["mailbox"], readonly=True)
        search = "UNSEEN" if unseen_only else "ALL"
        typ, data = srv.search(None, search)
        if typ != "OK" or not data or not data[0]:
            return []
        ids = data[0].split()
        # newest first
        for msg_id in ids[-limit:][::-1]:
            typ, msg_data = srv.fetch(msg_id, "(BODY.PEEK[])")
            if typ != "OK" or not msg_data or not msg_data[0]:
                continue
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)
            body = _extract_body(msg)
            out.append({
                "uid": msg_id.decode(errors="replace"),
                "from": _decode_header(msg.get("From")),
                "to": _decode_header(msg.get("To")),
                "subject": _decode_header(msg.get("Subject")),
                "date": msg.get("Date") or "",
                "snippet": (body or "").strip().split("\n", 1)[0][:280],
                "is_bounce": _is_bounce(msg, body),
                "bounced_addresses": _extract_bounced_addresses(msg, body) if _is_bounce(msg, body) else [],
            })
    return out


# ---------------------------------------------------------------------------
# Public async API
# ---------------------------------------------------------------------------
async def fetch_inbox(limit: int = 25, unseen_only: bool = False) -> list[dict]:
    return await asyncio.to_thread(_sync_fetch, limit, unseen_only)


async def process_bounces(limit: int = 50) -> dict:
    """Scan the last `limit` messages, add any hard-bounced addresses to
    the suppression list. Delegates to routers.mailops.add_suppression
    so we never duplicate the schema."""
    from routers.mailops import add_suppression
    messages = await fetch_inbox(limit=limit, unseen_only=False)
    added: list[str] = []
    scanned_bounces = 0
    for m in messages:
        if not m["is_bounce"]:
            continue
        scanned_bounces += 1
        for addr in m["bounced_addresses"]:
            try:
                await add_suppression(
                    addr,
                    reason="hard_bounce",
                    source="imap_scan",
                    meta={"from": m["from"], "subject": m["subject"]},
                )
                added.append(addr)
            except ValueError:
                pass
            except Exception as e:  # noqa: BLE001
                logger.warning(f"suppression add failed for {addr}: {e}")
    return {
        "scanned_messages": len(messages),
        "bounce_messages": scanned_bounces,
        "suppressions_added": len(added),
        "addresses": added[:50],
    }
