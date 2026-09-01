"""Shared email templates — one visual system for every outbound message.

Every helper returns `(subject, html, text)` so callers can hand the tuple
straight to `services.mailer.send_email`.

Design principles:
  • One shell (`_shell`) — brand header + body + safety footer.
  • Indigo #5459E8 primary, red #FF0515 accent for time-sensitive CTAs.
  • Plain-text fallback for every template (email clients that strip HTML,
    Gmail's auto-generated preview, screen readers).
"""
from __future__ import annotations
import os

BRAND_NAME = "BlueOcean"
INDIGO = "#5459E8"
INDIGO_LIGHT = "#818CF8"
RED = "#FF0515"
RED_LIGHT = "#FF5B6B"
INK = "#0F172A"

FRONTEND = os.environ.get(
    "FRONTEND_ORIGIN", "https://ocean-marketplace.preview.emergentagent.com"
).rstrip("/")

SUPPORT_EMAIL = os.environ.get("SUPPORT_EMAIL", "mailsupport@blueoceansmarthub.com")
BUSINESS_ADDRESS = os.environ.get(
    "EMAIL_BUSINESS_ADDRESS",
    "BlueOcean Smarthub · reply to this email for our mailing address",
)


def _footer(is_transactional: bool = True, unsubscribe_url: str | None = None) -> str:
    """Standard footer. Non-transactional emails include a physical
    address and a one-click unsubscribe link (required by Gmail/Yahoo
    bulk-sender policy and by US CAN-SPAM). Transactional emails skip
    both to avoid tripping false-positive spam filters."""
    base = (
        f"You&apos;re receiving this because of activity on your {BRAND_NAME} account.<br/>"
        f'Questions? Reply to this email or write to '
        f'<a href="mailto:{SUPPORT_EMAIL}" style="color:{INDIGO};text-decoration:none;">{SUPPORT_EMAIL}</a>.'
    )
    if is_transactional:
        return base
    unsub = ""
    if unsubscribe_url:
        unsub = (
            f'<br/><br/><a href="{unsubscribe_url}" '
            f'style="color:#94A3B8;text-decoration:underline;">Unsubscribe</a> '
            "or update your email preferences at any time."
        )
    address = f'<br/><br/><span style="color:#CBD5E1;">{BUSINESS_ADDRESS}</span>'
    return base + unsub + address


def _shell(title: str, body_html: str, cta_url: str | None = None,
           cta_label: str | None = None, accent: str = "indigo",
           is_transactional: bool = True,
           unsubscribe_url: str | None = None) -> str:
    """Branded envelope. `accent` picks the CTA colour — 'indigo' for
    routine flows, 'red' for time-sensitive nudges. `is_transactional`
    strips the marketing footer (unsubscribe + physical address) to keep
    verification / password-reset / receipt emails spam-filter clean."""
    bg = INDIGO if accent == "indigo" else RED
    cta = ""
    if cta_url and cta_label:
        cta = (
            f'<a href="{cta_url}" style="display:inline-block;background:{bg};'
            'color:#fff;font-weight:700;font-family:Arial,sans-serif;font-size:14px;'
            'padding:14px 26px;border-radius:999px;text-decoration:none;">'
            f"{cta_label}</a>"
        )
    footer_html = _footer(is_transactional=is_transactional, unsubscribe_url=unsubscribe_url)
    return f"""<!doctype html>
<html><body style="margin:0;background:#F8FAFC;font-family:Arial,Helvetica,sans-serif;color:{INK};">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="padding:24px 12px;">
    <tr><td align="center">
      <table role="presentation" width="560" cellpadding="0" cellspacing="0"
             style="background:#fff;border:1px solid #E5E7EB;border-radius:16px;overflow:hidden;">
        <tr><td style="padding:22px;background:linear-gradient(135deg,{INDIGO} 0%,{INDIGO_LIGHT} 100%);color:#fff;">
          <div style="font-size:20px;font-weight:800;letter-spacing:-0.02em;">
            Blue<span style="color:#FFC7CB;">Ocean</span>
          </div>
          <div style="font-size:12px;opacity:0.9;">Smart Ecommerce Platform</div>
        </td></tr>
        <tr><td style="padding:28px 28px 8px 28px;">
          <h1 style="margin:0 0 10px;font-size:22px;color:{INK};">{title}</h1>
          <div style="font-size:14px;line-height:1.6;color:#374151;">{body_html}</div>
          <div style="margin:24px 0;">{cta}</div>
        </td></tr>
        <tr><td style="padding:16px 28px;border-top:1px solid #F1F5F9;color:#94A3B8;font-size:11px;">
          {footer_html}
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""


# ---------------------------------------------------------------------------
# Verify email — magic-link flow (POST /verify/email/send)
# ---------------------------------------------------------------------------
def verify_email(username: str, verify_url: str):
    subject = "Verify your BlueOcean email"
    who = f"Hi {username}," if username else "Hi there,"
    body = (
        f"<p>{who}</p>"
        "<p>Click the button below to confirm this email address on your BlueOcean account. "
        "The link is valid for 60 minutes.</p>"
        "<p style='color:#6B7280;font-size:12px;word-break:break-all;'>"
        f"Or paste this link into your browser:<br>{verify_url}</p>"
    )
    text = (
        f"Verify your BlueOcean email by opening this link (60 min expiry):\n"
        f"{verify_url}\n\nIf you didn't request this, ignore this email."
    )
    return subject, _shell("Confirm your email", body, verify_url, "Verify email", accent="indigo"), text


# ---------------------------------------------------------------------------
# 6-digit email OTP
# ---------------------------------------------------------------------------
def otp_email(username: str, code: str, purpose_label: str, expires_minutes: int):
    subject = f"Your BlueOcean verification code: {code}"
    who = f"Hi {username}," if username else "Hi there,"
    body = (
        f"<p>{who}</p>"
        f"<p>Use this 6-digit code to confirm your <b>{purpose_label}</b>. "
        f"The code expires in {expires_minutes} minutes.</p>"
        f'<div style="font-size:32px;letter-spacing:8px;font-weight:bold;'
        f'background:#EEF2FF;color:{INDIGO};text-align:center;padding:18px;'
        f'border-radius:12px;margin:16px 0;font-family:ui-monospace,SFMono-Regular,Consolas,monospace">{code}</div>'
        "<p style='color:#6B7280;font-size:13px;'>If you didn't request this, ignore this email — nothing will happen.</p>"
    )
    text = (
        f"Your BlueOcean verification code is: {code}\n\n"
        f"It expires in {expires_minutes} minutes. If you didn't request this, ignore this email."
    )
    return subject, _shell(f"Confirm your {purpose_label}", body, accent="indigo"), text


# ---------------------------------------------------------------------------
# Password reset
# ---------------------------------------------------------------------------
def password_reset(username: str, reset_url: str):
    subject = "Reset your BlueOcean password"
    who = f"Hi {username}," if username else "Hi,"
    body = (
        f"<p>{who}</p>"
        "<p>We received a request to reset your password. This link is valid for 60 minutes and can be used once.</p>"
        "<p>If you didn&apos;t request this, you can safely ignore the message.</p>"
    )
    text = (
        "Reset your BlueOcean password by opening this link (60 min expiry, single-use):\n"
        f"{reset_url}\n\nIf you didn't request this, ignore this email."
    )
    return subject, _shell("Reset your password", body, reset_url, "Set new password", accent="indigo"), text


# ---------------------------------------------------------------------------
# Onboarding nudges
# ---------------------------------------------------------------------------
def onboarding_payout_nudge(username: str, payout_url: str, unsubscribe_url: str | None = None):
    subject = "Finish setting up your BlueOcean store (60 sec)"
    who = f"Hi {username}," if username else "Hi there,"
    body = (
        f"<p>{who}</p>"
        "<p>Your BlueOcean store is live — but we can&apos;t send you any earnings until you connect a payout method. It takes 60 seconds.</p>"
        "<p style='color:#6B7280;font-size:13px;'>Once your payout is on file, buyers can complete purchases and your first payout is auto-scheduled.</p>"
    )
    text = (
        "Hi! Your BlueOcean store is live but no payout method is on file yet.\n"
        f"Connect one in 60 seconds: {payout_url}\n"
    )
    return subject, _shell(
        "One tap to start earning", body, payout_url, "Connect payout method",
        accent="indigo", is_transactional=False, unsubscribe_url=unsubscribe_url,
    ), text


def onboarding_zero_listing_nudge(username: str, sell_url: str, unsubscribe_url: str | None = None):
    subject = "Your BlueOcean store is empty — list your first item"
    who = f"Hi {username}," if username else "Hi there,"
    body = (
        f"<p>{who}</p>"
        "<p>Your BlueOcean store is set up, but there&apos;s nothing on the shelves yet. Shoppers are already browsing your category — the fastest way to your first sale is to list one item now.</p>"
        "<p style='color:#6B7280;font-size:13px;'>Listing takes under a minute: photo, price, condition. You can edit anything later.</p>"
    )
    text = (
        "Hi! Your BlueOcean store is empty — list one item to unlock your first sale.\n"
        f"Start here: {sell_url}\n"
    )
    return subject, _shell(
        "Your store is empty — let&apos;s fix that", body, sell_url,
        "List your first item", accent="red", is_transactional=False,
        unsubscribe_url=unsubscribe_url,
    ), text


# ---------------------------------------------------------------------------
# Transactional templates (migrated from services.email_templates so every
# outbound email now shares the indigo envelope).
# ---------------------------------------------------------------------------
def welcome(username: str):
    subject = "Welcome to BlueOcean"
    body = (
        f"<p>Hi {username}, your account is ready. Your storefront is auto-provisioned "
        "and you can list your first product right away.</p>"
    )
    text = f"Hi {username}, your BlueOcean account is ready. Open the marketplace: {FRONTEND}/marketplace"
    return subject, _shell("Welcome aboard", body, f"{FRONTEND}/marketplace", "Open BlueOcean", accent="indigo"), text


def order_confirmation(buyer_name: str, order_id: str, listing_title: str, amount_str: str):
    subject = f"Order confirmed — #{order_id[:8]}"
    body = (
        f"<p>Hi {buyer_name}, thanks for your purchase.</p>"
        f"<p><b>{listing_title}</b><br/>Total: {amount_str}<br/>Order ID: {order_id[:8]}</p>"
    )
    text = (
        f"Hi {buyer_name}, your order is confirmed.\n"
        f"{listing_title} — Total {amount_str} — Order {order_id[:8]}.\n"
        f"Track it: {FRONTEND}/profile?tab=orders"
    )
    return subject, _shell("Order confirmed", body, f"{FRONTEND}/profile?tab=orders", "Track order", accent="indigo"), text


def deposit_approved(username: str, amount_str: str):
    subject = "Deposit credited to your wallet"
    body = f"<p>Hi {username}, your deposit of <b>{amount_str}</b> has been reviewed and credited.</p>"
    text = f"Hi {username}, your deposit of {amount_str} has been credited to your BlueOcean wallet: {FRONTEND}/wallet"
    return subject, _shell("Deposit credited", body, f"{FRONTEND}/wallet", "Open wallet", accent="indigo"), text


def account_locked(username: str, unlock_url: str):
    subject = "Your BlueOcean account was temporarily locked"
    body = (
        f"<p>Hi {username}, your account was locked after too many failed sign-in attempts. "
        "For your safety, we&apos;ve auto-unlocked it if this was you. If not, please reset your password.</p>"
    )
    text = (
        f"Hi {username}, we locked your BlueOcean account after too many failed sign-ins.\n"
        f"Reset your password if that wasn't you: {unlock_url}"
    )
    return subject, _shell("Account safety alert", body, unlock_url, "Reset password", accent="red"), text


def seller_application_approved(username: str, dashboard_url: str | None = None):
    """Congratulate the applicant and point them at their new seller
    dashboard so the first payout setup happens the same session."""
    who = f"Hi {username}," if username else "Hi there,"
    cta_url = dashboard_url or f"{FRONTEND}/dashboard/seller"
    subject = "You're approved to sell on BlueOcean"
    body = (
        f"<p>{who}</p>"
        "<p>Great news — your seller application is <b>approved</b>. Your BlueOcean store is now live "
        "and you can list items, receive orders, and cash out earnings.</p>"
        "<p style='color:#6B7280;font-size:13px;margin-top:16px;'>"
        "Your next step: connect a payout method so we can send earnings the moment your first order is delivered."
        "</p>"
    )
    text = (
        f"Hi {username}, your BlueOcean seller application is approved.\n"
        f"Open your seller dashboard and connect a payout method: {cta_url}\n"
    )
    return subject, _shell("Seller application approved", body, cta_url, "Open seller dashboard", accent="indigo"), text


def seller_application_rejected(username: str, admin_notes: str = "", reapply_url: str | None = None):
    """Explain the decision without shaming. Include admin notes verbatim
    when present, and always offer a clear next step."""
    who = f"Hi {username}," if username else "Hi there,"
    cta_url = reapply_url or f"{FRONTEND}/apply-seller"
    subject = "Update on your BlueOcean seller application"
    notes_block = ""
    if admin_notes and admin_notes.strip():
        safe = (
            admin_notes.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\n", "<br/>")
        )[:2000]
        notes_block = (
            "<p style='margin-top:16px;font-size:13px;color:#374151;'>"
            "<b>Notes from our team:</b><br/>"
            f"<span style='color:#4B5563;'>{safe}</span></p>"
        )
    body = (
        f"<p>{who}</p>"
        "<p>Thanks for applying to sell on BlueOcean. After review we're <b>not able to approve</b> "
        "this application right now.</p>"
        f"{notes_block}"
        "<p style='color:#6B7280;font-size:13px;margin-top:16px;'>"
        "You can reply to this email if you'd like a second look, or update your details and re-apply below."
        "</p>"
    )
    text_notes = f"\nNotes: {admin_notes}\n" if admin_notes and admin_notes.strip() else ""
    text = (
        f"Hi {username}, your BlueOcean seller application wasn't approved this time.{text_notes}\n"
        f"Reply to this email to appeal, or re-apply: {cta_url}\n"
    )
    return subject, _shell(
        "Application update", body, cta_url, "Update details & re-apply",
        accent="indigo",
    ), text


def catalog_seed_complete(username: str, provider: str, query: str, pages: int,
                          products_total: int, products_published: int,
                          duration_seconds: int, credits_spent: int):
    subject = f"Your seed of \u201c{query}\u201d is live \u2014 {products_published} products added"
    friendly_provider = {
        "amazon_search": "Amazon search",
        "amazon_bestsellers": "Amazon bestsellers",
        "mercari-global_search": "BlueOcean search",
    }.get(provider, provider)
    minutes = max(1, duration_seconds // 60)
    body = (
        f"<p>Hi {username}, your automated catalog seed just finished.</p>"
        "<table role='presentation' cellpadding='0' cellspacing='0' width='100%' "
        "style='background:#F8FAFC;border-radius:12px;padding:14px;margin:12px 0;'>"
        f"<tr><td style='padding:6px 0;'><b>Source</b></td><td>{friendly_provider}</td></tr>"
        f"<tr><td style='padding:6px 0;'><b>Keyword</b></td><td>{query}</td></tr>"
        f"<tr><td style='padding:6px 0;'><b>Pages crawled</b></td><td>{pages}</td></tr>"
        f"<tr><td style='padding:6px 0;'><b>Products extracted</b></td><td>{products_total}</td></tr>"
        f"<tr><td style='padding:6px 0;'><b>Published live</b></td>"
        f"<td style='color:#059669;font-weight:700;'>{products_published}</td></tr>"
        f"<tr><td style='padding:6px 0;'><b>Zyte credits used</b></td><td>{credits_spent}</td></tr>"
        f"<tr><td style='padding:6px 0;'><b>Duration</b></td><td>~{minutes} min</td></tr>"
        "</table>"
        "<p>All items are already live in your storefront under the category you chose. "
        "Tap below to review them or start another seed.</p>"
    )
    text = (
        f"Hi {username}, your BlueOcean seed of \"{query}\" via {friendly_provider} finished.\n"
        f"{products_published} of {products_total} products published in {minutes} min.\n"
        f"Review your listings: {FRONTEND}/profile?tab=listings"
    )
    return subject, _shell("Seed complete", body, f"{FRONTEND}/profile?tab=listings", "Review your listings", accent="indigo"), text

