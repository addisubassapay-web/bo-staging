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

SUPPORT_EMAIL = os.environ.get("SUPPORT_EMAIL", "supportteam@blueoceansmarthub.com")


def _shell(title: str, body_html: str, cta_url: str | None = None,
           cta_label: str | None = None, accent: str = "indigo") -> str:
    """Branded envelope. `accent` picks the CTA colour — 'indigo' for
    routine flows, 'red' for time-sensitive nudges."""
    bg = INDIGO if accent == "indigo" else RED
    cta = ""
    if cta_url and cta_label:
        cta = (
            f'<a href="{cta_url}" style="display:inline-block;background:{bg};'
            'color:#fff;font-weight:700;font-family:Arial,sans-serif;font-size:14px;'
            'padding:14px 26px;border-radius:999px;text-decoration:none;">'
            f"{cta_label}</a>"
        )
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
          You&apos;re receiving this because of activity on your {BRAND_NAME} account.<br/>
          Questions? Reply to this email or write to <a href="mailto:{SUPPORT_EMAIL}" style="color:{INDIGO};text-decoration:none;">{SUPPORT_EMAIL}</a>.
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
def onboarding_payout_nudge(username: str, payout_url: str):
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
    return subject, _shell("One tap to start earning", body, payout_url, "Connect payout method", accent="indigo"), text


def onboarding_zero_listing_nudge(username: str, sell_url: str):
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
    return subject, _shell("Your store is empty — let&apos;s fix that", body, sell_url, "List your first item", accent="red"), text
