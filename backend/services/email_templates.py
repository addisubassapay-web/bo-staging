"""Branded HTML email templates. Each helper returns (subject, html)."""
from __future__ import annotations
import os


BRAND_NAME = "Mercari-Global"
BRAND_ACCENT = "#FF211F"
FRONTEND = os.environ.get(
    "FRONTEND_ORIGIN", "https://seller-health-portal.preview.emergentagent.com"
)


def _shell(title: str, body_html: str, cta_url: str | None = None, cta_label: str | None = None) -> str:
    cta = ""
    if cta_url and cta_label:
        cta = (
            f'<a href="{cta_url}" style="display:inline-block;background:{BRAND_ACCENT};'
            f"color:#fff;font-weight:700;font-family:Arial,sans-serif;font-size:14px;"
            f'padding:12px 22px;border-radius:999px;text-decoration:none;">{cta_label}</a>'
        )
    return f"""<!doctype html>
<html><body style="margin:0;background:#F8FAFC;font-family:Arial,Helvetica,sans-serif;color:#111827;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="padding:24px 12px;">
    <tr><td align="center">
      <table role="presentation" width="560" cellpadding="0" cellspacing="0"
             style="background:#fff;border:1px solid #E5E7EB;border-radius:16px;overflow:hidden;">
        <tr><td style="padding:24px;background:linear-gradient(160deg,#0F172A,#1E293B);color:#fff;">
          <div style="font-size:20px;font-weight:800;letter-spacing:-0.02em;">
            <span style="color:{BRAND_ACCENT};">Mercari-Global</span> Global
          </div>
        </td></tr>
        <tr><td style="padding:28px 28px 8px 28px;">
          <h1 style="margin:0 0 10px;font-size:22px;">{title}</h1>
          <div style="font-size:14px;line-height:1.6;color:#374151;">{body_html}</div>
          <div style="margin:24px 0;">{cta}</div>
        </td></tr>
        <tr><td style="padding:16px 28px;border-top:1px solid #F1F5F9;color:#94A3B8;font-size:11px;">
          You&apos;re receiving this because of activity on your {BRAND_NAME} account.<br/>
          If this wasn&apos;t you, please contact support.
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""


def password_reset(reset_url: str, username: str | None = None):
    subject = "Reset your Mercari-Global password"
    who = f"Hi {username}," if username else "Hi,"
    body = (
        f"<p>{who}</p><p>We received a request to reset your password. "
        "This link is valid for 60 minutes and can be used once.</p>"
        "<p>If you didn&apos;t request this, you can safely ignore the message.</p>"
    )
    return subject, _shell("Reset your password", body, reset_url, "Set new password")


def welcome(username: str):
    subject = "Welcome to Mercari-Global"
    body = (
        f"<p>Hi {username}, your account is ready. Your storefront is auto-provisioned "
        "and you can list your first product right away.</p>"
    )
    return subject, _shell("Welcome aboard", body, f"{FRONTEND}/marketplace", "Open Mercari-Global")


def order_confirmation(buyer_name: str, order_id: str, listing_title: str, amount_str: str):
    subject = f"Order confirmed — #{order_id[:8]}"
    body = (
        f"<p>Hi {buyer_name}, thanks for your purchase.</p>"
        f"<p><b>{listing_title}</b><br/>Total: {amount_str}<br/>Order ID: {order_id[:8]}</p>"
    )
    return subject, _shell("Order confirmed", body, f"{FRONTEND}/profile?tab=orders", "Track order")


def deposit_approved(username: str, amount_str: str):
    subject = "Deposit credited to your wallet"
    body = f"<p>Hi {username}, your deposit of <b>{amount_str}</b> has been reviewed and credited.</p>"
    return subject, _shell("Deposit credited", body, f"{FRONTEND}/wallet", "Open wallet")


def account_locked(username: str, unlock_url: str):
    subject = "Your Mercari-Global account was temporarily locked"
    body = (
        f"<p>Hi {username}, your account was locked after too many failed sign-in attempts. "
        "For your safety, we&apos;ve auto-unlocked it if this was you. If not, please reset your password.</p>"
    )
    return subject, _shell("Account safety alert", body, unlock_url, "Reset password")


def catalog_seed_complete(username: str, provider: str, query: str, pages: int,
                          products_total: int, products_published: int,
                          duration_seconds: int, credits_spent: int):
    subject = f"Your seed of “{query}” is live — {products_published} products added"
    friendly_provider = {
        "amazon_search": "Amazon search",
        "amazon_bestsellers": "Amazon bestsellers",
        "mercari-global_search": "Mercari-Global search",
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
    return subject, _shell(
        "Seed complete",
        body,
        f"{FRONTEND}/profile?tab=listings",
        "Review your listings",
    )
