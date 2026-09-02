"""Broadcast the "BlueOcean progress update" to every existing user.

Design:
  * Goes through services.mailer.send_email → Resend primary, per-kind
    identity (marketing), List-Unsubscribe headers, rate-limited to
    EMAIL_RATE_LIMIT_PER_SECOND, suppression-list aware, delivery-log
    persisted.
  * Signed HMAC unsubscribe URL per recipient — one-click compliant.
  * Streams progress + failures to /app/backend/broadcast.log so admins
    can tail it while it runs.
  * Idempotency: uses a per-run "broadcast_id" + user email so a re-run
    on the same broadcast_id won't re-send. Change the ANNOUNCEMENT_ID
    below to force a fresh broadcast.
"""
import asyncio
import logging
import os
import sys
import time
from datetime import datetime, timezone

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

os.chdir("/app/backend")
sys.path.insert(0, "/app/backend")
load_dotenv()

# Wire the mailer delivery writer + idempotency lookup + suppression check
# the same way server.py does at boot — the script runs outside the API
# process so we must re-register.
from services import mailer  # noqa: E402
from routers.mailops import is_suppressed, unsubscribe_url, add_suppression  # noqa: F401,E402
from services import mailer_templates as tpl  # noqa: E402

ANNOUNCEMENT_ID = "progress-update-2026-09-02"
FRONTEND = os.environ.get("FRONTEND_ORIGIN", "https://blueoceansmarthub.com").rstrip("/")

LOG_PATH = "/app/backend/broadcast.log"
logging.basicConfig(
    filename=LOG_PATH, level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("broadcast")


def build_email(username: str, unsub: str):
    who = f"Hi {username}," if username else "Hi there,"
    body = (
        f"<p>{who}</p>"
        "<p>Quick update — we've been shipping a lot on BlueOcean over the past few weeks:</p>"
        "<ul style='margin:12px 0 12px 20px;padding:0;color:#374151;font-size:14px;line-height:1.8;'>"
        "<li>Rebranded end-to-end from Ocean to <b>BlueOcean Smarthub</b> with the new Aurora design system</li>"
        "<li>Real-time seller-application flow — apply in 60 seconds via /apply-seller</li>"
        "<li>Live SMTP + IMAP integrated support inbox (branded email addresses per purpose)</li>"
        "<li>Instant transactional emails via Resend with automatic Hostinger fallback</li>"
        "<li>Admin deliverability dashboard, master-pass override, bulk password reset, and more</li>"
        "</ul>"
        "<p>Everything runs on the same account you already have — just sign in and take a look.</p>"
        "<p style='color:#6B7280;font-size:13px;margin-top:16px;'>Thanks for being an early BlueOcean member.</p>"
    )
    text = (
        f"Hi {username}, quick progress update from BlueOcean:\n\n"
        "- Rebranded to BlueOcean Smarthub with the new Aurora design\n"
        "- Real-time seller-apply in 60 seconds\n"
        "- Live SMTP + IMAP support inbox\n"
        "- Resend-primary transactional email with Hostinger fallback\n"
        "- New Admin deliverability dashboard, master-pass override, bulk password reset\n\n"
        f"Sign in: {FRONTEND}\n"
    )
    subject = "What we've shipped on BlueOcean this month"
    html = tpl._shell(
        "What we've shipped this month", body,
        cta_url=FRONTEND, cta_label="Sign in",
        accent="indigo", is_transactional=False,
        unsubscribe_url=unsub,
    )
    return subject, html, text


async def main():
    mongo = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = mongo[os.environ["DB_NAME"]]

    # Register the writer + idempotency lookup so this script's sends
    # persist to email_delivery_log and show in /admin/deliverability.
    async def writer(entry: dict) -> None:
        try:
            await db.email_delivery_log.insert_one(entry)
        except Exception as e:
            log.warning(f"delivery-log write failed: {e}")

    async def idem_lookup(key: str):
        if not key:
            return None
        return await db.email_delivery_log.find_one(
            {"idempotency_key": key, "status": "sent"}, {"_id": 0},
        )

    # Registered suppression check needs to hit the running DB (this script
    # doesn't share process with server.py).
    async def check_suppressed(email: str) -> bool:
        return bool(await db.suppression_list.find_one({"email": email.strip().lower()}, {"_id": 0, "email": 1}))

    mailer.register_delivery_writer(writer)
    mailer.register_idempotency_lookup(idem_lookup)
    mailer.register_suppression_check(check_suppressed)

    users = await db.users.find(
        {"is_active": {"$ne": False}, "email": {"$regex": ".+@.+"}},
        {"_id": 0, "email": 1, "username": 1},
    ).to_list(10000)

    log.info(f"broadcast start id={ANNOUNCEMENT_ID} users={len(users)}")
    sent = failed = skipped = 0
    started = time.monotonic()

    for u in users:
        email = (u.get("email") or "").strip().lower()
        if not email or "@" not in email:
            skipped += 1
            continue
        # Skip obvious test / seed accounts to avoid Resend rejecting many
        # bad recipients in a row (protects sender reputation).
        if email.endswith("@t.local") or email.endswith("@example.com") \
                or email.endswith("@e2e.com") or email.endswith(".demo.local") \
                or "@mercari.local" in email:
            skipped += 1
            continue
        idem = f"{ANNOUNCEMENT_ID}::{email}"
        unsub = unsubscribe_url(email)
        subj, html, text = build_email(u.get("username") or "", unsub)
        try:
            r = await mailer.send_email(
                to=email, subject=subj, html=html, text=text,
                email_kind="marketing",
                is_transactional=False,
                unsubscribe_url=unsub,
                tags=["broadcast", ANNOUNCEMENT_ID],
                idempotency_key=idem,
            )
            if r.get("idempotent"):
                skipped += 1
            else:
                sent += 1
                log.info(f"sent to={email} provider={r.get('provider')} msg_id={r.get('message_id')}")
        except mailer.SuppressedRecipient:
            skipped += 1
        except Exception as e:
            failed += 1
            log.warning(f"failed to={email} err={str(e)[:200]}")

        if (sent + failed + skipped) % 25 == 0:
            log.info(f"progress sent={sent} failed={failed} skipped={skipped} elapsed={time.monotonic()-started:.0f}s")

    elapsed = time.monotonic() - started
    log.info(f"broadcast done id={ANNOUNCEMENT_ID} sent={sent} failed={failed} skipped={skipped} elapsed={elapsed:.0f}s")
    print(f"DONE sent={sent} failed={failed} skipped={skipped} elapsed={elapsed:.0f}s")
    mongo.close()


if __name__ == "__main__":
    asyncio.run(main())
