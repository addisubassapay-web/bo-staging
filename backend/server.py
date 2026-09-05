from fastapi import FastAPI, APIRouter, HTTPException, Depends, Query, status, UploadFile, File, Form, Header, Response, Request, Body
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import time
import logging
import base64
import secrets
import random
import re
import json as _json
import httpx
from pathlib import Path
from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional, Literal, Dict, Any
import uuid
import asyncio
from datetime import datetime, timezone, timedelta
import jwt
import requests as _requests
from passlib.context import CryptContext
from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent

from apify_sync import import_from_apify, simulate_live_update, get_sync_status
from shipping_providers import get_provider as get_shipping_provider, next_stage_for_age, event_details
from routers.search import router as search_router
from routers.discovery import router as discovery_router
from routers.users import router as users_router
from routers.newsletter import router as newsletter_router
from routers.google_auth import router as google_auth_router
from routers.auth import router as auth_router
from routers.onboarding_nudges import router as onboarding_nudges_router
from routers.stores_search import router as stores_search_router
from routers.shopping import router as shopping_router
from routers.listings import router as listings_router
from routers.personalized import router as personalized_router
from routers.checkout import router as checkout_router
from routers.coupons import router as coupons_router
from routers.scraper_stub import router as scraper_router
from routers.store_boosts import router as store_boosts_router
from routers.products import router as products_router
from routers.apify_runs import router as apify_runs_router
from routers.support import router as support_router
from routers.otp import router as otp_router
from routers.reviews import router as reviews_router
from routers.messaging import router as messaging_router
from routers.notifications import router as notifications_router
from routers.affiliate import router as affiliate_router
from routers.disputes import router as disputes_router
from routers.shipping import router as shipping_router


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

JWT_SECRET = os.environ.get('JWT_SECRET', 'change-me')
JWT_ALG = "HS256"
JWT_EXPIRE_HOURS = 24 * 7

EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")
AI_MODEL_PROVIDER = "openai"
AI_MODEL_NAME = "gpt-5.4"  # Set to gpt-5.6-luna, gpt-5.6-terra, gpt-5.6-sol etc. if desired

# Emergent object storage
STORAGE_BASE = (os.environ.get("INTEGRATION_PROXY_URL") or "").strip() or "https://integrations.emergentagent.com"
STORAGE_URL = STORAGE_BASE.rstrip("/") + "/objstore/api/v1/storage"
APP_NAME = "ocean"
_storage_key: Optional[str] = None

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)

app = FastAPI(title="Ocean Clone API")
api_router = APIRouter(prefix="/api")

# Static mount for scraper/local media uploads — served at /api/uploads/*
# so it flows through the same Kubernetes ingress rule as the rest of the API.
from fastapi.staticfiles import StaticFiles
_UPLOADS_DIR = Path(os.environ.get("MEDIA_LOCAL_ROOT") or "/app/backend/uploads")
_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/api/uploads", StaticFiles(directory=str(_UPLOADS_DIR)), name="uploads")


# ---------------------------------------------------------------------------
# Liveness / readiness probes
# ---------------------------------------------------------------------------
# Kubernetes hits `GET /health` (no `/api` prefix) at ~1Hz for liveness /
# readiness. Answer with a cheap 200 so the pod is never marked unhealthy.
# We also expose `/api/health` for the ingress-routed variant that the
# frontend + platform monitors sometimes probe.
@app.get("/health", include_in_schema=False)
@app.head("/health", include_in_schema=False)
async def _root_health(force_degraded: int = 0):
    return await _build_health_payload(force_degraded=bool(force_degraded))


@app.get("/api/health", include_in_schema=False)
@app.head("/api/health", include_in_schema=False)
async def _api_health(force_degraded: int = 0):
    return await _build_health_payload(force_degraded=bool(force_degraded))


# ---- Simulated-degraded state ----
# Persists in memory only. Set via POST /api/admin/health/force-degraded so
# operators can prove the Slack-paging pipeline end-to-end without needing to
# actually break Mongo or SMTP. Auto-clears after `duration_sec`.
_FORCE_DEGRADED_UNTIL_TS: float = 0.0
_FORCE_DEGRADED_REASON: str = ""


async def _build_health_payload(*, force_degraded: bool = False) -> dict:
    """Assemble the enriched heartbeat body.

    - ``db.latency_ms``: round-trip time for a Mongo `ping` command, or
      ``None`` when the ping fails / times out (2s cap).
    - ``mailer.breaker_open``: True when the mailer circuit-breaker is
      currently tripped (5 recent failures). Ops can watch this in the
      self-ping log to spot SMTP outages without opening the admin panel.
    - Overall ``status``: ``ok`` when the DB ping succeeds AND the
      admin-simulated ``_FORCE_DEGRADED_UNTIL_TS`` window has expired.
      Otherwise ``degraded`` so external monitors can alert.
    - ``force_degraded`` (query param, dev-only) — returns ``degraded`` for
      this single response without touching the shared timer. Handy for
      one-off Postman probes.
    """
    # ---- Mongo latency ----
    db_latency_ms: float | None = None
    db_ok = False
    try:
        _t0 = time.monotonic()
        await asyncio.wait_for(db.command("ping"), timeout=2.0)
        db_latency_ms = round((time.monotonic() - _t0) * 1000, 2)
        db_ok = True
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[health] mongo ping failed: {e}")

    # ---- Mailer circuit breaker ----
    breaker_open = False
    try:
        from services import mailer as _mailer
        breaker_open = bool(_mailer._circuit_open())
    except Exception as e:  # noqa: BLE001 — best-effort observability
        logger.warning(f"[health] mailer breaker probe failed: {e}")

    # ---- Admin-simulated / query-forced degrade ----
    simulated = False
    now = time.monotonic()
    if _FORCE_DEGRADED_UNTIL_TS > now:
        simulated = True
    if force_degraded:
        simulated = True

    overall = "degraded" if (simulated or not db_ok) else "ok"

    payload = {
        "status": overall,
        "uptime": _process_uptime_seconds(),
        "db": {"ok": db_ok, "latency_ms": db_latency_ms},
        "mailer": {"breaker_open": breaker_open},
    }
    if simulated:
        payload["simulated_degraded"] = {
            "active": True,
            "seconds_left": max(0.0, round(_FORCE_DEGRADED_UNTIL_TS - now, 1)) if _FORCE_DEGRADED_UNTIL_TS > now else 0.0,
            "reason": _FORCE_DEGRADED_REASON or ("query-param force_degraded=1" if force_degraded else "admin-simulated"),
        }
    return payload


# ---------------------------------------------------------------------------
# Self-pinging keep-alive so the preview environment never sleeps.
# Fires an HTTPS GET at ${PREVIEW_URL}/api/health every 5 minutes. Falls back
# to http://localhost:${PORT}/api/health when PREVIEW_URL isn't configured.
# ---------------------------------------------------------------------------
_PROCESS_START_TS = time.monotonic()


def _process_uptime_seconds() -> float:
    return round(time.monotonic() - _PROCESS_START_TS, 3)


async def _self_ping_tick(state: dict) -> dict:
    """One iteration of the self-ping cadence.

    ``state`` carries ``consecutive_degraded`` (int) and ``alert_state``
    ("healthy" | "alerting") across ticks. Split out from
    ``_self_ping_loop`` so unit tests can drive individual heartbeats
    without spinning up an asyncio task or waiting minutes.
    """
    import httpx  # local import so unit tests can patch it if needed.

    preview_url = (os.environ.get("PREVIEW_URL") or "").rstrip("/")
    if not preview_url:
        port = os.environ.get("PORT") or "8001"
        preview_url = f"http://localhost:{port}"
    target = f"{preview_url}/api/health"

    current_status = "unknown"
    data: dict = {}
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            r = await client.get(target)
        body = ""
        try:
            data = r.json() or {}
            current_status = data.get("status", "unknown")
            body = (
                f" db_ok={data.get('db',{}).get('ok')} "
                f"db_ms={data.get('db',{}).get('latency_ms')} "
                f"breaker_open={data.get('mailer',{}).get('breaker_open')}"
            )
        except Exception:  # noqa: BLE001
            pass
        logger.info(
            f"[self-ping] Heartbeat ping status: {r.status_code} → {target}{body}"
        )
        if r.status_code >= 500:
            current_status = "degraded"
    except Exception as e:  # noqa: BLE001 — best-effort keep-alive
        logger.error(f"[self-ping] Heartbeat request failed for {target}: {e}")
        current_status = "degraded"
        data = {"error": str(e)}

    fired: Optional[str] = None
    if current_status == "degraded":
        state["consecutive_degraded"] = state.get("consecutive_degraded", 0) + 1
        if state["consecutive_degraded"] >= 2 and state.get("alert_state") == "healthy":
            if await _post_health_alert(target, data, kind="degraded"):
                state["alert_state"] = "alerting"
                fired = "degraded"
    else:
        if state.get("alert_state") == "alerting":
            await _post_health_alert(target, data, kind="recovered")
            state["alert_state"] = "healthy"
            fired = "recovered"
        state["consecutive_degraded"] = 0

    return {"status": current_status, "target": target, "fired": fired, "data": data}


async def _self_ping_loop():
    """Every 5 min, GET ${PREVIEW_URL}/api/health so the pod stays warm.

    See ``_self_ping_tick`` for the per-iteration logic (extracted so
    tests can call it directly without waiting on ``asyncio.sleep``).
    """
    interval = int(os.environ.get("SELF_PING_INTERVAL_SEC", str(5 * 60)))
    # Wait a bit before first ping so the app has finished starting.
    await asyncio.sleep(15)

    state = {"consecutive_degraded": 0, "alert_state": "healthy"}
    while True:
        try:
            await _self_ping_tick(state)
        except Exception as e:  # noqa: BLE001 — never let the loop die
            logger.error(f"[self-ping] loop iteration crashed: {e}")
        await asyncio.sleep(max(60, interval))


async def _post_health_alert(target: str, data: dict, *, kind: str) -> bool:
    """POST a Slack/Discord-flavoured alert message.

    Returns True on any 2xx response; False when the webhook is unset or the
    POST failed. Autodetects Slack (``hooks.slack.com``) vs Discord
    (``discord.com/api/webhooks``) by hostname and shapes the payload
    accordingly.
    """
    webhook = (os.environ.get("HEALTH_ALERT_WEBHOOK_URL") or "").strip()
    if not webhook:
        logger.warning(
            "[self-ping] status=degraded twice in a row but "
            "HEALTH_ALERT_WEBHOOK_URL is unset — not paging ops"
        )
        return False

    db_ok = data.get("db", {}).get("ok")
    db_ms = data.get("db", {}).get("latency_ms")
    breaker = data.get("mailer", {}).get("breaker_open")
    err = data.get("error")
    if kind == "degraded":
        title = f":rotating_light: BlueOcean heartbeat DEGRADED (2× in a row) — {target}"
    else:
        title = f":white_check_mark: BlueOcean heartbeat RECOVERED — {target}"
    lines = [
        title,
        f"• db.ok={db_ok}",
        f"• db.latency_ms={db_ms}",
        f"• mailer.breaker_open={breaker}",
    ]
    if err:
        lines.append(f"• error={err}")
    text = "\n".join(lines)

    try:
        import httpx
        if "discord.com" in webhook:
            payload = {"content": text[:1900]}
        else:  # Slack (or Slack-compatible)
            payload = {"text": text}
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(webhook, json=payload)
        ok = 200 <= r.status_code < 300
        logger.info(f"[self-ping] alert kind={kind} → webhook status={r.status_code}")
        return ok
    except Exception as e:  # noqa: BLE001
        logger.error(f"[self-ping] alert webhook POST failed: {e}")
        return False


# =========================
# Models
# =========================
class UserBase(BaseModel):
    email: str  # Changed from EmailStr to allow .local domains in development
    username: str

class UserCreate(UserBase):
    password: str
    referral_code: Optional[str] = None  # code of the referrer

class UserLogin(BaseModel):
    email: str  # Changed from EmailStr to allow .local domains in development
    password: str

class User(UserBase):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    role: Literal["user", "admin"] = "user"
    avatar: Optional[str] = None
    bio: Optional[str] = ""
    rating: float = 5.0
    sales_count: int = 0
    is_active: bool = True
    referral_code: str = Field(default_factory=lambda: uuid.uuid4().hex[:8].upper())
    referred_by: Optional[str] = None  # user_id who referred this user
    wallet_balance: float = 0.0
    wallet_frozen_balance: float = 0.0  # earnings held until delivery is confirmed
    store_id: Optional[str] = None
    # Phase 1: Trust & Payments
    email_verified: bool = False
    email_verified_at: Optional[datetime] = None
    phone: Optional[str] = None
    phone_verified: bool = False
    phone_verified_at: Optional[datetime] = None
    seller_status: Literal["none", "pending", "approved", "rejected"] = "none"
    stripe_account_id: Optional[str] = None
    stripe_status: Literal["none", "pending", "active", "restricted"] = "none"
    weekly_earnings_goal: float = 0.0
    weekly_digest_opt_in: bool = True
    # Per-kind email preferences (true = send, false = opt-out).
    email_prefs: dict = Field(default_factory=lambda: {
        "order": True, "sale": True, "wallet": True,
        "payout": True, "dispute": True, "system": True,
    })
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class UserPublic(BaseModel):
    id: str
    email: str
    username: str
    role: str
    avatar: Optional[str] = None
    bio: Optional[str] = ""
    rating: float = 5.0
    sales_count: int = 0
    is_active: bool = True
    referral_code: Optional[str] = None
    referred_by: Optional[str] = None
    wallet_balance: float = 0.0
    wallet_frozen_balance: float = 0.0
    store_id: Optional[str] = None
    email_verified: bool = False
    resell_markup_override: Optional[float] = None
    created_at: Optional[datetime] = None
    # Security — soft-lock state (surfaced to admins for one-click unlock)
    failed_login_attempts: int = 0
    locked_until: Optional[datetime] = None
    # Seller badge & resell caps ----------------------------------------
    # `badge` is auto-derived from sales_count + rating unless the admin
    # sets `resell_markup_override` — a hard cap (%) that bypasses the tier table.
    resell_markup_override: Optional[float] = None
    email_verified_at: Optional[datetime] = None
    phone: Optional[str] = None
    phone_verified: bool = False
    phone_verified_at: Optional[datetime] = None
    seller_status: str = "none"
    stripe_account_id: Optional[str] = None
    stripe_status: str = "none"
    weekly_earnings_goal: float = 0.0
    email_prefs: Optional[dict] = None
    # When True, the next successful login must be immediately followed by a
    # password change. Set by admin-side resets and by the "legacy user"
    # migration so users who forgot their credentials are forced to pick a
    # fresh one on first sign-in.
    must_change_password: bool = False
    created_at: datetime

class AuthResponse(BaseModel):
    token: str
    user: UserPublic
    # Frontend uses this to route the user through /change-password before
    # they can access the rest of the app.
    password_change_required: bool = False

class Category(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    slug: str
    icon: str = "package"
    order: int = 0
    parent_id: Optional[str] = None

class CategoryCreate(BaseModel):
    name: str
    slug: str
    icon: str = "package"
    order: int = 0
    parent_id: Optional[str] = None

class Listing(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    seller_id: str
    seller_name: str
    # ISO 3166-1 alpha-2 (e.g. "US", "JP"). Rendered as a flag next to the
    # seller name on product tiles / storefront so buyers see origin instantly.
    seller_country: Optional[str] = None
    title: str
    description: str
    price: float
    original_price: Optional[float] = None
    category_id: str
    category_name: str
    # Additional category IDs a product also belongs to (multi-category tag).
    # `category_id` remains the primary/canonical bucket; `secondary_categories`
    # broadens visibility (e.g. an "electronics for women" laptop lives in
    # Electronics as primary + Women as secondary).
    secondary_categories: List[str] = Field(default_factory=list)
    condition: Literal["new", "like_new", "good", "fair", "poor"] = "good"
    brand: Optional[str] = ""
    size: Optional[str] = ""
    color: Optional[str] = ""
    images: List[str] = []
    shipping_paid_by: Literal["seller", "buyer"] = "seller"
    shipping_method: str = "Standard"
    status: Literal["active", "sold", "reserved", "removed", "suspended", "draft"] = "active"
    likes_count: int = 0
    views_count: int = 0
    featured: bool = False
    store_id: Optional[str] = None
    imported_from_id: Optional[str] = None  # original listing id if this is a dropship import
    base_price: Optional[float] = None  # original seller's price when imported
    # Flash deals (rotated daily)
    is_flash_deal: bool = False
    flash_deal_ends_at: Optional[datetime] = None
    flash_deal_discount_pct: Optional[int] = None
    # Wishlist / price drop
    price_drop_at: Optional[datetime] = None
    previous_price: Optional[float] = None
    # Scraper import tracking (Zyte pipeline dedupe key)
    source_url: Optional[str] = None
    # Best-sellers rotation — set when a weekly re-check detects supplier
    # price drift or the source disappearing.
    demoted: bool = False
    demoted_reason: Optional[str] = None  # 'supplier_price_shift' | 'supplier_gone'
    last_supplier_check_at: Optional[datetime] = None
    supplier_last_price: Optional[float] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ListingCreate(BaseModel):
    title: str
    description: str
    price: float
    original_price: Optional[float] = None
    category_id: str
    condition: str = "good"
    brand: Optional[str] = ""
    size: Optional[str] = ""
    color: Optional[str] = ""
    images: List[str] = []
    shipping_paid_by: str = "seller"
    shipping_method: str = "Standard"

class ListingUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    category_id: Optional[str] = None
    condition: Optional[str] = None
    images: Optional[List[str]] = None
    status: Optional[str] = None
    featured: Optional[bool] = None

class Favorite(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    listing_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class CartItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    listing_id: str
    added_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class Order(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    buyer_id: str
    buyer_name: str
    seller_id: str
    seller_name: str
    listing_id: str
    listing_title: str
    listing_image: Optional[str] = None
    quantity: int = 1
    unit_price: Optional[float] = None
    bulk_discount_pct: float = 0.0
    bulk_discount_amount: float = 0.0
    amount: float
    shipping_fee: float = 0.0
    status: Literal["pending", "paid", "shipped", "delivered", "cancelled"] = "paid"
    shipping_address: dict = {}
    # Commission breakdown
    platform_fee: float = 0.0
    seller_earnings: float = 0.0
    affiliate_link_id: Optional[str] = None
    affiliate_user_id: Optional[str] = None
    affiliate_earnings: float = 0.0
    referral_payouts: List[dict] = []  # [{level, user_id, amount}]
    dropship_source_seller_id: Optional[str] = None
    dropship_source_earnings: float = 0.0
    # Reseller wholesale-debit fulfillment (Feb 2026):
    reseller_wholesale_cost: float = 0.0
    reseller_paid_wholesale: bool = False
    reinvest_funded_amount: float = 0.0  # portion of wholesale funded via wallet Reinvest advance
    reinvest_funded_at: Optional[datetime] = None
    # Seller-pickup flow (Feb 2026): after a buyer places an order, the
    # seller must explicitly "pick and deliver" (which debits the wholesale
    # cost from their wallet) before fulfillment can start. Auto-cancels
    # after `pickup_deadline` if the seller never accepts.
    fulfillment_status: Literal[
        "pending_pickup", "picking", "picked", "shipped", "delivered",
        "auto_cancelled", "cancelled"
    ] = "pending_pickup"
    pickup_deadline: Optional[datetime] = None
    picked_up_at: Optional[datetime] = None
    paid_from_available: float = 0.0    # portion of wholesale paid from user's available balance
    paid_from_frozen: float = 0.0       # portion paid from frozen balance (max 75% of frozen usable)
    auto_cancelled_at: Optional[datetime] = None
    # Storefront Push attribution — set when the buyer arrived via a shared link.
    share_ref: Optional[str] = None
    push_reward_amount: float = 0.0
    # Payment method selected at checkout: card | wallet | crypto | bank
    payment_method: Optional[str] = None
    payment_currency: Optional[str] = None  # e.g. "ETH" / "SOL" for crypto, or manual method id for bank
    # Phase 2: Shipping (MOCKED EasyPost/Shippo)
    tracking_number: Optional[str] = None
    carrier: Optional[str] = None
    label_url: Optional[str] = None
    shipping_status: Optional[str] = None  # label_created, in_transit, delivered
    estimated_delivery: Optional[str] = None
    estimated_delivery_at: Optional[datetime] = None  # projected arrival date (order.created_at + delivery_days_estimate)
    shipping_delivered_at: Optional[datetime] = None  # set by shipping progression loop when carrier reports delivered — gates auto-confirm
    delivery_confirmed_at: Optional[datetime] = None  # set when buyer or auto-release marks delivery
    auto_confirmed: bool = False  # true when funds were released by auto-confirm loop (buyer didn't confirm manually)
    funds_released: bool = False  # true once seller/dropship-source frozen earnings are released to available balance
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class OrderCreate(BaseModel):
    listing_id: str
    quantity: int = 1
    shipping_address: dict = {}
    affiliate_code: Optional[str] = None
    share_ref: Optional[str] = None  # e.g. "push" when the buyer arrived from a Storefront Push share link
    payment_method: Optional[Literal["wallet"]] = "wallet"  # wallet-only: top up via /wallet first
    payment_currency: Optional[str] = None  # kept for backwards-compat (unused for wallet orders)


# =========================
# Phase 1: Stores / Affiliate / Wallet / Referral / Settings
# =========================
class Store(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    owner_id: str
    name: str
    slug: str
    tagline: Optional[str] = ""
    bio: Optional[str] = ""
    logo: Optional[str] = None
    banner: Optional[str] = None
    country: Optional[str] = None  # ISO 3166-1 alpha-2 (e.g. "US", "NG", "GB")
    contact_email: Optional[str] = None
    website: Optional[str] = None
    verified_tier: Literal["none", "bronze", "silver", "gold"] = "none"
    followers_count: int = 0
    total_sales: int = 0
    is_active: bool = True
    featured_rank: int = 9999
    category_ids: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class StoreCreate(BaseModel):
    name: str
    slug: str
    tagline: Optional[str] = ""
    bio: Optional[str] = ""
    logo: Optional[str] = None
    banner: Optional[str] = None
    country: Optional[str] = None
    contact_email: Optional[str] = None
    website: Optional[str] = None
    category_ids: Optional[List[str]] = None

class StoreUpdate(BaseModel):
    name: Optional[str] = None
    tagline: Optional[str] = None
    bio: Optional[str] = None
    logo: Optional[str] = None
    banner: Optional[str] = None
    country: Optional[str] = None
    contact_email: Optional[str] = None
    website: Optional[str] = None
    category_ids: Optional[List[str]] = None

# Affiliate models moved to `models/affiliate.py`
from models.affiliate import AffiliateLink, AffiliateLinkCreate  # noqa: E402

# Wallet/withdrawal Pydantic models moved to `models/wallet.py` so extracted
# routers can pull them without depending on this whole module. Re-imported
# below to preserve the (thousands of) legacy references in server.py.
from models.wallet import (  # noqa: E402
    DepositRequest as _DepositRequest,
    DepositRequestCreate as _DepositRequestCreate,
    WalletTransaction,
    WithdrawalRequest,
    WithdrawalRequestCreate,
)

class Settings(BaseModel):
    id: str = "global"
    platform_fee_pct: float = 10.0
    affiliate_commission_pct: float = 5.0
    referral_l1_pct: float = 3.0  # % of platform fee to referrer L1
    referral_l2_pct: float = 1.0
    referral_l3_pct: float = 0.5
    dropship_max_markup_pct: float = 100.0
    min_withdrawal: float = 10.0
    signup_bonus: float = 0.0
    affiliate_mode: Literal["auto", "semi", "manual"] = "auto"
    store_mode: Literal["auto", "semi", "manual"] = "auto"
    withdrawal_mode: Literal["auto", "semi", "manual"] = "manual"
    listing_mode: Literal["auto", "semi", "manual"] = "auto"
    semi_threshold: float = 100.0  # for semi-auto approvals under this amount
    referral_levels_enabled: bool = True
    dispute_auto_refund_threshold: float = 0.0  # auto-refund disputes below this amount ($). 0 disables.
    dispute_auto_refund_excluded_reasons: List[str] = Field(default_factory=lambda: ["counterfeit"])
    delivery_days_estimate: int = 7  # admin-set global ETA (days) shown to buyers and used to project delivery.
    delivery_auto_release_days: int = 14  # if buyer doesn't confirm, auto-release frozen funds after N days from order.
    # Resell markup caps (%) per seller badge. Admin-tunable.
    resell_markup_caps: dict = Field(default_factory=lambda: {"new": 25.0, "bronze": 50.0, "silver": 80.0, "gold": 120.0})
    # Wholesale discount (%) resellers get off the source retail price, per tier.
    # e.g. gold=15 means gold resellers buy inventory at 85% of retail. Admin-tunable.
    resell_wholesale_discounts: dict = Field(default_factory=lambda: {"new": 0.0, "bronze": 5.0, "silver": 10.0, "gold": 15.0})
    # Storefront Push reward: fixed bonus (USD) credited to the seller when their share link
    # converts to their first-ever share-attributed sale. Set to 0 to disable.
    push_reward_amount: float = 2.0
    # Bulk-buyer reward tiers. Each item: {min_qty, discount_pct}. The highest
    # tier whose min_qty is satisfied wins. Empty list disables bulk discounts.
    bulk_discount_tiers: List[dict] = Field(default_factory=lambda: [
        {"min_qty": 5, "discount_pct": 5.0},
        {"min_qty": 10, "discount_pct": 10.0},
    ])
    # Crypto deposit addresses shown to users on the Wallet page. Empty string = hidden.
    crypto_addresses: dict = Field(default_factory=lambda: {"BTC": "", "ETH": "", "USDC": "", "USDT": ""})
    # Multi-asset / multi-network crypto deposit config. Each item:
    # {id, symbol, network, address, active}
    # symbol: BTC|ETH|SOL|BNB|USDC|USDT|MATIC|... · network: Bitcoin|Ethereum|Solana|BEP-20|Polygon|...
    crypto_assets: List[dict] = Field(default_factory=lambda: [
        {"id": "btc_bitcoin",   "symbol": "BTC",   "network": "Bitcoin",  "address": "", "active": True},
        {"id": "eth_ethereum",  "symbol": "ETH",   "network": "Ethereum", "address": "", "active": True},
        {"id": "sol_solana",    "symbol": "SOL",   "network": "Solana",   "address": "", "active": True},
        {"id": "bnb_bep20",     "symbol": "BNB",   "network": "BEP-20",   "address": "", "active": True},
        {"id": "usdc_ethereum", "symbol": "USDC",  "network": "Ethereum", "address": "", "active": True},
        {"id": "usdc_solana",   "symbol": "USDC",  "network": "Solana",   "address": "", "active": True},
        {"id": "usdc_polygon",  "symbol": "USDC",  "network": "Polygon",  "address": "", "active": True},
        {"id": "usdt_ethereum", "symbol": "USDT",  "network": "Ethereum", "address": "", "active": True},
        {"id": "usdt_bep20",    "symbol": "USDT",  "network": "BEP-20",   "address": "", "active": True},
        {"id": "matic_polygon", "symbol": "MATIC", "network": "Polygon",  "address": "", "active": True},
    ])
    # Admin-managed manual payment methods (bank transfer, mobile money, PayPal link, etc.)
    # Each item: {id, name, instructions, icon, active}
    manual_payment_methods: List[dict] = Field(default_factory=list)
    # Invite-only signup — when True, /auth/register requires a valid invitation
    # (referral) code that matches an existing user's `referral_code`.
    invite_only_signup: bool = False
    # Legacy-account "any password" bypass — when True, users flagged
    # `must_change_password=True` can log in with any non-empty password and
    # are gated to /auth/change-password only. Turn OFF once the legacy fleet
    # has migrated to fresh credentials.
    legacy_bypass_enabled: bool = True
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# Deposit models — moved to models/wallet.py (imported above). We keep the
# legacy names bound here so every existing `DepositRequest(...)` /
# `isinstance(x, DepositRequest)` call site keeps working unchanged.
DepositRequest = _DepositRequest
DepositRequestCreate = _DepositRequestCreate


# Message models moved to `models/messages.py`
from models.messages import Message, MessageCreate  # noqa: E402


# Dispute models moved to `models/disputes.py`
from models.disputes import (  # noqa: E402
    Dispute, DisputeCreate, DisputeResolveIn,
    DisputeMessage, DisputeMessageCreate,
    DISPUTE_REASONS, DISPUTE_STATUSES,
)


# =========================
# Phase 2: Reviews & Notifications
# =========================
# Review + Notification models moved to `models/`
from models.reviews import Review, ReviewCreate  # noqa: E402
from models.notifications import Notification, NOTIFICATION_TYPES  # noqa: E402


# =========================
# Phase 1: Trust & Payments (Mocked External Services)
# =========================
class VerificationToken(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    kind: Literal["email", "phone"]
    token: str  # magic link token or 6-digit OTP
    target: str  # email address or phone number
    used: bool = False
    attempts: int = 0
    expires_at: datetime
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class SellerApplication(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    user_email: str
    user_username: str
    legal_name: str
    business_name: Optional[str] = ""
    business_type: Literal["individual", "sole_prop", "llc", "corp"] = "individual"
    tax_id: str = ""  # last-4 stored for mock; real would be tokenized
    country: str = "US"
    address_line1: str = ""
    address_line2: Optional[str] = ""
    city: str = ""
    state: str = ""
    postal_code: str = ""
    phone: str = ""
    payout_method: Literal["crypto", "bank_transfer", "card", "paypal", "crypto_alt", "stripe_connect"] = "crypto"
    id_document_note: Optional[str] = ""  # placeholder; real flow would upload
    id_document_file_id: Optional[str] = None  # points to /api/files/{id}
    status: Literal["pending", "approved", "rejected"] = "pending"
    admin_notes: Optional[str] = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    reviewed_at: Optional[datetime] = None
    reviewed_by: Optional[str] = None

class SellerApplicationCreate(BaseModel):
    legal_name: str
    business_name: Optional[str] = ""
    business_type: Literal["individual", "sole_prop", "llc", "corp"] = "individual"
    tax_id: str = ""
    country: str = "US"
    address_line1: str = ""
    address_line2: Optional[str] = ""
    city: str = ""
    state: str = ""
    postal_code: str = ""
    phone: str = ""
    payout_method: Literal["crypto", "bank_transfer", "card", "paypal", "crypto_alt"] = "crypto"
    id_document_note: Optional[str] = ""
    id_document_file_id: Optional[str] = None

class EmailSendRequest(BaseModel):
    email: Optional[str] = None  # optional override; defaults to user's account email

class PhoneSendRequest(BaseModel):
    phone: str

class PhoneConfirmRequest(BaseModel):
    phone: str
    code: str

class EmailConfirmRequest(BaseModel):
    token: str


# =========================
# Helpers
# =========================
def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    if not hashed:
        return False
    try:
        return pwd_context.verify(plain, hashed)
    except Exception:
        # Unknown / malformed hash -> treat as auth failure, never 500
        return False

def create_token(user_id: str, role: str) -> str:
    payload = {
        "sub": user_id,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRE_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)

# Endpoints a `must_change_password` user is still allowed to hit while the
# flag is set. Everything else must go through the change-password flow first.
_PWD_CHANGE_ALLOWED_PATHS = frozenset({
    "/api/auth/change-password",
    "/api/auth/me",
    "/api/auth/logout",
    "/api/health",
})


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    # Dual-mode auth: accept EITHER the Authorization: Bearer header (legacy
    # localStorage flow) OR the HTTPOnly `bo_token` cookie (issued on
    # /auth/login). Falling back to the cookie means a session survives
    # frontend cache clears / storage wipes / accidental log-outs, which
    # otherwise surfaced as a scary "Not authenticated" toast on every
    # authenticated action (e.g. clicking "Send verification code" on
    # /apply-seller after localStorage had been cleared).
    token = None
    if credentials and credentials.credentials:
        token = credentials.credentials
    else:
        token = request.cookies.get("bo_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        user_id = payload.get("sub")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="Account disabled")
    # Server-side enforcement of the "must change password" flag. When set,
    # only a tiny whitelist of endpoints is reachable so a malicious client
    # can't bypass the frontend redirect and use its JWT normally.
    if user.get("must_change_password"):
        path = request.url.path.rstrip("/") or "/"
        if path not in _PWD_CHANGE_ALLOWED_PATHS:
            raise HTTPException(
                status_code=403,
                detail={
                    "message": "Password change required before continuing.",
                    "password_change_required": True,
                },
            )
    return user


async def get_current_user_optional(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> Optional[dict]:
    token = None
    if credentials and credentials.credentials:
        token = credentials.credentials
    else:
        token = request.cookies.get("bo_token")
    if not token:
        return None
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        user = await db.users.find_one({"id": payload.get("sub")}, {"_id": 0, "password_hash": 0})
        return user
    except Exception:
        return None

async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user

def to_public_user(user: dict) -> dict:
    return {k: v for k, v in user.items() if k not in ("password_hash", "_id")}


# =========================
# Helpers: Settings, Wallet, Commissions
# =========================
async def get_settings() -> dict:
    doc = await db.settings.find_one({"id": "global"}, {"_id": 0})
    defaults = Settings().model_dump()
    if not doc:
        await db.settings.insert_one({**defaults})
        return defaults
    # Merge defaults for any newly introduced fields so callers never see None
    return {**defaults, **doc}

from services import ledger

async def credit_wallet(
    user_id: str,
    amount: float,
    tx_type: str,
    description: str,
    related_id: Optional[str] = None,
    frozen: bool = False,
):
    """Credit or debit a user's wallet. Thin wrapper around the unified
    ledger service so every existing call site keeps working while new
    code uses `services.ledger.apply_entry()` directly."""
    if amount == 0:
        return
    try:
        await ledger.apply_entry(
            db,
            user_id=user_id,
            delta=float(amount),
            tx_type=tx_type,  # type: ignore[arg-type]
            description=description,
            related_id=related_id,
            frozen=frozen,
        )
    except ledger.LedgerError as e:
        logger.error(f"credit_wallet: {e}")


async def release_frozen(user_id: str, amount: float, description: str, related_id: Optional[str] = None, tx_type: str = "sale_released"):
    """Move `amount` from user's frozen balance into their available balance and log a tx.
    Delegates to the unified ledger service."""
    try:
        await ledger.release_frozen(
            db,
            user_id=user_id,
            amount=amount,
            order_id=related_id,
            description=description,
        )
    except ledger.LedgerError as e:
        logger.error(f"release_frozen: {e}")

async def get_referral_chain(user_id: str, max_levels: int = 3) -> List[str]:
    """Return referrer chain for a user: [L1, L2, L3, ...] up to max_levels."""
    chain: List[str] = []
    current_id = user_id
    for _ in range(max_levels):
        u = await db.users.find_one({"id": current_id}, {"_id": 0, "referred_by": 1})
        if not u or not u.get("referred_by"):
            break
        chain.append(u["referred_by"])
        current_id = u["referred_by"]
    return chain

EMAIL_KINDS = {"order", "sale", "wallet", "payout", "dispute", "system"}


async def notify(user_id: str, ntype: str, title: str, body: str = "", link: Optional[str] = None):
    if not user_id:
        return
    n = Notification(user_id=user_id, type=ntype, title=title, body=body, link=link)
    await db.notifications.insert_one(n.model_dump())

    # Also dispatch an email for account-changing events, respecting the
    # user's per-kind email preferences.
    if ntype not in EMAIL_KINDS:
        return
    try:
        user = await db.users.find_one(
            {"id": user_id},
            {"_id": 0, "email": 1, "username": 1, "email_prefs": 1},
        )
        if not user or not user.get("email"):
            return
        prefs = user.get("email_prefs") or {}
        if prefs.get(ntype) is False:
            return  # user opted out of this category
        from services import mailer
        from services.email_templates import _shell, FRONTEND
        cta_url = f"{FRONTEND}{link}" if link and link.startswith("/") else (link or FRONTEND)
        subject = f"{title}"
        html = _shell(title, f"<p>Hi {user.get('username','')},</p><p>{body}</p>", cta_url, "Open Ocean")
        result = await mailer.send_email(to=user["email"], subject=subject, html=html, tags=[f"notify:{ntype}"])
        await db.email_log.insert_one({
            "kind": ntype, "to": user["email"], "user_id": user_id,
            "subject": subject, "provider": result.get("provider"),
            "ok": result.get("ok"), "error": result.get("error"),
            "sent_at": datetime.now(timezone.utc),
        })
    except Exception as e:
        logger.error(f"notify email failed for {user_id} / {ntype}: {e}")




# =========================
# Categories
# =========================
@api_router.get("/categories", response_model=List[Category])
async def list_categories():
    docs = await db.categories.find({}, {"_id": 0}).sort("order", 1).to_list(500)
    return [Category(**d) for d in docs]

@api_router.post("/categories", response_model=Category)
async def create_category(payload: CategoryCreate, _admin: dict = Depends(require_admin)):
    cat = Category(**payload.model_dump())
    await db.categories.insert_one(cat.model_dump())
    return cat

@api_router.put("/categories/{cat_id}", response_model=Category)
async def update_category(cat_id: str, payload: CategoryCreate, _admin: dict = Depends(require_admin)):
    await db.categories.update_one({"id": cat_id}, {"$set": payload.model_dump()})
    doc = await db.categories.find_one({"id": cat_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Category not found")
    return Category(**doc)

@api_router.delete("/categories/{cat_id}")
async def delete_category(cat_id: str, _admin: dict = Depends(require_admin)):
    await db.categories.delete_one({"id": cat_id})
    return {"ok": True}


# =========================
# Listings
# =========================
@api_router.get("/listings", response_model=List[Listing])
async def list_listings(
    q: Optional[str] = None,
    category_id: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    condition: Optional[str] = None,
    brand: Optional[str] = None,
    sort: str = "newest",
    featured: Optional[bool] = None,
    seller_id: Optional[str] = None,
    status_filter: Optional[str] = "active",
    limit: int = 60,
    skip: int = 0,
):
    query = _build_listings_query(
        q=q, category_id=category_id, min_price=min_price, max_price=max_price,
        condition=condition, brand=brand, featured=featured, seller_id=seller_id, status_filter=status_filter,
    )
    sort_map = {
        "newest": [("created_at", -1)],
        "oldest": [("created_at", 1)],
        "price_asc": [("price", 1)],
        "price_desc": [("price", -1)],
        "popular": [("likes_count", -1), ("views_count", -1)],
        "trending": [("views_count", -1), ("likes_count", -1), ("created_at", -1)],
    }
    limit = max(1, min(int(limit), 500))
    skip = max(0, int(skip))
    cursor = db.listings.find(query, {"_id": 0}).sort(sort_map.get(sort, sort_map["newest"])).skip(skip).limit(limit)
    docs = await cursor.to_list(limit)
    return [Listing(**d) for d in docs]




def _build_listings_query(
    q: Optional[str],
    category_id: Optional[str],
    min_price: Optional[float],
    max_price: Optional[float],
    condition: Optional[str],
    featured: Optional[bool],
    seller_id: Optional[str],
    status_filter: Optional[str],
    brand: Optional[str] = None,
) -> dict:
    query: dict = {}
    if status_filter:
        query["status"] = status_filter
    # ZYTE REMOVAL — exclude any listing whose source_url was ingested by the
    # legacy Zyte scraper (books.toscrape.com, generic ebay/shopify sources, etc.).
    # Only Amazon-derived (or source-less demo) listings surface on the marketplace.
    # Also exclude testing artefacts via the shared storefront filter — single
    # source of truth for all test-listing exclusions.
    from services.storefront_filter import LISTING_TEST_TITLE_RE, SELLER_TEST_USERNAME_RE
    query["$nor"] = [
        {"source_url": {"$regex": r"toscrape\.com", "$options": "i"}},
        {"source_url": {"$regex": r"scrape\.me", "$options": "i"}},
        {"source_url": {"$regex": r"quotes\.toscrape", "$options": "i"}},
        {"title": {"$regex": LISTING_TEST_TITLE_RE, "$options": "i"}},
        {"seller_name": {"$regex": SELLER_TEST_USERNAME_RE}},
    ]
    and_clauses: list = []
    if q:
        and_clauses.append({
            "$or": [
                {"title": {"$regex": q, "$options": "i"}},
                {"description": {"$regex": q, "$options": "i"}},
                {"brand": {"$regex": q, "$options": "i"}},
            ]
        })
    if category_id:
        and_clauses.append({
            "$or": [
                {"category_id": category_id},
                {"secondary_categories": category_id},
            ]
        })
    if len(and_clauses) == 1:
        # Merge the single $or straight into the query (cleaner explain plans)
        query.update(and_clauses[0])
    elif len(and_clauses) > 1:
        query["$and"] = and_clauses
    if condition:
        query["condition"] = condition
    if brand:
        query["brand"] = brand
    if seller_id:
        query["seller_id"] = seller_id
    if featured is not None:
        query["featured"] = featured
    if min_price is not None or max_price is not None:
        pr: dict = {}
        if min_price is not None:
            pr["$gte"] = min_price
        if max_price is not None:
            pr["$lte"] = max_price
        query["price"] = pr
    return query

@api_router.post("/listings", response_model=Listing)
async def create_listing(payload: ListingCreate, user: dict = Depends(get_current_user)):
    # Gate: only approved sellers (or admins) can create listings
    if user.get("role") != "admin" and user.get("seller_status") != "approved":
        raise HTTPException(403, "Complete seller verification and approval to create listings")
    cat = await db.categories.find_one({"id": payload.category_id}, {"_id": 0})
    if not cat:
        raise HTTPException(400, "Invalid category")
    # Safety net: ensure the seller has a storefront so the listing is instantly added to it.
    store_id = user.get("store_id")
    if not store_id and user.get("role") != "admin":
        s = await ensure_store_for_user(user["id"])
        store_id = s["id"] if s else None
    listing = Listing(
        seller_id=user["id"],
        seller_name=user["username"],
        category_name=cat["name"],
        store_id=store_id,
        **payload.model_dump(),
    )
    await db.listings.insert_one(listing.model_dump())
    await _notify_store_followers(store_id, listing.title, listing.id)
    await schedule_sitemap_ping(changed_listing_id=listing.id)
    return listing

@api_router.put("/listings/{listing_id}", response_model=Listing)
async def update_listing(listing_id: str, payload: ListingUpdate, user: dict = Depends(get_current_user)):
    doc = await db.listings.find_one({"id": listing_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Listing not found")
    if doc["seller_id"] != user["id"] and user["role"] != "admin":
        raise HTTPException(403, "Not allowed")
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if "category_id" in updates:
        cat = await db.categories.find_one({"id": updates["category_id"]}, {"_id": 0})
        if not cat:
            raise HTTPException(400, "Invalid category")
        updates["category_name"] = cat["name"]
    price_drop_pct = 0
    old_price = float(doc.get("price") or 0)
    new_price = float(updates.get("price")) if "price" in updates else old_price
    if old_price and new_price and new_price < old_price:
        price_drop_pct = round((old_price - new_price) / old_price * 100)
    if price_drop_pct >= 5:
        updates["price_drop_at"] = _now_utc()
        updates["previous_price"] = old_price
    if updates:
        await db.listings.update_one({"id": listing_id}, {"$set": updates})
    # Notify every user who has this listing favorited when price drops >=5%
    if price_drop_pct >= 5:
        fav_users = await db.favorites.find(
            {"listing_id": listing_id}, {"_id": 0, "user_id": 1}
        ).to_list(1000)
        for f in fav_users:
            if f["user_id"] == user["id"]:
                continue
            await notify(
                f["user_id"], "system",
                f"Price drop: -{price_drop_pct}% on a favourite",
                f"{doc.get('title','Your favourite')} is now ${new_price:.2f} (was ${old_price:.2f}).",
                f"/listing/{listing_id}",
            )
    doc = await db.listings.find_one({"id": listing_id}, {"_id": 0})
    # Any listing metadata change (price, title, status) can affect search
    # ranking → nudge Google + Bing to re-crawl.
    if updates:
        await schedule_sitemap_ping(changed_listing_id=listing_id)
    return Listing(**doc)

@api_router.delete("/listings/{listing_id}")
async def delete_listing(listing_id: str, user: dict = Depends(get_current_user)):
    doc = await db.listings.find_one({"id": listing_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Listing not found")
    if doc["seller_id"] != user["id"] and user["role"] != "admin":
        raise HTTPException(403, "Not allowed")
    await db.listings.delete_one({"id": listing_id})
    await db.favorites.delete_many({"listing_id": listing_id})
    await db.cart_items.delete_many({"listing_id": listing_id})
    await schedule_sitemap_ping()
    return {"ok": True}




# =========================
# Orders (mock checkout)
# =========================
@api_router.get("/orders", response_model=List[Order])
async def get_orders(user: dict = Depends(get_current_user), role: str = "buyer"):
    key = "seller_id" if role == "seller" else "buyer_id"
    docs = await db.orders.find({key: user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return [Order(**d) for d in docs]

@api_router.post("/orders", response_model=Order)
async def create_order(payload: OrderCreate, user: dict = Depends(get_current_user)):
    listing = await db.listings.find_one({"id": payload.listing_id, "status": "active"}, {"_id": 0})
    if not listing:
        raise HTTPException(404, "Listing not available")
    if listing["seller_id"] == user["id"]:
        raise HTTPException(400, "Cannot buy your own listing")

    quantity = max(1, min(int(payload.quantity or 1), 99))

    settings = await get_settings()
    unit_price = float(listing["price"])
    gross = round(unit_price * quantity, 2)
    # Bulk-buyer reward — auto-applied server-side so it's always correct.
    bulk_tiers = settings.get("bulk_discount_tiers") or [
        {"min_qty": 5, "discount_pct": 5.0},
        {"min_qty": 10, "discount_pct": 10.0},
    ]
    active_tier = max(
        (t for t in bulk_tiers if quantity >= int(t.get("min_qty", 0))),
        key=lambda t: float(t.get("min_qty", 0)), default=None,
    )
    bulk_discount_pct = float(active_tier["discount_pct"]) if active_tier else 0.0
    bulk_discount_amount = round(gross * bulk_discount_pct / 100.0, 2)
    amount = round(gross - bulk_discount_amount, 2)
    # Flat shipping (one shipment covers the whole bulk order).
    shipping_fee = 0.0 if listing.get("shipping_paid_by") == "seller" else 5.99

    # Payment method — Ocean orders are wallet-only. Users top up
    # the wallet via crypto or bank first (see /api/wallet/deposit/pending),
    # then pay from wallet balance here. This keeps the escrow ledger single-
    # source and lets admins gate every real-money inflow via one review queue.
    method = (payload.payment_method or "wallet").strip().lower() or "wallet"
    if method != "wallet":
        raise HTTPException(
            400,
            "Orders are wallet-only. Please top up your wallet via /wallet "
            "(crypto or bank transfer) and then pay from your wallet balance.",
        )
    total_due = round(amount + shipping_fee, 2)
    try:
        await ledger.purchase_debit(
            db,
            user_id=user["id"],
            amount=total_due,
            order_id="pending",  # updated after order id is minted
            description=f"Wallet payment × {quantity}: {listing['title']}",
        )
    except ledger.InsufficientFunds:
        # Re-read the wallet balance so the response reflects the current state.
        fresh = await db.users.find_one({"id": user["id"]}, {"_id": 0, "wallet_balance": 1})
        available = float((fresh or user).get("wallet_balance", 0.0) or 0.0)
        deposit_needed = round(max(0.0, total_due - available), 2)
        raise HTTPException(
            status_code=402,
            detail={
                "error": "insufficient_wallet_balance",
                "message": (
                    f"Wallet balance is ${available:.2f}, but this order needs "
                    f"${total_due:.2f}. Top up ${deposit_needed:.2f} first."
                ),
                "wallet_balance": available,
                "total_due": total_due,
                "deposit_needed": deposit_needed,
                "redirect": "/wallet",
            },
        )

    # Platform fee — scales with the total merchandise amount.
    platform_fee = round(amount * settings["platform_fee_pct"] / 100.0, 2)

    # Affiliate lookup
    affiliate_link = None
    affiliate_user_id = None
    affiliate_earnings = 0.0
    if payload.affiliate_code:
        affiliate_link = await db.affiliate_links.find_one(
            {"code": payload.affiliate_code, "status": "active"}, {"_id": 0}
        )
        if affiliate_link:
            # ensure affiliate is not the buyer
            if affiliate_link["affiliate_user_id"] != user["id"]:
                affiliate_earnings = round(amount * settings["affiliate_commission_pct"] / 100.0, 2)
                affiliate_user_id = affiliate_link["affiliate_user_id"]

    # Dropship / Reseller wholesale flow ---------------------------------
    # NEW (Feb 2026 seller-pickup flow): compute wholesale cost for EVERY
    # listing (not just imported ones) but DO NOT debit it here. The seller
    # must explicitly "Pick and Deliver" — see POST /api/orders/{id}/pickup.
    dropship_source_seller_id = None
    dropship_source_earnings = 0.0
    reseller_wholesale_cost = 0.0
    reseller_paid_wholesale = False  # flipped True by the pickup endpoint

    if listing.get("imported_from_id") and listing.get("base_price"):
        # P2P dropship — Alice reselling Bob's listing.
        original = await db.listings.find_one({"id": listing["imported_from_id"]}, {"_id": 0, "seller_id": 1})
        if original and original.get("seller_id"):
            dropship_source_seller_id = original["seller_id"]
            retail_base = float(listing["base_price"]) * quantity
            reseller_user = await db.users.find_one({"id": listing["seller_id"]}, {"_id": 0})
            if reseller_user:
                badge = compute_seller_badge(reseller_user)
                discounts = settings.get("resell_wholesale_discounts") or {"new": 0.0, "bronze": 5.0, "silver": 10.0, "gold": 15.0}
                discount_pct = float(discounts.get(badge, 0.0))
                reseller_wholesale_cost = round(retail_base * (1 - discount_pct / 100.0), 2)
                dropship_source_earnings = reseller_wholesale_cost
            else:
                dropship_source_earnings = retail_base
                reseller_wholesale_cost = retail_base
    elif listing.get("source_url") or listing.get("imported_from_id"):
        # External-supplier listing (e.g. sourced from an Amazon/Apify catalog
        # product) — try the catalog first, then base_price, then finally
        # fall back to the listing's retail price so the seller ALWAYS pays
        # a real source cost at pickup (never $0.00).
        cat = None
        if listing.get("imported_from_id"):
            cat = await db.products.find_one({"id": listing["imported_from_id"]}, {"_id": 0, "price": 1})
        if not cat and listing.get("source_url"):
            cat = await db.products.find_one({"source_url": listing["source_url"]}, {"_id": 0, "price": 1})
        if cat and cat.get("price"):
            reseller_wholesale_cost = round(float(cat["price"]) * quantity, 2)
        elif listing.get("base_price"):
            reseller_wholesale_cost = round(float(listing["base_price"]) * quantity, 2)
        else:
            # Last-resort fallback — mirror the retail price so seller pays
            # the real source cost. Better UX than presenting a $0 pickup
            # and helps admins spot listings missing base_price data.
            reseller_wholesale_cost = round(float(listing["price"]) * quantity, 2)
    # Pure P2P listings (seller's own inventory, no source_url, no import) →
    # reseller_wholesale_cost stays 0 — seller still has to "pick" but no
    # wallet debit occurs.

    # Seller earnings: retail - fees - source_seller cut (if any).
    seller_earnings = round(amount - platform_fee - affiliate_earnings - dropship_source_earnings, 2)
    if seller_earnings < 0:
        seller_earnings = 0.0

    # Referral chain from the seller side (rewards seller's referrers)
    referral_payouts: List[dict] = []
    if settings.get("referral_levels_enabled", True):
        chain = await get_referral_chain(listing["seller_id"], max_levels=3)
        pcts = [settings["referral_l1_pct"], settings["referral_l2_pct"], settings["referral_l3_pct"]]
        for level, referrer_id in enumerate(chain, start=1):
            pct = pcts[level - 1]
            payout = round(platform_fee * pct / 100.0, 2)
            if payout > 0:
                referral_payouts.append({"level": level, "user_id": referrer_id, "amount": payout})

    order = Order(
        buyer_id=user["id"],
        buyer_name=user["username"],
        seller_id=listing["seller_id"],
        seller_name=listing["seller_name"],
        listing_id=listing["id"],
        listing_title=listing["title"],
        listing_image=listing["images"][0] if listing.get("images") else None,
        quantity=quantity,
        unit_price=unit_price,
        bulk_discount_pct=bulk_discount_pct,
        bulk_discount_amount=bulk_discount_amount,
        amount=amount,
        shipping_fee=shipping_fee,
        shipping_address=payload.shipping_address,
        status="paid",
        platform_fee=platform_fee,
        seller_earnings=seller_earnings,
        affiliate_link_id=affiliate_link["id"] if affiliate_link else None,
        affiliate_user_id=affiliate_user_id,
        affiliate_earnings=affiliate_earnings,
        referral_payouts=referral_payouts,
        dropship_source_seller_id=dropship_source_seller_id,
        dropship_source_earnings=dropship_source_earnings,
        reseller_wholesale_cost=reseller_wholesale_cost,
        reseller_paid_wholesale=reseller_paid_wholesale,
        share_ref=(payload.share_ref or None),
        payment_method=method,
        payment_currency=(payload.payment_currency or None),
        estimated_delivery_at=datetime.now(timezone.utc) + timedelta(days=int(settings.get("delivery_days_estimate", 7))),
        fulfillment_status="pending_pickup",
        pickup_deadline=datetime.now(timezone.utc) + timedelta(hours=int(settings.get("pickup_deadline_hours", 48))),
    )
    await db.orders.insert_one(order.model_dump())
    # Backfill the placeholder `related_id="pending"` on the buyer's purchase
    # debit now that we know the real order id. Without this, the buyer's
    # /api/orders/{id}/wallet-events feed can't find the purchase entry.
    await db.wallet_txs.update_many(
        {"user_id": user["id"], "type": "purchase", "related_id": "pending"},
        {"$set": {"related_id": order.id}},
    )
    await db.listings.update_one({"id": listing["id"]}, {"$set": {"status": "sold"}})
    await db.users.update_one({"id": listing["seller_id"]}, {"$inc": {"sales_count": 1}})
    await db.cart_items.delete_many({"listing_id": listing["id"]})

    # Credit wallets — seller & dropship-source earnings are FROZEN until delivery is confirmed.
    # Affiliate + referral commissions release immediately (they're marketing rewards, not merchandise).
    await credit_wallet(
        listing["seller_id"], seller_earnings, "sale_frozen",
        f"Sale (held until delivery): {listing['title']}", order.id, frozen=True,
    )
    if affiliate_user_id and affiliate_earnings > 0:
        await credit_wallet(affiliate_user_id, affiliate_earnings, "affiliate", f"Affiliate commission: {listing['title']}", order.id)
        await db.affiliate_links.update_one(
            {"id": affiliate_link["id"]},
            {"$inc": {"conversions": 1, "earnings": affiliate_earnings}},
        )
    if dropship_source_seller_id and dropship_source_earnings > 0:
        await credit_wallet(
            dropship_source_seller_id, dropship_source_earnings, "dropship_frozen",
            f"Dropship sale (held until delivery): {listing['title']}", order.id, frozen=True,
        )
    # (Wholesale debit was already recorded via ledger.apply_entry above —
    # do NOT insert a second wallet_txs row here or reconcile will see a
    # phantom 2× drift.)
    for rp in referral_payouts:
        await credit_wallet(rp["user_id"], rp["amount"], "referral", f"Referral L{rp['level']} bonus", order.id)

    # Update store total_sales
    if listing.get("store_id"):
        await db.stores.update_one({"id": listing["store_id"]}, {"$inc": {"total_sales": 1}})

    # Notifications
    eta_days = int(settings.get("delivery_days_estimate", 7))
    pickup_hours = int(settings.get("pickup_deadline_hours", 48))
    if reseller_wholesale_cost > 0:
        seller_headline = f"New order — Pick & Deliver ${reseller_wholesale_cost:.2f}"
        seller_body = (
            f"You have {pickup_hours}h to accept and pay the source cost "
            f"(${reseller_wholesale_cost:.2f}). Your profit: ${max(0.0, seller_earnings):.2f}."
        )
    else:
        seller_headline = f"New order — please pick and deliver"
        seller_body = f"{listing['title']}. Accept within {pickup_hours}h to keep the sale."
    await notify(listing["seller_id"], "sale", seller_headline, seller_body,
                 f"/profile?tab=sales&pickup={order.id}")
    # Fire the initial pickup email (fire-and-forget so checkout stays fast).
    try:
        asyncio.create_task(_send_pickup_email(
            listing["seller_id"], order.id, listing["title"],
            reseller_wholesale_cost, max(0.0, seller_earnings), pickup_hours, kind="new",
        ))
    except Exception as e:
        logger.warning(f"pickup email schedule failed for order {order.id}: {e}")
    await notify(user["id"], "order", f"Order placed: {listing['title']}",
                 f"You paid ${amount + shipping_fee:.2f} · arrives in ~{eta_days} days",
                 f"/profile?tab=orders")
    if affiliate_user_id:
        await notify(affiliate_user_id, "payout", f"Affiliate commission earned", f"+${affiliate_earnings:.2f} from your link", "/affiliate")
    if dropship_source_seller_id:
        await notify(dropship_source_seller_id, "sale",
                     f"Dropship sale: {listing['title']}",
                     f"Earnings ${dropship_source_earnings:.2f} are held until delivery is confirmed.", None)

    # Storefront Push reward — first share-attributed sale ever for this seller earns a small bonus.
    if payload.share_ref == "push" and seller_earnings > 0:
        bonus = float(settings.get("push_reward_amount", 2.0) or 0.0)
        if bonus > 0:
            already = await db.wallet_txs.find_one(
                {"user_id": listing["seller_id"], "type": "bonus", "description": {"$regex": "^Storefront Push"}},
                {"_id": 0, "id": 1},
            )
            if not already:
                await credit_wallet(
                    listing["seller_id"], bonus, "bonus",
                    f"Storefront Push reward — first share-attributed sale: {listing['title']}",
                    order.id,
                )
                order.push_reward_amount = bonus
                await db.orders.update_one({"id": order.id}, {"$set": {"push_reward_amount": bonus}})
                await notify(listing["seller_id"], "payout",
                             f"Storefront Push reward: +${bonus:.2f}",
                             "Your shared link brought in your first sale — bonus credited to your wallet 🎉",
                             "/wallet")

    return order


@api_router.post("/orders/{order_id}/nudge-buyer")
async def nudge_buyer_confirm(order_id: str, user: dict = Depends(get_current_user)):
    """Seller-triggered nudge — sends the buyer an in-app + email reminder to
    confirm delivery so escrow funds unlock. Rate-limited to once every 24h
    per order to prevent spam. Returns {ok, next_available_at}."""
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(404, "Order not found")
    if order.get("seller_id") != user["id"] and user.get("role") != "admin":
        raise HTTPException(403, "Only the seller or an admin can nudge the buyer")
    if order.get("funds_released"):
        raise HTTPException(400, "Funds already released")

    now = datetime.now(timezone.utc)
    last_nudge = order.get("last_nudge_at")
    if isinstance(last_nudge, str):
        try:
            last_nudge = datetime.fromisoformat(last_nudge.replace("Z", "+00:00"))
        except Exception:
            last_nudge = None
    if last_nudge and last_nudge.tzinfo is None:
        last_nudge = last_nudge.replace(tzinfo=timezone.utc)
    if last_nudge and (now - last_nudge) < timedelta(hours=24):
        wait_h = round(24 - (now - last_nudge).total_seconds() / 3600, 1)
        raise HTTPException(429, f"Already nudged recently. Try again in {wait_h}h.")

    await db.orders.update_one(
        {"id": order_id},
        {"$set": {"last_nudge_at": now}, "$inc": {"nudge_count": 1}},
    )
    title = f"Please confirm delivery: {order.get('listing_title','your order')}"
    body = (
        f"Your seller sent a friendly reminder to confirm delivery for order "
        f"#{order_id[:8]}. Confirming unlocks their earnings and closes the sale."
    )
    await notify(order["buyer_id"], "order", title, body, f"/profile?tab=orders")
    return {"ok": True, "nudged_at": now.isoformat()}


# --- Seller Pick & Deliver flow ------------------------------------------
# The Feb 2026 flow: after a buyer places an order, the seller must
# explicitly accept it and pay the source cost from their wallet before
# fulfillment starts. If they lack funds, they can top up the wallet or
# tap into up to 50% of their frozen earnings.

FROZEN_USABLE_PCT = 0.50  # sellers can reinvest at most 50% of frozen balance


@api_router.get("/orders/{order_id}/pickup-quote")
async def pickup_quote(order_id: str, user: dict = Depends(get_current_user)):
    """Preview what accepting this order costs — used by the pickup modal.

    Returns cost, seller profit, current wallet balances, how much of
    frozen is reinvestable (75% cap), whether the seller can afford the
    order with available-only, and how much they'd still need to deposit."""
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(404, "Order not found")
    if order.get("seller_id") != user["id"] and user.get("role") != "admin":
        raise HTTPException(403, "Only the seller can accept this order")

    cost = float(order.get("reseller_wholesale_cost") or 0.0)
    profit = float(order.get("seller_earnings") or 0.0)
    seller_row = await db.users.find_one({"id": order["seller_id"]},
                                         {"_id": 0, "wallet_balance": 1, "wallet_frozen_balance": 1})
    available = round(float((seller_row or {}).get("wallet_balance") or 0.0), 2)
    frozen_total = round(float((seller_row or {}).get("wallet_frozen_balance") or 0.0), 2)
    # Exclude the current order's own sale_frozen credit (the buyer's escrow
    # for THIS order) from the reinvestable base — otherwise a seller could
    # spend 75% of the buyer's own escrow on the same order's source cost,
    # making refund reconciliation ugly if the buyer later disputes.
    frozen_ex_own = max(0.0, round(frozen_total - profit, 2))
    frozen_usable = round(frozen_ex_own * FROZEN_USABLE_PCT, 2)

    now = datetime.now(timezone.utc)
    deadline = order.get("pickup_deadline")
    if isinstance(deadline, str):
        try:
            deadline = datetime.fromisoformat(deadline.replace("Z", "+00:00"))
        except Exception:
            deadline = None
    if deadline and deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    hours_left = max(0.0, round((deadline - now).total_seconds() / 3600, 1)) if deadline else None

    max_pay = round(available + frozen_usable, 2)
    # Compute the auto-split preview so the UI can show exactly which
    # buckets will fund the pickup — no more opt-in checkbox.
    will_use_available = round(min(available, cost), 2) if cost > 0 else 0.0
    will_use_frozen = round(max(0.0, cost - available), 2) if cost > 0 else 0.0
    if will_use_frozen > frozen_usable:
        will_use_frozen = frozen_usable
    return {
        "order_id": order_id,
        "listing_title": order.get("listing_title"),
        "cost": cost,
        "profit": profit,
        "quantity": order.get("quantity", 1),
        "wallet": {
            "available": available,
            "frozen": frozen_total,
            "frozen_excluding_this_order": frozen_ex_own,
            "frozen_usable": frozen_usable,
            "this_order_escrow": profit,
        },
        "affordable_from_available": available >= cost,
        "affordable_with_frozen": max_pay >= cost,
        "will_use_available": will_use_available,
        "will_use_frozen": will_use_frozen,
        "deposit_needed": max(0.0, round(cost - max_pay, 2)),
        "fulfillment_status": order.get("fulfillment_status") or "pending_pickup",
        "pickup_deadline": deadline.isoformat() if deadline else None,
        "hours_left": hours_left,
    }


@api_router.get("/orders/{order_id}/wallet-events")
async def order_wallet_events(order_id: str, user: dict = Depends(get_current_user)):
    """Ledger timeline scoped to a single order — used by the Sales / Purchases
    row expander to render every wallet event that touched this order:

      * buyer's `purchase` debit at checkout
      * seller's `sale_frozen` credit (escrow held)
      * seller's `wholesale_debit` at Pick & Deliver
      * seller's `sale_released` credit when the buyer confirms delivery
      * affiliate / referral / dropship payouts

    Access: buyer, seller, dropship-source seller, or admin. Non-admin users
    only see their own rows so we don't leak other parties' balances."""
    order = await db.orders.find_one(
        {"id": order_id},
        {"_id": 0, "id": 1, "buyer_id": 1, "seller_id": 1,
         "dropship_source_seller_id": 1, "affiliate_user_id": 1, "listing_title": 1},
    )
    if not order:
        raise HTTPException(404, "Order not found")

    is_admin = user.get("role") == "admin"
    allowed = {order.get("buyer_id"), order.get("seller_id"),
               order.get("dropship_source_seller_id"), order.get("affiliate_user_id")}
    allowed.discard(None)
    if not is_admin and user["id"] not in allowed:
        raise HTTPException(403, "Not a party to this order")

    q: dict = {"related_id": order_id}
    if not is_admin:
        q["user_id"] = user["id"]

    rows = await db.wallet_txs.find(q, {"_id": 0}).sort("created_at", 1).to_list(500)

    # Attach a small view-model role tag so the UI can pick an icon / color
    # without re-inventing the mapping.
    def _tag(r: dict) -> dict:
        t = (r.get("type") or "").lower()
        amt = float(r.get("amount") or 0.0)
        if t == "purchase":
            role = "buyer_paid"
        elif t == "sale_frozen":
            role = "seller_escrow_held"
        elif t == "sale_released":
            role = "seller_delivery_released"
        elif t == "sale":
            role = "seller_credited"
        elif t == "wholesale_debit":
            role = "seller_wholesale_paid"
        elif t == "dropship_frozen":
            role = "dropship_source_escrow_held"
        elif t == "dropship_released":
            role = "dropship_source_released"
        elif t == "dropship":
            role = "dropship_source_credited"
        elif t == "affiliate":
            role = "affiliate_paid"
        elif t == "referral":
            role = "referral_paid"
        elif t == "refund":
            role = "refunded"
        else:
            role = t or "misc"
        r["role"] = role
        r["direction"] = "credit" if amt > 0 else ("debit" if amt < 0 else "hold")
        return r

    return {
        "order_id": order_id,
        "listing_title": order.get("listing_title"),
        "count": len(rows),
        "events": [_tag(r) for r in rows],
    }


@api_router.post("/orders/{order_id}/pickup", response_model=Order)
async def pickup_order(
    order_id: str,
    payload: dict = Body(default={}),   # kept for backwards compat; body is now ignored
    user: dict = Depends(get_current_user),
):
    """Seller accepts the order and pays the wholesale cost from their wallet.

    Auto-split (Feb 2026): the platform decides where the money comes from.
    * If `available >= cost` — the entire cost is debited from available.
    * Else — `available` is exhausted first, then the shortfall is drawn
      from frozen (capped at 75% of the seller's frozen balance).
    * If `available + 0.5*frozen < cost` — returns HTTP 402 with a
      `deposit_needed` amount so the UI can route the seller to /wallet.

    Concurrency: uses a `findOneAndUpdate` sentinel to atomically flip
    `pending_pickup → picking` so two concurrent pickup calls on the same
    order can't both slip past the balance check.
    """
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(404, "Order not found")
    if order.get("seller_id") != user["id"] and user.get("role") != "admin":
        raise HTTPException(403, "Only the seller can accept this order")
    if order.get("fulfillment_status") not in (None, "pending_pickup"):
        raise HTTPException(400, f"Order already {order.get('fulfillment_status')}")
    if order.get("status") in ("cancelled",):
        raise HTTPException(400, "Order has been cancelled")

    now = datetime.now(timezone.utc)
    deadline = order.get("pickup_deadline")
    if isinstance(deadline, str):
        try:
            deadline = datetime.fromisoformat(deadline.replace("Z", "+00:00"))
        except Exception:
            deadline = None
    if deadline and deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    if deadline and deadline < now:
        raise HTTPException(410, "Pickup window expired — order has been auto-cancelled")

    # Atomically claim the order — only one concurrent request can flip
    # pending_pickup → picking. This prevents a race where two /pickup
    # calls both read `available` before either wallet debit lands.
    claim = await db.orders.find_one_and_update(
        {"id": order_id, "fulfillment_status": "pending_pickup"},
        {"$set": {"fulfillment_status": "picking", "picking_started_at": now}},
        return_document=False,  # return the pre-update doc; None means someone else won
    )
    if not claim:
        # Another request is already handling this order (or it's not pending anymore).
        raise HTTPException(409, "Pickup already in progress for this order")

    cost = float(order.get("reseller_wholesale_cost") or 0.0)

    async def _release_claim():
        """Roll the sentinel back to pending_pickup on any failure path."""
        await db.orders.update_one(
            {"id": order_id, "fulfillment_status": "picking"},
            {"$set": {"fulfillment_status": "pending_pickup"},
             "$unset": {"picking_started_at": ""}},
        )

    seller_row = await db.users.find_one(
        {"id": order["seller_id"]},
        {"_id": 0, "wallet_balance": 1, "wallet_frozen_balance": 1},
    ) or {}
    available = round(float(seller_row.get("wallet_balance") or 0.0), 2)
    frozen_total = round(float(seller_row.get("wallet_frozen_balance") or 0.0), 2)
    # Exclude this order's own escrow credit (seller_earnings) from the
    # reinvestable base so a seller can't fund the source cost with the
    # buyer's own escrow for this same order. Refund reconciliation stays
    # clean if the buyer later disputes.
    this_order_escrow = float(order.get("seller_earnings") or 0.0)
    frozen_ex_own = max(0.0, round(frozen_total - this_order_escrow, 2))
    frozen_usable = round(frozen_ex_own * FROZEN_USABLE_PCT, 2)

    paid_frozen = 0.0
    paid_available = 0.0
    if cost > 0:
        if available >= cost:
            paid_available = cost
        else:
            paid_available = available
            paid_frozen = round(cost - available, 2)
            if paid_frozen > frozen_usable:
                # Frozen 75% cap can't cover the shortfall either.
                await _release_claim()
                max_pay = round(available + frozen_usable, 2)
                raise HTTPException(
                    402,
                    detail={
                        "code": "insufficient_funds",
                        "cost": cost,
                        "available": available,
                        "frozen": frozen_total,
                        "frozen_excluding_this_order": frozen_ex_own,
                        "frozen_usable": frozen_usable,
                        "this_order_escrow": this_order_escrow,
                        "deposit_needed": round(cost - max_pay, 2),
                        "message": "Not enough funds. Deposit into your wallet to pick this order.",
                    },
                )

        # Debit frozen first (if any), then available. Any ledger failure
        # rolls the sentinel back so the seller can retry cleanly.
        try:
            if paid_frozen > 0:
                await ledger.apply_entry(
                    db,
                    user_id=order["seller_id"],
                    delta=-paid_frozen,
                    tx_type="wholesale_debit",
                    description=f"Pick & Deliver (frozen reinvest): {order.get('listing_title','order')}",
                    related_id=order_id,
                    frozen=True,
                    require_available=True,
                )
            if paid_available > 0:
                await ledger.apply_entry(
                    db,
                    user_id=order["seller_id"],
                    delta=-paid_available,
                    tx_type="wholesale_debit",
                    description=f"Pick & Deliver: {order.get('listing_title','order')}",
                    related_id=order_id,
                    require_available=True,
                )
        except Exception:
            await _release_claim()
            raise
    # -- end wholesale debit block --

    updates = {
        "fulfillment_status": "picked",
        "reseller_paid_wholesale": cost > 0,
        "paid_from_available": paid_available,
        "paid_from_frozen": paid_frozen,
        "picked_up_at": now,
    }
    await db.orders.update_one(
        {"id": order_id},
        {
            "$set": updates,
            "$push": {
                "pickup_events": {
                    "type": "picked",
                    "at": now,
                    "paid_from_available": paid_available,
                    "paid_from_frozen": paid_frozen,
                    "channel": "seller",
                }
            },
        },
    )

    # Notify buyer
    await notify(
        order["buyer_id"], "order",
        f"Seller accepted your order",
        f"{order.get('listing_title','Your order')} has been picked up for delivery.",
        f"/profile?tab=orders",
    )

    updated = await db.orders.find_one({"id": order_id}, {"_id": 0})
    return Order(**updated)


@api_router.get("/seller/store-health")
async def seller_store_health(
    user: dict = Depends(get_current_user),
    days: int = 30,
):
    """Seller-facing "pickup health score" for their dashboard.

    Returns response-time and on-time acceptance stats over the last N days.
    Only counts orders whose pickup window has already closed (picked,
    delivered, shipped, or auto_cancelled) so the numbers stay stable."""
    health = await _compute_store_health(user["id"], days=days)
    history = await _get_or_backfill_health_history(user["id"], days=min(days, 30))
    health["history"] = history
    return health


async def _get_or_backfill_health_history(seller_id: str, *, days: int = 30) -> list[dict]:
    """Return up to `days` daily entries of `{date, score, tier}`. Prefer
    the array written by the nightly sweep; if fewer than 2 entries exist
    we synthesise a per-day rolling 30-day score from orders so the
    sparkline has something to draw on day one."""
    row = await db.users.find_one({"id": seller_id}, {"_id": 0, "health_history": 1}) or {}
    stored = list(row.get("health_history") or [])
    if len(stored) >= 2:
        # Trim to the last `days` entries. Stored entries look like
        # {"date": "YYYY-MM-DD", "score": float, "tier": str}.
        return stored[-days:]

    # Backfill: for each of the last `days` days compute the trailing
    # 30-day score based on orders resolved BEFORE that day. This is
    # O(days) find calls — bounded and cheap (small collection per seller).
    from asyncio import gather

    now = datetime.now(timezone.utc)
    async def _score_for_day(offset: int) -> dict:
        anchor = now - timedelta(days=offset)
        # Score using the trailing 30d window ending at `anchor`.
        window_start = anchor - timedelta(days=30)
        cursor = db.orders.find(
            {
                "seller_id": seller_id,
                "created_at": {"$gte": window_start, "$lte": anchor},
                "fulfillment_status": {"$in": ["picked", "shipped", "delivered", "auto_cancelled"]},
            },
            {"_id": 0, "picked_up_at": 1, "pickup_deadline": 1,
             "fulfillment_status": 1},
        )
        rows = await cursor.to_list(length=5000)
        total = len(rows)
        picked = [r for r in rows if r.get("picked_up_at")]
        on_time = 0
        for r in picked:
            pu = r.get("picked_up_at")
            dl = r.get("pickup_deadline")
            if isinstance(pu, str):
                try: pu = datetime.fromisoformat(pu.replace("Z", "+00:00"))
                except Exception: pu = None
            if isinstance(dl, str):
                try: dl = datetime.fromisoformat(dl.replace("Z", "+00:00"))
                except Exception: dl = None
            if pu and dl:
                if pu.tzinfo is None: pu = pu.replace(tzinfo=timezone.utc)
                if dl.tzinfo is None: dl = dl.replace(tzinfo=timezone.utc)
                if pu <= dl: on_time += 1
        if total == 0:
            return {"date": anchor.date().isoformat(), "score": None, "tier": "no_data"}
        acc = 100.0 * len(picked) / total
        ot = (100.0 * on_time / len(picked)) if picked else acc
        score = round(0.6 * acc + 0.4 * ot, 1)
        if score >= 90: tier = "excellent"
        elif score >= 75: tier = "good"
        elif score >= 50: tier = "at_risk"
        else: tier = "poor"
        return {"date": anchor.date().isoformat(), "score": score, "tier": tier}

    # Compute newest-last so the sparkline reads left→right chronologically.
    results = await gather(*[_score_for_day(i) for i in range(days - 1, -1, -1)])
    return results


async def _compute_store_health(seller_id: str, *, days: int = 30) -> dict:
    """Pure helper used by both the seller-facing endpoint and the nightly
    suspension sweep. Returns the same shape either way."""
    days = max(1, min(int(days or 30), 365))
    since = datetime.now(timezone.utc) - timedelta(days=days)

    resolved_statuses = ["picked", "shipped", "delivered", "auto_cancelled"]
    cursor = db.orders.find(
        {
            "seller_id": seller_id,
            "created_at": {"$gte": since},
            "fulfillment_status": {"$in": resolved_statuses},
        },
        {"_id": 0, "created_at": 1, "picked_up_at": 1, "pickup_deadline": 1,
         "fulfillment_status": 1, "auto_cancelled_at": 1},
    )
    rows = await cursor.to_list(length=5000)
    total = len(rows)
    picked = [r for r in rows if r.get("picked_up_at")]
    on_time = 0
    response_seconds: list[float] = []
    for r in picked:
        created = r.get("created_at")
        picked_at = r.get("picked_up_at")
        deadline = r.get("pickup_deadline")
        try:
            if isinstance(created, str):
                created = datetime.fromisoformat(created.replace("Z", "+00:00"))
            if isinstance(picked_at, str):
                picked_at = datetime.fromisoformat(picked_at.replace("Z", "+00:00"))
            if isinstance(deadline, str) and deadline:
                deadline = datetime.fromisoformat(deadline.replace("Z", "+00:00"))
        except Exception:
            continue
        if not (created and picked_at):
            continue
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        if picked_at.tzinfo is None:
            picked_at = picked_at.replace(tzinfo=timezone.utc)
        response_seconds.append((picked_at - created).total_seconds())
        if deadline:
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=timezone.utc)
            if picked_at <= deadline:
                on_time += 1

    picked_count = len(picked)
    cancelled_count = len([r for r in rows if r.get("fulfillment_status") == "auto_cancelled"])
    acceptance_rate = round(100.0 * picked_count / total, 1) if total else None
    on_time_rate = round(100.0 * on_time / picked_count, 1) if picked_count else None
    avg_response_hours = round(sum(response_seconds) / len(response_seconds) / 3600, 2) if response_seconds else None

    if total == 0:
        score = None
        tier = "no_data"
    else:
        acc = acceptance_rate or 0.0
        ot = on_time_rate if on_time_rate is not None else acc
        score = round(0.6 * acc + 0.4 * ot, 1)
        if score >= 90: tier = "excellent"
        elif score >= 75: tier = "good"
        elif score >= 50: tier = "at_risk"
        else: tier = "poor"

    return {
        "window_days": days,
        "total_orders": total,
        "picked_count": picked_count,
        "auto_cancelled_count": cancelled_count,
        "acceptance_rate_pct": acceptance_rate,
        "on_time_rate_pct": on_time_rate,
        "avg_response_hours": avg_response_hours,
        "score": score,
        "tier": tier,
    }


POOR_STREAK_SUSPEND_DAYS = 7  # after this many consecutive 'poor' days, auto-suspend listings


async def store_health_sweep_loop():
    """Nightly sweep: recompute every seller's rolling 30-day health tier.
    Sellers who've been at 'poor' for POOR_STREAK_SUSPEND_DAYS consecutive
    days get all their active listings auto-suspended; a `listings_suspended_at`
    marker is set on the user so the UI can show a banner. Any tier better
    than 'poor' resets the streak."""
    await asyncio.sleep(45)
    while True:
        try:
            # Only score users who've actually sold recently — cheap filter.
            now = datetime.now(timezone.utc)
            since = now - timedelta(days=30)
            seller_ids: list[str] = await db.orders.distinct(
                "seller_id", {"created_at": {"$gte": since}}
            )
            logger.info(f"[health-sweep] scoring {len(seller_ids)} sellers")
            for sid in seller_ids:
                try:
                    health = await _compute_store_health(sid, days=30)
                    user_row = await db.users.find_one(
                        {"id": sid},
                        {"_id": 0, "health_poor_streak_days": 1,
                         "listings_suspended_at": 1, "email": 1, "username": 1},
                    ) or {}
                    prev_streak = int(user_row.get("health_poor_streak_days") or 0)
                    tier = health.get("tier")
                    # Common history entry pushed for both branches.
                    history_entry = {
                        "date": now.date().isoformat(),
                        "score": health.get("score"),
                        "tier": tier,
                    }
                    if tier == "poor":
                        new_streak = prev_streak + 1
                        set_updates = {
                            "health_poor_streak_days": new_streak,
                            "health_score": health.get("score"),
                            "health_tier": tier,
                            "health_scored_at": now,
                        }
                        if prev_streak == 0:
                            set_updates["health_poor_since"] = now
                        # Auto-suspend when we hit the threshold — do it once.
                        if new_streak >= POOR_STREAK_SUSPEND_DAYS and not user_row.get("listings_suspended_at"):
                            set_updates["listings_suspended_at"] = now
                            set_updates["listings_suspend_reason"] = "poor_store_health"
                            await db.listings.update_many(
                                {"seller_id": sid, "status": "active"},
                                {"$set": {"status": "suspended", "suspended_at": now,
                                          "suspended_reason": "poor_store_health"}},
                            )
                            await notify(
                                sid, "admin",
                                "Your listings have been paused",
                                f"7 straight days of 'poor' store health triggered an automatic pause. Improve your acceptance rate and contact support to unpause.",
                                "/profile?tab=sales",
                            )
                        # Push history + cap array to last 30 entries.
                        await db.users.update_one(
                            {"id": sid},
                            {
                                "$set": set_updates,
                                "$push": {"health_history": {"$each": [history_entry], "$slice": -30}},
                            },
                        )
                    else:
                        # Any better tier resets the streak.
                        await db.users.update_one(
                            {"id": sid},
                            {
                                "$set": {
                                    "health_poor_streak_days": 0,
                                    "health_poor_since": None,
                                    "health_score": health.get("score"),
                                    "health_tier": tier,
                                    "health_scored_at": now,
                                },
                                "$push": {"health_history": {"$each": [history_entry], "$slice": -30}},
                            },
                        )
                except Exception as e:
                    logger.warning(f"[health-sweep] failed for seller {sid}: {e}")
        except Exception as e:
            logger.exception(f"store_health_sweep_loop error: {e}")
        # Run daily (or on the interval env var — smaller for testing).
        await asyncio.sleep(int(os.environ.get("HEALTH_SWEEP_INTERVAL_SEC", "86400")))


@api_router.get("/admin/users/suspended-listings")
async def admin_list_suspended_sellers(_admin: dict = Depends(require_admin)):
    """List all sellers currently auto-suspended due to poor store health."""
    cursor = db.users.find(
        {"listings_suspended_at": {"$exists": True},
         "listings_suspend_reason": "poor_store_health"},
        {"_id": 0, "id": 1, "email": 1, "username": 1,
         "listings_suspended_at": 1, "health_score": 1, "health_tier": 1,
         "health_poor_streak_days": 1},
    ).sort("listings_suspended_at", -1)
    rows = await cursor.to_list(length=200)
    # Enrich with number of suspended listings each.
    for r in rows:
        r["suspended_listing_count"] = await db.listings.count_documents({
            "seller_id": r["id"], "status": "suspended",
            "suspended_reason": "poor_store_health",
        })
    return {"users": rows, "count": len(rows)}


@api_router.post("/admin/users/{user_id}/unlock-listings")
async def admin_unlock_listings(user_id: str, _admin: dict = Depends(require_admin)):
    """Restore a seller's suspended listings after a health-tier auto-pause.
    Only affects listings that were suspended by the health sweep — leaves
    other suspensions (admin-issued, reported, etc.) untouched."""
    result = await db.listings.update_many(
        {"seller_id": user_id, "status": "suspended", "suspended_reason": "poor_store_health"},
        {"$set": {"status": "active"},
         "$unset": {"suspended_at": "", "suspended_reason": ""}},
    )
    now = datetime.now(timezone.utc)
    await db.users.update_one(
        {"id": user_id},
        {"$set": {
            "health_poor_streak_days": 0,
            "health_poor_since": None,
            "reactivated_at": now,           # arms the mandatory reactivation checklist
        },
         "$unset": {
            "listings_suspended_at": "",
            "listings_suspend_reason": "",
            "reactivation_checklist_acked_at": "",  # force re-ack on every unlock
         }},
    )
    await notify(
        user_id, "admin",
        "Your listings are back online — please review the reactivation checklist",
        "An admin restored your listings. Complete the 60-second checklist on your dashboard so you don't get auto-paused again.",
        "/profile?tab=sales",
    )
    return {
        "ok": True,
        "user_id": user_id,
        "listings_restored": result.modified_count,
    }


# Days the checklist stays "armed" after reactivation — auto-clears itself.
REACTIVATION_CHECKLIST_TTL_DAYS = 7

REACTIVATION_CHECKLIST_ITEMS = [
    {
        "id": "accept_fast",
        "title": "Accept new orders within 6 hours",
        "body": "Speed is the single biggest driver of the health score — the faster you pick, the higher your on-time rate climbs.",
    },
    {
        "id": "no_auto_cancel",
        "title": "Never let an order auto-cancel",
        "body": "A single auto-cancel wipes out days of good behaviour. Turn on push notifications and watch your inbox for reminders.",
    },
    {
        "id": "keep_wallet_topped",
        "title": "Keep your wallet topped up",
        "body": "Deposit before you list high-value items so you can Pick & Deliver immediately without waiting on a bank transfer.",
    },
    {
        "id": "reply_buyers",
        "title": "Reply to buyer messages within 24 hours",
        "body": "Fast replies reduce dispute rates and keep your acceptance rate looking strong.",
    },
    {
        "id": "watch_dashboard",
        "title": "Check your store health score daily for the next week",
        "body": "Your dashboard now shows a live tier — if it drops to 'poor' again, you'll be auto-paused after 7 straight days.",
    },
]


@api_router.get("/seller/reactivation-checklist")
async def get_reactivation_checklist(user: dict = Depends(get_current_user)):
    """Returns whether the seller should see the mandatory reactivation
    checklist (post-unlock onboarding) plus the item list. Auto-expires
    after REACTIVATION_CHECKLIST_TTL_DAYS."""
    row = await db.users.find_one(
        {"id": user["id"]},
        {"_id": 0, "reactivated_at": 1, "reactivation_checklist_acked_at": 1},
    ) or {}
    reactivated_at = row.get("reactivated_at")
    acked_at = row.get("reactivation_checklist_acked_at")

    def _dt(v):
        if isinstance(v, str):
            try:
                return datetime.fromisoformat(v.replace("Z", "+00:00"))
            except Exception:
                return None
        return v

    reactivated_at = _dt(reactivated_at)
    acked_at = _dt(acked_at)
    now = datetime.now(timezone.utc)

    required = False
    if reactivated_at:
        if reactivated_at.tzinfo is None:
            reactivated_at = reactivated_at.replace(tzinfo=timezone.utc)
        # Auto-clear after TTL so a stale row doesn't nag forever.
        if (now - reactivated_at).days >= REACTIVATION_CHECKLIST_TTL_DAYS:
            required = False
        elif not acked_at or (acked_at.replace(tzinfo=timezone.utc) if acked_at.tzinfo is None else acked_at) < reactivated_at:
            required = True

    return {
        "required": required,
        "reactivated_at": reactivated_at.isoformat() if reactivated_at else None,
        "acked_at": acked_at.isoformat() if acked_at else None,
        "items": REACTIVATION_CHECKLIST_ITEMS,
    }


@api_router.post("/seller/reactivation-checklist/ack")
async def ack_reactivation_checklist(user: dict = Depends(get_current_user)):
    """Seller acknowledges the reactivation checklist — dismisses the
    modal until the next admin unlock. Idempotent."""
    now = datetime.now(timezone.utc)
    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {"reactivation_checklist_acked_at": now}},
    )
    return {"ok": True, "acked_at": now.isoformat()}


@api_router.get("/seller/orders/pending-pickup")
async def seller_pending_pickups(user: dict = Depends(get_current_user)):
    cursor = db.orders.find(
        {"seller_id": user["id"], "fulfillment_status": "pending_pickup"},
        {"_id": 0},
    ).sort("created_at", 1)
    rows = await cursor.to_list(length=200)
    now = datetime.now(timezone.utc)
    out = []
    for r in rows:
        d = r.get("pickup_deadline")
        if isinstance(d, str):
            try:
                d = datetime.fromisoformat(d.replace("Z", "+00:00"))
            except Exception:
                d = None
        if d and d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        r["hours_left"] = max(0.0, round((d - now).total_seconds() / 3600, 1)) if d else None
        out.append(r)
    return {"orders": out, "count": len(out)}


@api_router.get("/stores/{slug}/pending-pickups")
async def store_pending_pickups(slug: str, user: dict = Depends(get_current_user)):
    """Admin-only: list pending pickups for the seller behind a store.
    Powers the red "nudge seller" banner on `/store/:slug`."""
    if user.get("role") != "admin":
        raise HTTPException(403, "Admin only")
    store = await db.stores.find_one({"slug": slug}, {"_id": 0, "owner_id": 1, "name": 1})
    if not store:
        raise HTTPException(404, "Store not found")
    cursor = db.orders.find(
        {"seller_id": store["owner_id"], "fulfillment_status": "pending_pickup"},
        {"_id": 0, "id": 1, "listing_title": 1, "reseller_wholesale_cost": 1,
         "pickup_deadline": 1, "created_at": 1, "buyer_id": 1, "amount": 1,
         "nudged_at": 1, "nudge_count": 1},
    ).sort("pickup_deadline", 1)
    rows = await cursor.to_list(length=200)
    now = datetime.now(timezone.utc)
    for r in rows:
        d = r.get("pickup_deadline")
        if isinstance(d, str):
            try:
                d = datetime.fromisoformat(d.replace("Z", "+00:00"))
            except Exception:
                d = None
        if d and d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        r["hours_left"] = max(0.0, round((d - now).total_seconds() / 3600, 1)) if d else None
    return {
        "store": {"slug": slug, "owner_id": store["owner_id"], "name": store.get("name")},
        "orders": rows,
        "count": len(rows),
    }


@api_router.post("/admin/orders/{order_id}/nudge")
async def admin_nudge_seller(
    order_id: str,
    payload: dict = Body(default={}),
    _admin: dict = Depends(require_admin),
):
    """Admin-triggered nudge: sends a stern email + in-app notification
    urging the seller to Pick & Deliver an order that's still pending.
    Tracks `nudged_at` + `nudge_count` on the order so admins can see
    how many times they've chased this one."""
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(404, "Order not found")
    if order.get("fulfillment_status") != "pending_pickup":
        raise HTTPException(400, f"Order is not pending pickup ({order.get('fulfillment_status')})")

    note = str(payload.get("message") or "").strip()
    seller_id = order["seller_id"]
    cost = float(order.get("reseller_wholesale_cost") or 0.0)
    profit = float(order.get("seller_earnings") or 0.0)

    # In-app notification.
    body = note or (
        f"An admin is chasing this order — pay the ${cost:.2f} source cost now "
        f"or lose the sale (and your ${profit:.2f} profit)."
    )
    await notify(
        seller_id, "admin",
        f"Admin nudge: pick and deliver '{order.get('listing_title','order')}'",
        body,
        f"/profile?tab=orders&pickup={order_id}",
    )

    # Escalated email — reuse pickup email template with `admin_nudge` kind.
    try:
        from services.mailer import send_email
        from services.email_templates import _shell, FRONTEND
        seller = await db.users.find_one({"id": seller_id}, {"_id": 0, "email": 1, "username": 1})
        if seller and seller.get("email"):
            cta_url = f"{FRONTEND.rstrip('/')}/profile?tab=sales&pickup={order_id}"
            html = _shell(seller.get("username") or "Seller", f"""
<h1 style="margin:0 0 8px 0;font-size:22px;color:#111;">Admin nudge — accept your order now</h1>
<p style="margin:0 0 12px 0;color:#333;">
{note or "One of our admins is watching this order. Accept and pay the source cost immediately, or the order will auto-cancel and the buyer will be refunded."}
</p>
<div style="border:1px solid #eee;border-radius:8px;padding:14px 16px;background:#fafafa;margin:12px 0;">
  <div style="font-weight:600;color:#111;margin-bottom:6px;">{order.get('listing_title','')}</div>
  <div>Source cost: <b>${cost:.2f}</b></div>
  <div>Your profit (held until delivery): <b style="color:#0a7c3e;">${profit:.2f}</b></div>
</div>
<p style="margin:16px 0;">
  <a href="{cta_url}" style="background:#FF211F;color:#fff;padding:10px 22px;border-radius:999px;text-decoration:none;font-weight:600;">
    Pick &amp; Deliver →
  </a>
</p>
""".strip())
            await send_email(
                to=seller["email"],
                subject="[Ocean] Admin nudge — accept your order now",
                html=html,
                tags=["pickup", "admin_nudge"],
            )
    except Exception as e:
        logger.warning(f"admin nudge email failed for order {order_id}: {e}")

    await db.orders.update_one(
        {"id": order_id},
        {
            "$set": {"nudged_at": datetime.now(timezone.utc)},
            "$inc": {"nudge_count": 1},
            "$push": {
                "pickup_events": {
                    "type": "admin_nudge",
                    "at": datetime.now(timezone.utc),
                    "admin_id": _admin["id"],
                    "admin_email": _admin.get("email"),
                    "message": note or None,
                    "channel": "email+notify",
                }
            },
        },
    )
    return {"ok": True, "order_id": order_id, "message": "Seller nudged"}


@api_router.get("/admin/orders/{order_id}/pickup-timeline")
async def admin_pickup_timeline(order_id: str, _admin: dict = Depends(require_admin)):
    """Chronological audit trail of everything that fired on this order's
    pickup lifecycle — used by admins before escalating a lazy seller."""
    order = await db.orders.find_one(
        {"id": order_id},
        {"_id": 0, "id": 1, "fulfillment_status": 1, "created_at": 1,
         "pickup_deadline": 1, "picked_up_at": 1, "auto_cancelled_at": 1,
         "nudge_count": 1, "nudged_at": 1, "listing_title": 1,
         "seller_id": 1, "pickup_events": 1},
    )
    if not order:
        raise HTTPException(404, "Order not found")

    events = list(order.get("pickup_events") or [])
    # Synthesise the lifecycle bookends so admins see the full picture even
    # if a legacy order was created before the pickup_events log existed.
    if order.get("created_at"):
        events.append({"type": "order_created", "at": order["created_at"], "channel": "system"})
    if order.get("picked_up_at"):
        events.append({"type": "picked", "at": order["picked_up_at"], "channel": "seller"})
    if order.get("auto_cancelled_at"):
        events.append({"type": "auto_cancelled", "at": order["auto_cancelled_at"], "channel": "system"})

    def _ts(e):
        v = e.get("at")
        if isinstance(v, str):
            try:
                return datetime.fromisoformat(v.replace("Z", "+00:00"))
            except Exception:
                return datetime.min.replace(tzinfo=timezone.utc)
        return v or datetime.min.replace(tzinfo=timezone.utc)

    events.sort(key=_ts)
    return {
        "order_id": order_id,
        "listing_title": order.get("listing_title"),
        "fulfillment_status": order.get("fulfillment_status"),
        "nudge_count": order.get("nudge_count", 0),
        "pickup_deadline": order.get("pickup_deadline"),
        "events": events,
    }





@api_router.post("/orders/{order_id}/confirm-delivery", response_model=Order)
async def confirm_delivery(order_id: str, user: dict = Depends(get_current_user)):
    """Buyer confirms they received the item. Releases the seller's (and dropship
    source's) frozen earnings into their available wallet balance. Admins may also
    call this to force-release. Idempotent — repeat calls are no-ops."""
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(404, "Order not found")
    is_buyer = order.get("buyer_id") == user["id"]
    is_admin = user.get("role") == "admin"
    if not (is_buyer or is_admin):
        raise HTTPException(403, "Only the buyer or an admin can confirm delivery")
    if order.get("funds_released"):
        return Order(**order)

    now = datetime.now(timezone.utc)
    updates: dict = {
        "delivery_confirmed_at": now.isoformat(),
        "funds_released": True,
        "status": "delivered",
        "shipping_status": "delivered",
    }
    await db.orders.update_one({"id": order_id}, {"$set": updates})

    # Release frozen earnings.
    if float(order.get("seller_earnings", 0.0)) > 0:
        await release_frozen(
            order["seller_id"], float(order["seller_earnings"]),
            f"Released: {order.get('listing_title','sale')}", order_id, tx_type="sale_released",
        )
        await notify(
            order["seller_id"], "wallet",
            f"Funds released: {order.get('listing_title','')}",
            f"${float(order['seller_earnings']):.2f} moved from frozen to available.",
            "/wallet",
        )
    if order.get("dropship_source_seller_id") and float(order.get("dropship_source_earnings", 0.0)) > 0:
        await release_frozen(
            order["dropship_source_seller_id"], float(order["dropship_source_earnings"]),
            f"Dropship released: {order.get('listing_title','sale')}", order_id, tx_type="dropship_released",
        )
        await notify(
            order["dropship_source_seller_id"], "wallet",
            f"Dropship funds released: {order.get('listing_title','')}",
            f"${float(order['dropship_source_earnings']):.2f} moved from frozen to available.",
            "/wallet",
        )
    await notify(
        order["buyer_id"], "order",
        f"Delivery confirmed: {order.get('listing_title','')}",
        "Thanks! Your seller has been paid out.",
        "/profile?tab=orders",
    )
    fresh = await db.orders.find_one({"id": order_id}, {"_id": 0})
    return Order(**fresh)


class BulkConfirmDeliveryRequest(BaseModel):
    order_ids: List[str]


@api_router.post("/admin/orders/bulk-confirm-delivery")
async def bulk_confirm_delivery(
    payload: BulkConfirmDeliveryRequest,
    _admin: dict = Depends(require_admin),
):
    """Admin-only. Force-release escrow on many orders at once by treating
    each as if the buyer confirmed delivery. Idempotent per order — orders
    that already have `funds_released=True` are counted as skipped."""
    ids = [i for i in (payload.order_ids or []) if isinstance(i, str) and i]
    if not ids:
        raise HTTPException(400, "No order ids provided")
    if len(ids) > 500:
        raise HTTPException(400, "Max 500 orders per call")

    results: List[dict] = []
    for oid in ids:
        order = await db.orders.find_one({"id": oid}, {"_id": 0})
        if not order:
            results.append({"order_id": oid, "ok": False, "message": "not found", "skipped": True})
            continue
        if order.get("funds_released"):
            results.append({"order_id": oid, "ok": True, "message": "already released", "skipped": True})
            continue

        try:
            now = datetime.now(timezone.utc)
            await db.orders.update_one(
                {"id": oid, "funds_released": {"$ne": True}},
                {"$set": {
                    "delivery_confirmed_at": now.isoformat(),
                    "funds_released": True,
                    "status": "delivered",
                    "shipping_status": "delivered",
                }},
            )
            seller_amt = float(order.get("seller_earnings") or 0.0)
            if seller_amt > 0:
                await release_frozen(
                    order["seller_id"], seller_amt,
                    f"Released: {order.get('listing_title','sale')}",
                    oid, tx_type="sale_released",
                )
                await notify(
                    order["seller_id"], "wallet",
                    f"Funds released: {order.get('listing_title','')}",
                    f"${seller_amt:.2f} moved from frozen to available.",
                    "/wallet",
                )
            drop_amt = float(order.get("dropship_source_earnings") or 0.0)
            if order.get("dropship_source_seller_id") and drop_amt > 0:
                await release_frozen(
                    order["dropship_source_seller_id"], drop_amt,
                    f"Dropship released: {order.get('listing_title','sale')}",
                    oid, tx_type="dropship_released",
                )
                await notify(
                    order["dropship_source_seller_id"], "wallet",
                    f"Dropship funds released: {order.get('listing_title','')}",
                    f"${drop_amt:.2f} moved from frozen to available.",
                    "/wallet",
                )
            await notify(
                order["buyer_id"], "order",
                f"Delivery confirmed: {order.get('listing_title','')}",
                "An admin confirmed delivery on this order — your seller has been paid out.",
                "/profile?tab=orders",
            )
            results.append({
                "order_id": oid, "ok": True,
                "message": f"released ${seller_amt + drop_amt:.2f}",
                "_releases": {
                    "order_id": oid,
                    "seller_id": order.get("seller_id"),
                    "seller_amt": seller_amt,
                    "source_seller_id": order.get("dropship_source_seller_id"),
                    "source_amt": drop_amt,
                    "title": order.get("listing_title", ""),
                },
            })
        except Exception as e:
            results.append({"order_id": oid, "ok": False, "message": str(e)[:120]})

    succeeded = sum(1 for r in results if r.get("ok") and not r.get("skipped"))
    skipped = sum(1 for r in results if r.get("skipped"))
    failed = sum(1 for r in results if not r.get("ok") and not r.get("skipped"))

    # Record the batch so admins can roll it back within a short window
    # (defence-in-depth for accidental confirms). Only orders that were
    # actually released (ok=True, skipped=False) are eligible for rollback.
    releases = [
        r for r in results
        if r.get("ok") and not r.get("skipped") and r.get("_releases")
    ]
    batch_id: Optional[str] = None
    if releases:
        batch_id = str(uuid.uuid4())
        await db.bulk_confirm_batches.insert_one({
            "id": batch_id,
            "admin_id": _admin["id"],
            "admin_username": _admin.get("username"),
            "created_at": datetime.now(timezone.utc),
            "rolled_back_at": None,
            "releases": [r["_releases"] for r in releases],
        })
    # Strip the internal `_releases` key before returning to the client
    for r in results:
        r.pop("_releases", None)
    return {
        "results": results, "succeeded": succeeded, "skipped": skipped,
        "failed": failed, "batch_id": batch_id,
    }


ROLLBACK_WINDOW_MIN = 30


@api_router.get("/admin/orders/last-bulk-confirm-batch")
async def last_bulk_confirm_batch(_admin: dict = Depends(require_admin)):
    """Return the most recent non-rolled-back batch inside the rollback
    window. UI uses this to decide whether to show the Undo button."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=ROLLBACK_WINDOW_MIN)
    doc = await db.bulk_confirm_batches.find_one(
        {"rolled_back_at": None, "created_at": {"$gte": cutoff}},
        {"_id": 0},
        sort=[("created_at", -1)],
    )
    if not doc:
        return {"batch": None}
    # Convert datetime for JSON
    doc["created_at"] = doc["created_at"].isoformat() if hasattr(doc["created_at"], "isoformat") else doc["created_at"]
    doc["order_count"] = len(doc.get("releases") or [])
    doc["total_amount"] = round(
        sum(float(r.get("seller_amt", 0) or 0) + float(r.get("source_amt", 0) or 0)
            for r in (doc.get("releases") or [])), 2,
    )
    # Strip the full releases array from the wire — UI just needs the summary
    doc.pop("releases", None)
    return {"batch": doc, "window_min": ROLLBACK_WINDOW_MIN}


class BulkConfirmRollbackRequest(BaseModel):
    batch_id: str


@api_router.post("/admin/orders/bulk-confirm-rollback")
async def bulk_confirm_rollback(
    payload: BulkConfirmRollbackRequest,
    _admin: dict = Depends(require_admin),
):
    """Reverse a bulk-confirm-delivery batch: re-freeze each released amount
    and flip funds_released back to False on every order in the batch. Only
    works within ROLLBACK_WINDOW_MIN minutes of the original batch."""
    batch = await db.bulk_confirm_batches.find_one({"id": payload.batch_id}, {"_id": 0})
    if not batch:
        raise HTTPException(404, "Batch not found")
    if batch.get("rolled_back_at"):
        raise HTTPException(400, "Batch already rolled back")
    created = batch.get("created_at")
    if isinstance(created, str):
        try:
            created = datetime.fromisoformat(created.replace("Z", "+00:00"))
        except Exception:
            created = None
    if created and created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    if not created or (datetime.now(timezone.utc) - created) > timedelta(minutes=ROLLBACK_WINDOW_MIN):
        raise HTTPException(400, f"Rollback window ({ROLLBACK_WINDOW_MIN} min) expired")

    reversed_orders: List[dict] = []
    for rel in (batch.get("releases") or []):
        oid = rel.get("order_id")
        if not oid:
            continue
        # Flip order back — only if it's still marked released (someone might
        # have manually altered it since; we don't want to fight admin actions).
        upd = await db.orders.update_one(
            {"id": oid, "funds_released": True},
            {"$set": {"funds_released": False, "status": "paid",
                      "delivery_confirmed_at": None}},
        )
        if upd.modified_count == 0:
            reversed_orders.append({"order_id": oid, "ok": False, "message": "order no longer released"})
            continue
        # Reverse seller side
        seller_amt = float(rel.get("seller_amt") or 0)
        if seller_amt > 0 and rel.get("seller_id"):
            await credit_wallet(rel["seller_id"], -seller_amt, "sale_frozen",
                                f"Bulk confirm rolled back: {rel.get('title','')}", oid)
            await credit_wallet(rel["seller_id"], seller_amt, "sale_frozen",
                                f"Re-frozen after rollback: {rel.get('title','')}", oid, frozen=True)
            await notify(rel["seller_id"], "wallet",
                         f"Escrow re-frozen: {rel.get('title','')}",
                         f"An admin rolled back the delivery confirm. ${seller_amt:.2f} moved back to frozen.",
                         "/wallet")
        source_amt = float(rel.get("source_amt") or 0)
        if source_amt > 0 and rel.get("source_seller_id"):
            await credit_wallet(rel["source_seller_id"], -source_amt, "dropship_frozen",
                                f"Bulk confirm rolled back: {rel.get('title','')}", oid)
            await credit_wallet(rel["source_seller_id"], source_amt, "dropship_frozen",
                                f"Re-frozen after rollback: {rel.get('title','')}", oid, frozen=True)
        reversed_orders.append({"order_id": oid, "ok": True,
                                "message": f"reversed ${seller_amt + source_amt:.2f}"})

    await db.bulk_confirm_batches.update_one(
        {"id": payload.batch_id},
        {"$set": {"rolled_back_at": datetime.now(timezone.utc),
                  "rolled_back_by": _admin["id"]}},
    )
    succeeded = sum(1 for r in reversed_orders if r.get("ok"))
    failed = len(reversed_orders) - succeeded
    return {"results": reversed_orders, "succeeded": succeeded, "failed": failed}


# =========================
# Messages
# =========================
# Legacy /messages routes moved to routers/messaging.py


# =========================
# Admin
# =========================
@api_router.get("/admin/stats")
async def admin_stats(_admin: dict = Depends(require_admin)):
    users_count = await db.users.count_documents({})
    active_listings = await db.listings.count_documents({"status": "active"})
    sold_listings = await db.listings.count_documents({"status": "sold"})
    orders_count = await db.orders.count_documents({})
    categories_count = await db.categories.count_documents({})
    stores_count = await db.stores.count_documents({})
    pending_withdrawals = await db.withdrawals.count_documents({"status": "pending"})
    pending_seller_apps = await db.seller_applications.count_documents({"status": "pending"})
    revenue_agg = await db.orders.aggregate([
        {"$group": {"_id": None, "total": {"$sum": "$amount"}, "fees": {"$sum": "$platform_fee"}}}
    ]).to_list(1)
    total_revenue = revenue_agg[0]["total"] if revenue_agg else 0
    total_fees = revenue_agg[0].get("fees", 0) if revenue_agg else 0
    affiliate_links = await db.affiliate_links.count_documents({})
    return {
        "users": users_count,
        "active_listings": active_listings,
        "sold_listings": sold_listings,
        "orders": orders_count,
        "categories": categories_count,
        "stores": stores_count,
        "affiliate_links": affiliate_links,
        "pending_withdrawals": pending_withdrawals,
        "pending_seller_apps": pending_seller_apps,
        "revenue": total_revenue,
        "platform_fees": total_fees,
    }


# ---------------------------------------------------------------------------
# SMTP health probe — admin-only, cached 60s.
# ---------------------------------------------------------------------------
_SMTP_HEALTH_CACHE: dict = {"at": None, "result": None}
_SMTP_HEALTH_TTL_SECONDS = 60


async def _smtp_probe() -> dict:
    """Open a real SMTP session and issue `MAIL FROM` + `RCPT TO` + `RSET`
    (no DATA — no email actually sent). Returns
    {ok, state, provider, host, error?, latency_ms, checked_at}.
    Distinguishes:
      - unconfigured: SMTP env vars missing
      - unreachable:  can't connect
      - auth_failed:  login rejected
      - blocked:      Hostinger 5.7.1 outbound-disabled fires at MAIL FROM
                      even though login succeeded (this is the real
                      failure mode; login-only probes falsely pass)
      - healthy:      MAIL FROM/RCPT TO accepted, session RSET cleanly
    """
    import time
    from services import mailer as _mailer
    started = time.time()
    now = datetime.now(timezone.utc)
    cfg = _mailer._cfg()
    if not _mailer.is_configured():
        return {
            "ok": False,
            "state": "unconfigured",
            "provider": cfg["provider"] or None,
            "host": cfg["host"] or None,
            "error": "SMTP env vars missing (SMTP_HOST/USER/PASSWORD/EMAIL_FROM_ADDRESS/EMAIL_PROVIDER)",
            "latency_ms": 0,
            "checked_at": now.isoformat(),
        }
    try:
        import aiosmtplib
        secure = cfg["secure"]
        use_tls = secure and cfg["port"] == 465
        start_tls = secure and cfg["port"] in (587, 25)
        client = aiosmtplib.SMTP(
            hostname=cfg["host"],
            port=cfg["port"],
            use_tls=use_tls,
            start_tls=False,
            timeout=10,
        )
        await client.connect()
        try:
            if start_tls:
                await client.starttls()
            await client.login(cfg["user"], cfg["password"])
            # Login accepted — now confirm outbound MAIL FROM/RCPT TO also
            # works. Hostinger blocks with 554 5.7.1 here when the mailbox
            # has outbound disabled, even though login just succeeded.
            probe_to = cfg["from_addr"]  # loopback to self — never delivered
            await client.mail(cfg["from_addr"])
            await client.rcpt(probe_to)
            # Abort before DATA — no email ever leaves the server.
            await client.rset()
        finally:
            try:
                await client.quit()
            except Exception:
                pass
        return {
            "ok": True,
            "state": "healthy",
            "provider": cfg["provider"],
            "host": cfg["host"],
            "latency_ms": int((time.time() - started) * 1000),
            "checked_at": now.isoformat(),
        }
    except Exception as e:  # noqa: BLE001
        err_str = str(e)
        state = "unreachable"
        if "Outbound sending is disabled" in err_str or "5.7.1" in err_str:
            state = "blocked"
        elif "authentication" in err_str.lower() or "5.7.8" in err_str:
            state = "auth_failed"
        elif "5.7." in err_str or "554" in err_str:
            # Any other 5.7.x policy rejection = still a blocked mailbox
            state = "blocked"
        return {
            "ok": False,
            "state": state,
            "provider": cfg["provider"],
            "host": cfg["host"],
            "error": err_str[:400],
            "latency_ms": int((time.time() - started) * 1000),
            "checked_at": now.isoformat(),
        }


@api_router.get("/admin/smtp/health")
async def admin_smtp_health(_admin: dict = Depends(require_admin), force: bool = False):
    """Cached SMTP health probe. Runs a real login handshake against the
    configured SMTP provider (no email is sent). Cached for 60 seconds so
    the admin ticker can poll every minute without hammering Hostinger.
    Pass `?force=1` to bypass the cache.

    Correctness note: the handshake alone is not enough — Hostinger and
    some other providers enforce outbound blocks only at the DATA stage.
    So we also consult the recent real send-outcome history from
    services.mailer; if we've seen a 5.7.1 rejection in the last 15
    minutes, we override a `healthy` handshake with `blocked` and surface
    the real error text."""
    cached = _SMTP_HEALTH_CACHE.get("result")
    at = _SMTP_HEALTH_CACHE.get("at")
    now = datetime.now(timezone.utc)
    if not force and cached and at:
        age = (now - at).total_seconds()
        if age < _SMTP_HEALTH_TTL_SECONDS:
            return {**cached, "cached": True, "cache_age_seconds": int(age)}
    result = await _smtp_probe()

    # Consult the real send outcome history — a handshake-only pass can
    # be a false positive on Hostinger.
    try:
        from services import mailer as _mailer
        recent = _mailer.recent_send_outcomes(within_seconds=900)
        failures = [o for o in recent if not o["ok"]]
        if failures and result.get("state") == "healthy":
            # Look for the well-known blocking codes in the recent errors
            last_err = failures[-1].get("error", "")
            override_state = None
            if "Outbound sending is disabled" in last_err or "5.7.1" in last_err:
                override_state = "blocked"
            elif "5.7.8" in last_err or "authentication" in last_err.lower():
                override_state = "auth_failed"
            elif "5.7." in last_err or "554" in last_err:
                override_state = "blocked"
            if override_state:
                result = {
                    **result,
                    "ok": False,
                    "state": override_state,
                    "error": last_err[:400],
                    "handshake_passed": True,
                    "recent_failures": len(failures),
                    "recent_send_window_seconds": 900,
                }
        # Always attach the counts so the UI can show "X of Y recent sends failed".
        result.setdefault("recent_failures", len(failures))
        result.setdefault("recent_successes", len(recent) - len(failures))
    except Exception:  # noqa: BLE001
        pass

    _SMTP_HEALTH_CACHE["result"] = result
    _SMTP_HEALTH_CACHE["at"] = now
    return {**result, "cached": False, "cache_age_seconds": 0}


@api_router.get("/admin/users", response_model=List[UserPublic])
async def admin_list_users(_admin: dict = Depends(require_admin), real_only: bool = False):
    docs = await db.users.find({}, {"_id": 0, "password_hash": 0}).sort("created_at", -1).to_list(1000)

    # Real users float to the top so admins don't scroll past hundreds of
    # e2e / seed / apify fixture rows. Classification lives in
    # utils.admin_sort so every admin listing endpoint uses the same rules.
    from utils.admin_sort import is_synthetic_user_doc as _is_synth_user, _created_ts

    if real_only:
        docs = [u for u in docs if not _is_synth_user(u)]
    docs.sort(key=lambda u: (_is_synth_user(u), -_created_ts(u)))
    return [UserPublic(**d) for d in docs]


# ---------------------------------------------------------------------------
# Force-degraded simulator — admin can flip `/api/health` into `degraded`
# state for N seconds so the self-ping loop sees it twice and fires a real
# Slack alert end-to-end. Perfect for Postman-driven pipeline validation.
# ---------------------------------------------------------------------------
class _ForceDegradedRequest(BaseModel):
    duration_sec: int = 900  # default 15 min — enough for 3 self-pings @ 5m
    reason: Optional[str] = None


@api_router.post("/admin/health/force-degraded")
async def admin_health_force_degraded(
    body: _ForceDegradedRequest,
    _admin: dict = Depends(require_admin),
):
    """Simulate a degraded state so the Slack paging pipeline can be tested
    without breaking Mongo or SMTP. The self-ping loop hits `/api/health`
    every 5 min; two consecutive `degraded` reads trigger the alert. Set
    ``duration_sec >= 600`` to guarantee both pings land inside the window.
    """
    global _FORCE_DEGRADED_UNTIL_TS, _FORCE_DEGRADED_REASON  # noqa: PLW0603
    duration = max(0, min(int(body.duration_sec or 0), 3600))  # cap at 1h
    if duration == 0:
        _FORCE_DEGRADED_UNTIL_TS = 0.0
        _FORCE_DEGRADED_REASON = ""
        logger.info("[health] force-degraded cleared by admin")
        return {"ok": True, "cleared": True}
    _FORCE_DEGRADED_UNTIL_TS = time.monotonic() + duration
    _FORCE_DEGRADED_REASON = (body.reason or "admin-simulated")[:200]
    logger.warning(
        f"[health] admin forced status=degraded for {duration}s "
        f"(reason: {_FORCE_DEGRADED_REASON})"
    )
    return {
        "ok": True,
        "seconds_left": duration,
        "reason": _FORCE_DEGRADED_REASON,
    }


@api_router.get("/admin/health/force-degraded")
async def admin_health_force_degraded_state(_admin: dict = Depends(require_admin)):
    now = time.monotonic()
    active = _FORCE_DEGRADED_UNTIL_TS > now
    return {
        "active": active,
        "seconds_left": max(0.0, round(_FORCE_DEGRADED_UNTIL_TS - now, 1)) if active else 0.0,
        "reason": _FORCE_DEGRADED_REASON if active else "",
    }

@api_router.put("/admin/users/{user_id}")
async def admin_update_user(user_id: str, updates: dict, _admin: dict = Depends(require_admin)):
    allowed = {"role", "is_active", "bio", "avatar", "resell_markup_override", "seller_status"}
    filtered: dict = {}
    for k, v in updates.items():
        if k not in allowed:
            continue
        if k == "resell_markup_override":
            if v is None or v == "":
                filtered[k] = None  # clear override -> revert to tier-based cap
            else:
                try:
                    n = float(v)
                    if n < 0 or n > 500:
                        raise HTTPException(400, "resell_markup_override must be between 0 and 500")
                    filtered[k] = n
                except (TypeError, ValueError):
                    raise HTTPException(400, "resell_markup_override must be numeric")
        else:
            filtered[k] = v
    if not filtered:
        raise HTTPException(400, "No valid updates")
    await db.users.update_one({"id": user_id}, {"$set": filtered})
    doc = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    return UserPublic(**doc) if doc else {"ok": True}


@api_router.post("/admin/users/{user_id}/wallet-adjust")
async def admin_wallet_adjust(user_id: str, payload: dict = Body(...), _admin: dict = Depends(require_admin)):
    """Admin-driven wallet balance adjustment.

    Body: {"delta": float, "description": str, "bucket"?: "available"|"frozen"}
    Posts a signed ledger entry (`tx_type='adjustment'`) that atomically
    credits (delta > 0) or debits (delta < 0) the user's wallet. Debits
    from the available bucket are guarded so we never overdraw. Every
    adjustment produces a `wallet_txs` row + a wallet notification to the
    user for transparency.
    """
    from services import ledger as _ledger
    try:
        delta = float(payload.get("delta", 0))
    except (TypeError, ValueError):
        raise HTTPException(400, "delta must be a number")
    if delta == 0:
        raise HTTPException(400, "delta must be non-zero")
    description = (payload.get("description") or "").strip() or "Admin adjustment"
    if len(description) > 300:
        raise HTTPException(400, "description too long (max 300 chars)")
    bucket = (payload.get("bucket") or "available").strip().lower()
    if bucket not in ("available", "frozen"):
        raise HTTPException(400, "bucket must be 'available' or 'frozen'")

    target = await db.users.find_one({"id": user_id}, {"_id": 0, "id": 1, "username": 1, "wallet_balance": 1, "wallet_frozen_balance": 1})
    if not target:
        raise HTTPException(404, "User not found")

    try:
        tx = await _ledger.apply_entry(
            db,
            user_id=user_id,
            delta=delta,
            tx_type="adjustment",
            description=f"[admin:{_admin.get('username') or _admin['id']}] {description}",
            frozen=(bucket == "frozen"),
            require_available=(delta < 0 and bucket == "available"),
        )
    except _ledger.InsufficientFunds:
        raise HTTPException(400, "Insufficient available balance for debit")
    # Strip Mongo _id if the insert mutated the dict — it's not JSON-serializable.
    if isinstance(tx, dict):
        tx.pop("_id", None)

    fresh = await db.users.find_one({"id": user_id}, {"_id": 0, "wallet_balance": 1, "wallet_frozen_balance": 1}) or {}
    # Notify the user so they see the change in real time
    sign = "+" if delta > 0 else "−"
    amt_str = f"${abs(delta):.2f}"
    try:
        await notify(
            user_id,
            "wallet",
            f"Wallet adjusted by admin: {sign}{amt_str}",
            f"{description}. New available balance: ${float(fresh.get('wallet_balance', 0.0) or 0.0):.2f}.",
            "/wallet",
        )
    except Exception:
        pass

    return {
        "ok": True,
        "tx": tx,
        "wallet_balance": round(float(fresh.get("wallet_balance", 0.0) or 0.0), 2),
        "wallet_frozen_balance": round(float(fresh.get("wallet_frozen_balance", 0.0) or 0.0), 2),
    }


@api_router.post("/admin/catalog/restore-apify-only")
async def admin_restore_apify_only(payload: dict = Body(default={}), _admin: dict = Depends(require_admin)):
    """Restore the catalog to its Apify-extracted state.

    Body: {
      "protect_seller_listings": true,  // if false, also deletes seller-created rows
      "apify_original_slugs": [...],    // categories Apify extracts into. Defaults to the 10 canonical slugs.
    }

    Actions (in order):
      1. Clear `secondary_categories` on every listing (undo any cross-tag padding).
      2. Delete "orphan" listings — no `apify_asin` AND no `store_id` — since those
         were rebalance clones, not real Apify content.
      3. Delete listings whose primary `category_id` points at a category not in
         `apify_original_slugs`, and drop those categories from the catalog too.
      4. Delete any remaining category that has zero active listings.
    Idempotent: re-running produces zero further changes once catalog is clean.
    """
    protect_seller = bool(payload.get("protect_seller_listings", True))
    default_slugs = ["women", "men", "kids", "electronics", "home", "beauty",
                     "sports", "toys", "books", "handmade"]
    apify_slugs = set(payload.get("apify_original_slugs") or default_slugs)

    # 1) Clear secondary_categories on all
    upd = await db.listings.update_many({}, {"$set": {"secondary_categories": []}})

    # 2) Delete orphan rebalance clones
    orphan_query = {"$and": [
        {"$or": [{"apify_asin": None}, {"apify_asin": {"$exists": False}}]},
    ]}
    if protect_seller:
        orphan_query["$and"].append(
            {"$or": [{"store_id": None}, {"store_id": {"$exists": False}}]}
        )
    orphans_deleted = (await db.listings.delete_many(orphan_query)).deleted_count

    # 3) Drop non-Apify-original categories (and their listings)
    cats = await db.categories.find({}, {"_id": 0}).to_list(200)
    dropped_cats: list = []
    exotic_listings_deleted = 0
    for c in cats:
        if c.get("slug") not in apify_slugs:
            r = await db.listings.delete_many({"category_id": c["id"]})
            exotic_listings_deleted += r.deleted_count
            await db.categories.delete_one({"id": c["id"]})
            dropped_cats.append(c.get("slug"))

    # 4) Remove any category still empty (defensive — should be none after step 3)
    remaining_cats = await db.categories.find({}, {"_id": 0}).to_list(200)
    empty_removed: list = []
    kept_counts: dict = {}
    for c in remaining_cats:
        n = await db.listings.count_documents({"status": "active", "category_id": c["id"]})
        if n == 0:
            await db.categories.delete_one({"id": c["id"]})
            empty_removed.append(c.get("slug"))
        else:
            kept_counts[c.get("slug")] = n

    return {
        "ok": True,
        "secondary_categories_cleared": upd.modified_count,
        "orphan_listings_deleted": orphans_deleted,
        "exotic_categories_dropped": dropped_cats,
        "exotic_listings_deleted": exotic_listings_deleted,
        "empty_categories_removed": empty_removed,
        "final_counts": kept_counts,
        "total_active_listings": sum(kept_counts.values()),
    }


@api_router.post("/admin/listings/rebalance")
async def admin_rebalance_listings(payload: dict = Body(default={}), _admin: dict = Depends(require_admin)):
    """Re-classify every listing with the keyword classifier and, optionally,
    top-up empty/thin categories with copies of well-fitting listings so
    every catalog category has at least `min_per_category` items.

    Body: {
      "min_per_category": 20,     // optional — 0 disables the top-up pass
      "clear_sync_flag": true     // resets a stuck sync_running=true
    }

    Idempotency: this endpoint is safe to run repeatedly. Reclassification
    only writes when the computed primary/secondary differs from the stored
    values. Top-up adds sparse category ids to donor listings'
    `secondary_categories` instead of cloning — so the same rebalance twice
    creates zero duplicates.
    """
    from services.category_classifier import classify as _classify
    from collections import Counter

    min_per_cat = int(payload.get("min_per_category", 20))
    clear_sync = bool(payload.get("clear_sync_flag", True))

    cats = await db.categories.find({}, {"_id": 0}).to_list(200)
    if not cats:
        raise HTTPException(400, "No categories exist to rebalance into")
    cats_by_slug = {c["slug"]: c for c in cats}
    cats_by_id = {c["id"]: c for c in cats}
    unique_slugs = list(cats_by_slug.keys())
    fallback_pool = [s for s in unique_slugs if s != "other"] or unique_slugs

    listings = await db.listings.find(
        {"status": "active"},
        {
            "_id": 0, "id": 1, "title": 1, "description": 1, "brand": 1,
            "category_id": 1, "category_name": 1, "secondary_categories": 1,
        },
    ).sort("id", 1).to_list(20000)

    from pymongo import UpdateOne
    import hashlib as _hl

    reclassified = 0
    new_primary: Counter = Counter()
    update_ops: list = []
    for l in listings:
        pseudo = {
            "title": l.get("title") or "",
            "description": l.get("description") or "",
            "brand": l.get("brand") or "",
            "category": l.get("category_name") or "",
        }
        matched = _classify(pseudo, unique_slugs)
        if matched:
            primary = matched[0]
            computed_secondary = matched[1:]
        else:
            # Deterministic fallback: keep the listing's existing primary if it
            # still points at a valid slug (avoids drift on repeated runs). Only
            # if the current primary is unknown / missing do we pick a bucket —
            # and we pick it from a stable hash of the listing id so the same
            # listing always lands in the same fallback slot.
            existing_primary_slug = None
            existing_cid = l.get("category_id")
            if existing_cid and existing_cid in cats_by_id:
                existing_primary_slug = cats_by_id[existing_cid]["slug"]
            if existing_primary_slug and existing_primary_slug in cats_by_slug:
                primary = existing_primary_slug
            else:
                h = int(_hl.sha1((l.get("id") or "").encode("utf-8")).hexdigest(), 16)
                primary = fallback_pool[h % len(fallback_pool)]
            computed_secondary = []
        primary_cat = cats_by_slug.get(primary) or cats_by_slug.get("other") or cats[0]
        computed_secondary_ids = [
            cats_by_slug[s]["id"] for s in computed_secondary
            if s in cats_by_slug and cats_by_slug[s]["id"] != primary_cat["id"]
        ]
        new_primary[primary] += 1

        # Merge with any manually-added secondary tags already on the listing
        # (e.g. from a previous top-up pass) — dedupe, drop the new primary.
        existing_secondary = list(l.get("secondary_categories") or [])
        merged_secondary_ids: List[str] = []
        for cid in computed_secondary_ids + existing_secondary:
            if cid == primary_cat["id"]:
                continue
            if cid in cats_by_id and cid not in merged_secondary_ids:
                merged_secondary_ids.append(cid)

        old_primary_id = l.get("category_id")
        primary_changed = old_primary_id != primary_cat["id"]
        secondary_changed = set(existing_secondary) != set(merged_secondary_ids)
        if primary_changed or secondary_changed:
            update_ops.append(UpdateOne(
                {"id": l["id"]},
                {"$set": {
                    "category_id": primary_cat["id"],
                    "category_name": primary_cat["name"],
                    "secondary_categories": merged_secondary_ids,
                }},
            ))
            reclassified += 1

    if update_ops:
        await db.listings.bulk_write(update_ops, ordered=False)

    # Top-up sparse categories by TAGGING existing listings — no duplicates.
    # This is naturally idempotent: re-running with the same threshold finds
    # zero deficit because tagged listings already count via secondary_categories.
    listings_tagged = 0
    per_cat_after: dict = {}
    if min_per_cat > 0:
        active_total = await db.listings.count_documents({"status": "active"})
        if active_total >= min_per_cat:
            for slug, cat in cats_by_slug.items():
                current = await db.listings.count_documents({
                    "status": "active",
                    "$or": [{"category_id": cat["id"]}, {"secondary_categories": cat["id"]}],
                })
                deficit = min_per_cat - current
                if deficit <= 0:
                    per_cat_after[slug] = current
                    continue
                # Pick random donors that aren't already tagged with this category
                donors = await db.listings.aggregate([
                    {"$match": {
                        "status": "active",
                        "category_id": {"$ne": cat["id"]},
                        "secondary_categories": {"$ne": cat["id"]},
                    }},
                    {"$sample": {"size": deficit}},
                    {"$project": {"_id": 0, "id": 1}},
                ]).to_list(deficit)
                if donors:
                    await db.listings.update_many(
                        {"id": {"$in": [d["id"] for d in donors]}},
                        {"$addToSet": {"secondary_categories": cat["id"]}},
                    )
                    listings_tagged += len(donors)
                per_cat_after[slug] = current + len(donors)

    if clear_sync:
        await db.sync_state.update_one(
            {"id": "apify"},
            {"$set": {"sync_running": False, "message": "Cleared by admin rebalance"}},
        )

    # Final counts for the response
    final_counts: dict = {}
    for cid, cat in cats_by_id.items():
        c = await db.listings.count_documents({
            "status": "active",
            "$or": [{"category_id": cid}, {"secondary_categories": cid}],
        })
        final_counts[cat["slug"]] = c

    return {
        "ok": True,
        "listings_scanned": len(listings),
        "reclassified": reclassified,
        "duplicates_created": 0,           # kept for API compat with older clients
        "listings_tagged": listings_tagged,
        "sync_flag_cleared": clear_sync,
        "counts_after": final_counts,
        "primary_distribution": dict(new_primary),
    }



@api_router.put("/me/email-prefs")
async def update_email_prefs(payload: dict = Body(...), user: dict = Depends(get_current_user)):
    """Update the current user's per-kind email opt-in map."""
    allowed = {"order", "sale", "wallet", "payout", "dispute", "system"}
    prefs = {k: bool(v) for k, v in (payload or {}).items() if k in allowed}
    if not prefs:
        raise HTTPException(400, "Provide at least one preference toggle")
    current = (user.get("email_prefs") or {})
    current.update(prefs)
    await db.users.update_one({"id": user["id"]}, {"$set": {"email_prefs": current}})
    return {"ok": True, "email_prefs": current}


@api_router.get("/admin/email/log")
async def admin_email_log(limit: int = 100, kind: Optional[str] = None,
                           _admin: dict = Depends(require_admin)):
    """List recent email attempts. Filters: `kind`. Sorted newest first."""
    q: dict = {}
    if kind:
        q["kind"] = kind
    rows = await db.email_log.find(q, {"_id": 0}).sort("sent_at", -1).to_list(min(500, max(1, limit)))
    for r in rows:
        if isinstance(r.get("sent_at"), datetime):
            r["sent_at"] = r["sent_at"].isoformat()
    return {"items": rows, "count": len(rows)}


@api_router.post("/admin/email/test")
async def admin_email_test(payload: dict = Body(...), _admin: dict = Depends(require_admin)):
    """Send a test email to any address so admins can verify the Hostinger
    SMTP pipeline is live. Returns the provider result."""
    to = (payload.get("to") or "").strip()
    if "@" not in to:
        raise HTTPException(400, "Provide a valid `to` email address")
    from services import mailer
    from services.email_templates import welcome as tpl
    subject, html = tpl(to.split("@")[0])
    result = await mailer.send_email(
        to=to, subject=f"[test] {subject}", html=html, tags=["admin_test"],
    )
    await db.email_log.insert_one({
        "kind": "admin_test", "to": to, "provider": result.get("provider"),
        "ok": result.get("ok"), "error": result.get("error"),
        "sent_at": datetime.now(timezone.utc),
    })
    return {
        "configured": mailer.is_configured(),
        **result,
    }


@api_router.post("/admin/users/{user_id}/unlock")
async def admin_unlock_user(user_id: str, _admin: dict = Depends(require_admin)):
    """Clear a soft-locked account so the user can sign in again. Resets
    `failed_login_attempts` and `locked_until` and stamps an audit note."""
    exists = await db.users.find_one({"id": user_id}, {"_id": 0, "id": 1, "username": 1})
    if not exists:
        raise HTTPException(404, "User not found")
    await db.users.update_one(
        {"id": user_id},
        {"$set": {
            "failed_login_attempts": 0,
            "locked_until": None,
            "unlocked_at": datetime.now(timezone.utc),
            "unlocked_by_admin_id": _admin["id"],
        }},
    )
    return {"ok": True, "user_id": user_id, "username": exists.get("username")}


@api_router.post("/admin/users/{user_id}/reset-password")
async def admin_reset_user_password(
    user_id: str,
    payload: dict,
    _admin: dict = Depends(require_admin),
):
    """Directly overwrite a user's password (admin-only). This is the escape
    hatch for the `every account should be able to log in` requirement — when
    a user has lost access to their email or to the /auth/forgot-password
    flow, an admin can hand them a fresh temporary password.

    Body: `{ "new_password": "MinLen6" }`
    Side effects: clears `failed_login_attempts` + `locked_until`, so the
    account is immediately usable. Stamps `password_reset_by_admin_id`
    for audit.
    """
    new_password = (payload.get("new_password") or "").strip()
    if len(new_password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")
    exists = await db.users.find_one({"id": user_id}, {"_id": 0, "id": 1, "username": 1, "email": 1})
    if not exists:
        raise HTTPException(404, "User not found")
    await db.users.update_one(
        {"id": user_id},
        {"$set": {
            "password_hash": hash_password(new_password),
            "failed_login_attempts": 0,
            "locked_until": None,
            "password_updated_at": datetime.now(timezone.utc),
            "password_reset_by_admin_id": _admin["id"],
            # Force the user to pick their own password on next login.
            "must_change_password": True,
        }},
    )
    return {
        "ok": True,
        "user_id": user_id,
        "email": exists.get("email"),
        "username": exists.get("username"),
        "must_change_password": True,
    }


@api_router.post("/admin/users/bulk-password-reset")
async def admin_bulk_password_reset(
    payload: dict,
    _admin: dict = Depends(require_admin),
):
    """Bulk password recovery for legacy accounts. Two modes:

    - `mode="temp"` (default): overwrite the target users' password with the
      supplied `temp_password` (min 6 chars) and set `must_change_password=True`.
      Returns the count of affected accounts and the temp credential so the
      admin can share it.
    - `mode="email"`: create a fresh `/auth/reset-password` token per target
      user and dispatch the standard password-reset email. Users click the
      link to pick their own new credential. Returns { emailed, skipped }.

    Target filter (JSON body):
      - `all_non_admin`: bool — every non-admin account
      - `only_missing_hash`: bool — only accounts with no password_hash yet
      - `user_ids`: list[str] — explicit id list (takes precedence over flags)
    """
    import secrets, os, logging
    mode = (payload.get("mode") or "temp").strip().lower()
    if mode not in ("temp", "email"):
        raise HTTPException(400, "mode must be 'temp' or 'email'")

    # Build the target filter.
    if payload.get("user_ids"):
        filt = {"id": {"$in": list(payload["user_ids"])}}
    elif payload.get("only_missing_hash"):
        filt = {"$or": [
            {"password_hash": {"$exists": False}},
            {"password_hash": None},
            {"password_hash": ""},
        ], "role": {"$ne": "admin"}}
    elif payload.get("all_non_admin"):
        filt = {"role": {"$ne": "admin"}}
    else:
        raise HTTPException(400, "Specify user_ids, only_missing_hash, or all_non_admin")

    targets = await db.users.find(filt, {"_id": 0, "id": 1, "email": 1, "username": 1}).to_list(20000)
    if not targets:
        return {"ok": True, "mode": mode, "affected": 0, "targets": []}

    if mode == "temp":
        temp = (payload.get("temp_password") or "").strip()
        if len(temp) < 6:
            raise HTTPException(400, "temp_password must be at least 6 characters")
        hashed = hash_password(temp)
        ids = [t["id"] for t in targets]
        await db.users.update_many(
            {"id": {"$in": ids}},
            {"$set": {
                "password_hash": hashed,
                "failed_login_attempts": 0,
                "locked_until": None,
                "password_updated_at": datetime.now(timezone.utc),
                "password_reset_by_admin_id": _admin["id"],
                "must_change_password": True,
            }},
        )
        return {
            "ok": True,
            "mode": "temp",
            "affected": len(ids),
            "temp_password": temp,
            "note": "Share this temp password with the users. They must change it on first login.",
            "sample": [t["email"] for t in targets[:10]],
        }

    # mode == "email" — dispatch per-user reset links via existing template.
    try:
        from services import mailer
        from services.email_templates import password_reset as tpl
    except Exception as e:
        raise HTTPException(500, f"Mailer templates unavailable: {e}")

    frontend = os.environ.get("FRONTEND_ORIGIN", "").rstrip("/")
    if not frontend:
        raise HTTPException(500, "FRONTEND_ORIGIN env var not set")

    emailed = 0
    skipped = 0
    now = datetime.now(timezone.utc)
    for t in targets:
        try:
            token = secrets.token_urlsafe(32)
            await db.password_resets.insert_one({
                "token": token,
                "user_id": t["id"],
                "email": t.get("email"),
                "created_at": now,
                "expires_at": now + timedelta(hours=24),
                "used_at": None,
                "created_by_admin_id": _admin["id"],
            })
            subject, html = tpl(f"{frontend}/reset-password?token={token}", username=t.get("username"))
            await mailer.send_email(to=t["email"], subject=subject, html=html, tags=["password_reset", "bulk"])
            emailed += 1
        except Exception as e:  # noqa: BLE001
            skipped += 1
            logging.getLogger("email").warning(f"bulk_reset skip {t.get('email')}: {e}")
    return {"ok": True, "mode": "email", "affected": len(targets), "emailed": emailed, "skipped": skipped}


@api_router.delete("/admin/users/{user_id}")
async def admin_delete_user(user_id: str, _admin: dict = Depends(require_admin)):
    await db.users.delete_one({"id": user_id})
    await db.listings.delete_many({"seller_id": user_id})
    return {"ok": True}

@api_router.get("/admin/orders", response_model=List[Order])
async def admin_orders(_admin: dict = Depends(require_admin), real_only: bool = False):
    docs = await db.orders.find({}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    from utils.admin_sort import real_users_first, filter_real_only
    if real_only:
        docs = await filter_real_only(db, docs, ("buyer_id", "seller_id"))
    docs = await real_users_first(db, docs, ("buyer_id", "seller_id"))
    return [Order(**d) for d in docs]

@api_router.get("/admin/listings", response_model=List[Listing])
async def admin_listings(_admin: dict = Depends(require_admin), status_filter: Optional[str] = None):
    q = {}
    if status_filter:
        q["status"] = status_filter
    docs = await db.listings.find(q, {"_id": 0}).sort("created_at", -1).to_list(2000)
    from utils.admin_sort import real_users_first
    docs = await real_users_first(db, docs, ("seller_id",))
    # Belt-and-braces: skip any doc that fails Pydantic validation instead
    # of nuking the whole admin queue. Schema drift (e.g. a legacy
    # status='draft' row) should not hide 1,999 healthy listings.
    out: List[Listing] = []
    for d in docs:
        try:
            out.append(Listing(**d))
        except Exception as e:  # noqa: BLE001
            logging.getLogger("admin_listings").warning(
                f"skip malformed listing {d.get('id')}: {e}"
            )
    return out


# =========================
# STORES
# =========================
@api_router.post("/stores", response_model=Store)
async def create_store(payload: StoreCreate, user: dict = Depends(get_current_user)):
    if user.get("store_id"):
        raise HTTPException(400, "You already own a store")
    slug_taken = await db.stores.find_one({"slug": payload.slug.lower()})
    if slug_taken:
        raise HTTPException(400, "Slug already taken")
    if payload.category_ids and len(payload.category_ids) > 3:
        raise HTTPException(400, "Pick at most 3 categories for your store")
    settings = await get_settings()
    is_active = settings.get("store_mode", "auto") == "auto"
    store = Store(owner_id=user["id"], **{**payload.model_dump(), "slug": payload.slug.lower()}, is_active=is_active)
    await db.stores.insert_one(store.model_dump())
    await db.users.update_one({"id": user["id"]}, {"$set": {"store_id": store.id}})
    return store


async def ensure_store_for_user(user_id: str) -> Optional[dict]:
    """Auto-create a storefront for an approved seller if they don't have one yet."""
    user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not user:
        return None
    if user.get("store_id"):
        return await db.stores.find_one({"id": user["store_id"]}, {"_id": 0})

    base_slug = re.sub(r"[^a-z0-9-]+", "-", (user.get("username") or "seller").lower()).strip("-") or "seller"
    slug = base_slug
    suffix = 1
    while await db.stores.find_one({"slug": slug}, {"_id": 0, "id": 1}):
        suffix += 1
        slug = f"{base_slug}-{suffix}"
    settings = await get_settings()
    is_active = settings.get("store_mode", "auto") == "auto"
    first = (user.get("first_name") or user.get("username") or "Seller").strip()
    store = Store(
        owner_id=user_id,
        name=f"{first}'s Store" if first else "New Store",
        slug=slug,
        tagline="Curated with care",
        bio="",
        logo=user.get("avatar", ""),
        banner="",
        is_active=is_active,
    )
    await db.stores.insert_one(store.model_dump())
    await db.users.update_one({"id": user_id}, {"$set": {"store_id": store.id}})
    return store.model_dump()


@api_router.post("/stores/{slug}/follow")
async def follow_store(slug: str, user: dict = Depends(get_current_user)):
    store = await db.stores.find_one({"slug": slug.lower()}, {"_id": 0})
    if not store:
        raise HTTPException(404, "Store not found")
    if store["owner_id"] == user["id"]:
        raise HTTPException(400, "You can't follow your own store")
    existing = await db.store_follows.find_one({"store_id": store["id"], "user_id": user["id"]}, {"_id": 0})
    if existing:
        await db.store_follows.delete_one({"store_id": store["id"], "user_id": user["id"]})
        await db.stores.update_one({"id": store["id"]}, {"$inc": {"followers_count": -1}})
        following = False
    else:
        await db.store_follows.insert_one({
            "store_id": store["id"], "user_id": user["id"],
            "created_at": datetime.now(timezone.utc),
        })
        await db.stores.update_one({"id": store["id"]}, {"$inc": {"followers_count": 1}})
        following = True
    fresh = await db.stores.find_one({"id": store["id"]}, {"_id": 0, "followers_count": 1})
    return {"following": following, "followers_count": int(fresh.get("followers_count", 0) or 0)}


@api_router.get("/stores/{slug}/follow-status")
async def follow_status(slug: str, user: dict = Depends(get_current_user)):
    store = await db.stores.find_one({"slug": slug.lower()}, {"_id": 0, "id": 1, "followers_count": 1})
    if not store:
        raise HTTPException(404, "Store not found")
    existing = await db.store_follows.find_one({"store_id": store["id"], "user_id": user["id"]}, {"_id": 0, "user_id": 1})
    return {"following": bool(existing), "followers_count": int(store.get("followers_count", 0) or 0)}


async def _notify_store_followers(store_id: Optional[str], title: str, listing_id: Optional[str], bulk: bool = False):
    """Notify every follower of a store when the seller drops new inventory.
       Silent no-op if store_id is missing or has no followers. Cursor-based to scale beyond 1k followers."""
    if not store_id:
        return
    store = await db.stores.find_one({"id": store_id}, {"_id": 0, "name": 1, "slug": 1})
    if not store:
        return
    link = f"/listing/{listing_id}" if listing_id else f"/store/{store.get('slug', '')}"
    heading = f"{store.get('name', 'A store you follow')} just added new items" if bulk else f"{store.get('name', 'A store you follow')} added something new"
    async for f in db.store_follows.find({"store_id": store_id}, {"_id": 0, "user_id": 1}):
        try:
            await notify(f["user_id"], "system", heading, title, link)
        except Exception:
            pass


@api_router.get("/seller/push-stats")
async def seller_push_stats(user: dict = Depends(get_current_user)):
    """Compact Storefront Push metrics for the seller's Profile widget."""
    # Push-attributed sales as seller
    pipe = [
        {"$match": {"seller_id": user["id"], "share_ref": "push"}},
        {"$group": {
            "_id": None,
            "sales": {"$sum": 1},
            "gmv": {"$sum": "$amount"},
            "earnings": {"$sum": "$seller_earnings"},
            "last_at": {"$max": "$created_at"},
        }},
    ]
    agg = await db.orders.aggregate(pipe).to_list(1)
    sales = agg[0] if agg else {"sales": 0, "gmv": 0.0, "earnings": 0.0, "last_at": None}

    bonus_pipe = [
        {"$match": {"user_id": user["id"], "type": "bonus", "description": {"$regex": "^Storefront Push"}}},
        {"$group": {"_id": None, "count": {"$sum": 1}, "total": {"$sum": "$amount"}, "last_at": {"$max": "$created_at"}}},
    ]
    b = await db.wallet_txs.aggregate(bonus_pipe).to_list(1)
    bonuses = b[0] if b else {"count": 0, "total": 0.0, "last_at": None}

    # Followers as a proxy for share reach
    store_id = user.get("store_id")
    followers = 0
    if store_id:
        s = await db.stores.find_one({"id": store_id}, {"_id": 0, "followers_count": 1})
        followers = int((s or {}).get("followers_count", 0) or 0)

    settings = await get_settings()
    return {
        "share_reach_followers": followers,
        "share_attributed_sales": int(sales.get("sales", 0) or 0),
        "share_attributed_gmv": round(float(sales.get("gmv", 0.0) or 0.0), 2),
        "share_attributed_earnings": round(float(sales.get("earnings", 0.0) or 0.0), 2),
        "last_share_sale_at": sales.get("last_at"),
        "bonuses_count": int(bonuses.get("count", 0) or 0),
        "bonuses_total": round(float(bonuses.get("total", 0.0) or 0.0), 2),
        "last_bonus_at": bonuses.get("last_at"),
        "push_reward_amount": float(settings.get("push_reward_amount", 2.0) or 0.0),
        "eligible_for_next_bonus": int(bonuses.get("count", 0) or 0) == 0,
    }


@api_router.get("/feed/following", response_model=List[Listing])
async def followed_stores_feed(
    user: dict = Depends(get_current_user),
    limit: int = Query(20, ge=1, le=50),
):
    """Recent active listings from stores the current user follows, newest first."""
    follows = await db.store_follows.find({"user_id": user["id"]}, {"_id": 0, "store_id": 1}).to_list(500)
    store_ids = [f["store_id"] for f in follows if f.get("store_id")]
    if not store_ids:
        return []
    docs = await db.listings.find(
        {"store_id": {"$in": store_ids}, "status": "active", "seller_id": {"$ne": user["id"]}},
        {"_id": 0},
    ).sort("created_at", -1).limit(limit).to_list(limit)
    return [Listing(**d) for d in docs]

@api_router.get("/stores/{slug}", response_model=Store)
async def get_store_by_slug(slug: str):
    doc = await db.stores.find_one({"slug": slug.lower()}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Store not found")
    return Store(**doc)

@api_router.get("/stores/{slug}/listings", response_model=List[Listing])
async def get_store_listings(slug: str):
    store = await db.stores.find_one({"slug": slug.lower()}, {"_id": 0})
    if not store:
        raise HTTPException(404, "Store not found")
    # Storefront hygiene: exclude testing artefacts via the shared filter
    # (single source of truth in services/storefront_filter.py).
    from services.storefront_filter import LISTING_TEST_TITLE_RE, SELLER_TEST_USERNAME_RE
    query: dict = {
        "store_id": store["id"],
        "status": "active",
        "$nor": [
            {"title": {"$regex": LISTING_TEST_TITLE_RE, "$options": "i"}},
            {"seller_name": {"$regex": SELLER_TEST_USERNAME_RE}},
        ],
    }
    docs = await db.listings.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
    return [Listing(**d) for d in docs]


@api_router.get("/stores/{slug}/health-badge")
async def get_store_health_badge(slug: str):
    """Public badge endpoint — returns the seller's tier/score for buyers
    to see on the store header. Only shows positive tiers (`excellent`,
    `good`) publicly; anything worse returns `visible: false` so we don't
    embarrass slower sellers in front of buyers."""
    store = await db.stores.find_one({"slug": slug.lower()}, {"_id": 0, "owner_id": 1})
    if not store:
        raise HTTPException(404, "Store not found")
    # Prefer the cached score written by the nightly sweep for speed.
    owner = await db.users.find_one(
        {"id": store["owner_id"]},
        {"_id": 0, "health_tier": 1, "health_score": 1, "health_scored_at": 1},
    ) or {}
    tier = owner.get("health_tier")
    score = owner.get("health_score")
    if tier is None:
        # No cached value yet — compute on the fly (cold path only).
        h = await _compute_store_health(store["owner_id"], days=30)
        tier = h.get("tier")
        score = h.get("score")
    visible = tier in ("excellent", "good")
    return {
        "tier": tier if visible else None,
        "score": score if visible else None,
        "visible": visible,
        "label": {"excellent": "Ships fast", "good": "Reliable seller"}.get(tier),
    }

@api_router.put("/stores/{store_id}", response_model=Store)
async def update_store(store_id: str, payload: StoreUpdate, user: dict = Depends(get_current_user)):
    store = await db.stores.find_one({"id": store_id}, {"_id": 0})
    if not store:
        raise HTTPException(404, "Store not found")
    if store["owner_id"] != user["id"] and user["role"] != "admin":
        raise HTTPException(403, "Not allowed")
    if payload.category_ids is not None and len(payload.category_ids) > 3:
        raise HTTPException(400, "Pick at most 3 categories for your store")
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    # Normalize country to ISO-3166-1 alpha-2 upper-case (empty string clears it).
    if "country" in updates:
        c = (updates["country"] or "").strip().upper()
        if c and (len(c) != 2 or not c.isalpha()):
            raise HTTPException(400, "country must be a 2-letter ISO code (e.g. US, NG, GB)")
        updates["country"] = c or None
    if "website" in updates and updates["website"]:
        w = updates["website"].strip()
        if w and not w.startswith(("http://", "https://")):
            w = f"https://{w}"
        if len(w) > 300:
            raise HTTPException(400, "website URL too long")
        updates["website"] = w
    if "contact_email" in updates and updates["contact_email"]:
        e = updates["contact_email"].strip().lower()
        if "@" not in e or len(e) > 200:
            raise HTTPException(400, "contact_email must be a valid email address")
        updates["contact_email"] = e
    if updates:
        await db.stores.update_one({"id": store_id}, {"$set": updates})
    doc = await db.stores.find_one({"id": store_id}, {"_id": 0})
    return Store(**doc)

@api_router.get("/my/store", response_model=Optional[Store])
async def my_store(user: dict = Depends(get_current_user)):
    if not user.get("store_id"):
        return None
    doc = await db.stores.find_one({"id": user["store_id"]}, {"_id": 0})
    return Store(**doc) if doc else None


# =========================
# AFFILIATE LINKS
# =========================
# Affiliate + referrals routes moved to routers/affiliate.py


# =========================
# WALLET
# =========================
@api_router.get("/wallet/payout-dashboard")
async def payout_dashboard(days: int = 30, user: dict = Depends(get_current_user)):
    """Aggregated seller payout view: current balances + a per-day timeline for the
    last `days` days broken down by kind (sale_frozen, sale_released, dropship_*,
    referral, affiliate, withdrawal, refund) plus top selling listings."""
    days = max(7, min(int(days or 30), 180))
    since = datetime.now(timezone.utc) - timedelta(days=days)
    fresh = await db.users.find_one(
        {"id": user["id"]},
        {"_id": 0, "wallet_balance": 1, "wallet_frozen_balance": 1},
    ) or {}
    available = float(fresh.get("wallet_balance", 0.0))
    frozen = float(fresh.get("wallet_frozen_balance", 0.0))
    pending_wd_docs = await db.withdrawals.find(
        {"user_id": user["id"], "status": {"$in": ["pending", "approved"]}},
        {"_id": 0, "amount": 1, "status": 1, "created_at": 1},
    ).to_list(200)
    pending_withdrawals_total = round(sum(float(w.get("amount", 0.0)) for w in pending_wd_docs), 2)

    # Per-day timeline
    tx_docs = await db.wallet_txs.find(
        {"user_id": user["id"], "created_at": {"$gte": since}},
        {"_id": 0, "type": 1, "amount": 1, "created_at": 1},
    ).sort("created_at", 1).to_list(2000)

    def bucket_key(dt) -> str:
        if isinstance(dt, str):
            try:
                dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
            except Exception:
                return "unknown"
        return dt.date().isoformat()

    # Prime every day so the chart has continuous points
    timeline: dict = {}
    today = datetime.now(timezone.utc).date()
    for i in range(days, -1, -1):
        key = (today - timedelta(days=i)).isoformat()
        timeline[key] = {
            "date": key, "frozen_in": 0.0, "released": 0.0, "resell_frozen_in": 0.0,
            "resell_released": 0.0, "affiliate": 0.0, "referral": 0.0,
            "withdrawal": 0.0, "refund": 0.0, "adjustment": 0.0, "bonus": 0.0, "net": 0.0,
        }
    for t in tx_docs:
        key = bucket_key(t.get("created_at"))
        if key not in timeline:
            continue
        amt = float(t.get("amount", 0.0))
        typ = t.get("type", "")
        if typ == "sale_frozen":
            timeline[key]["frozen_in"] += amt
        elif typ in ("sale", "sale_released"):
            timeline[key]["released"] += amt
        elif typ == "dropship_frozen":
            timeline[key]["resell_frozen_in"] += amt
        elif typ in ("dropship", "dropship_released"):
            timeline[key]["resell_released"] += amt
        elif typ == "affiliate":
            timeline[key]["affiliate"] += amt
        elif typ == "referral":
            timeline[key]["referral"] += amt
        elif typ == "withdrawal":
            timeline[key]["withdrawal"] += amt  # already negative
        elif typ == "refund":
            timeline[key]["refund"] += amt
        elif typ == "adjustment":
            timeline[key]["adjustment"] += amt
        elif typ == "bonus":
            timeline[key]["bonus"] += amt
        timeline[key]["net"] += amt
    # Round each field for a clean payload
    for row in timeline.values():
        for k, v in row.items():
            if isinstance(v, float):
                row[k] = round(v, 2)
    timeline_list = list(timeline.values())

    # Totals over window
    total_earned = round(sum(r["frozen_in"] + r["released"] + r["resell_frozen_in"] + r["resell_released"] + r["affiliate"] + r["referral"] + r["refund"] + r["bonus"] for r in timeline_list), 2)
    total_released = round(sum(r["released"] + r["resell_released"] for r in timeline_list), 2)
    total_frozen_in = round(sum(r["frozen_in"] + r["resell_frozen_in"] for r in timeline_list), 2)
    total_withdrawn = round(-sum(r["withdrawal"] for r in timeline_list), 2)  # positive number

    # Top selling listings (delivered sales in window)
    top_agg = [
        {"$match": {"seller_id": user["id"], "created_at": {"$gte": since}}},
        {"$group": {
            "_id": "$listing_id",
            "title": {"$first": "$listing_title"},
            "image": {"$first": "$listing_image"},
            "sales": {"$sum": 1},
            "earnings": {"$sum": "$seller_earnings"},
        }},
        {"$sort": {"earnings": -1}},
        {"$limit": 5},
    ]
    top_listings = [
        {
            "listing_id": r["_id"], "title": r.get("title") or "",
            "image": r.get("image"), "sales": int(r.get("sales", 0)),
            "earnings": round(float(r.get("earnings", 0.0)), 2),
        }
        async for r in db.orders.aggregate(top_agg)
    ]

    # Next expected release (oldest un-released order still frozen)
    next_release_doc = await db.orders.find_one(
        {"seller_id": user["id"], "funds_released": False, "seller_earnings": {"$gt": 0}},
        {"_id": 0, "id": 1, "listing_title": 1, "seller_earnings": 1, "estimated_delivery_at": 1, "created_at": 1},
        sort=[("estimated_delivery_at", 1)],
    )

    return {
        "balances": {
            "available": round(available, 2),
            "frozen": round(frozen, 2),
            "pending_withdrawals": pending_withdrawals_total,
            "lifetime_total": round(available + frozen + pending_withdrawals_total, 2),
        },
        "window": {
            "days": days,
            "total_earned": total_earned,
            "total_released": total_released,
            "total_frozen_in": total_frozen_in,
            "total_withdrawn": total_withdrawn,
        },
        "timeline": timeline_list,
        "top_listings": top_listings,
        "next_release": next_release_doc,
        "pending_withdrawals_list": pending_wd_docs,
    }


@api_router.get("/wallet")
async def get_wallet(user: dict = Depends(get_current_user)):
    txs = await db.wallet_txs.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(200)
    pending_wd = await db.withdrawals.find({"user_id": user["id"], "status": {"$in": ["pending", "approved"]}}, {"_id": 0}).to_list(100)
    # Refresh from DB to be safe with concurrent orders
    fresh = await db.users.find_one({"id": user["id"]}, {"_id": 0, "wallet_balance": 1, "wallet_frozen_balance": 1}) or {}

    # ---- Balance Health metrics (drives the "Balance Health Tile" on /wallet)
    # In-flight orders = seller earnings frozen in escrow, waiting on delivery.
    inflight_orders = await db.orders.find(
        {"seller_id": user["id"], "funds_released": False, "seller_earnings": {"$gt": 0}},
        {"_id": 0, "id": 1, "listing_title": 1, "listing_image": 1,
         "seller_earnings": 1, "estimated_delivery_at": 1, "created_at": 1},
    ).sort("estimated_delivery_at", 1).to_list(500)

    now = datetime.now(timezone.utc)

    def _to_aware(dt):
        if dt is None:
            return None
        if isinstance(dt, str):
            try:
                dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
            except Exception:
                return None
        # Naive datetimes coming out of Mongo are treated as UTC.
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    days_in_flight_samples: List[float] = []
    for o in inflight_orders:
        created = _to_aware(o.get("created_at"))
        if created:
            days_in_flight_samples.append((now - created).total_seconds() / 86400.0)

    avg_days_in_flight = round(sum(days_in_flight_samples) / len(days_in_flight_samples), 1) if days_in_flight_samples else 0.0
    oldest_days_in_flight = round(max(days_in_flight_samples), 1) if days_in_flight_samples else 0.0

    next_release = None
    if inflight_orders:
        # Oldest ETA first (already sorted).
        first = inflight_orders[0]
        eta = _to_aware(first.get("estimated_delivery_at"))
        eta_days = round((eta - now).total_seconds() / 86400.0, 1) if eta else None
        next_release = {
            "order_id": first["id"],
            "listing_title": first.get("listing_title"),
            "listing_image": first.get("listing_image"),
            "amount": round(float(first.get("seller_earnings", 0.0)), 2),
            "estimated_delivery_at": eta.isoformat() if eta else None,
            "eta_days": eta_days,
            "overdue": (eta_days is not None and eta_days < 0),
        }

    available = round(float(fresh.get("wallet_balance", user.get("wallet_balance", 0.0))), 2)
    frozen = round(float(fresh.get("wallet_frozen_balance", 0.0)), 2)
    total_flow = available + frozen
    frozen_pct = round((frozen / total_flow) * 100, 1) if total_flow > 0 else 0.0

    health = {
        "available": available,
        "frozen": frozen,
        "frozen_pct": frozen_pct,
        "orders_in_flight": len(inflight_orders),
        "avg_days_in_flight": avg_days_in_flight,
        "oldest_days_in_flight": oldest_days_in_flight,
        "next_release": next_release,
    }
    # ---- /Balance Health metrics

    # Resolve any Reinvest-advance nested order refs into lightweight cards
    funded_order_ids: List[str] = []
    for t in txs:
        funded_order_ids.extend(t.get("funded_orders") or [])
    orders_by_id: dict = {}
    if funded_order_ids:
        for o in await db.orders.find(
            {"id": {"$in": list(set(funded_order_ids))}},
            {"_id": 0, "id": 1, "listing_title": 1, "listing_image": 1,
             "amount": 1, "quantity": 1, "status": 1,
             "reinvest_funded_amount": 1, "created_at": 1},
        ).to_list(len(funded_order_ids)):
            orders_by_id[o["id"]] = o
    return {
        "balance": fresh.get("wallet_balance", user.get("wallet_balance", 0.0)),
        "frozen_balance": fresh.get("wallet_frozen_balance", 0.0),
        "transactions": [WalletTransaction(**t).model_dump() for t in txs],
        "pending_withdrawals": [WithdrawalRequest(**w).model_dump() for w in pending_wd],
        "orders_by_id": orders_by_id,
        "health": health,
    }

@api_router.post("/wallet/withdraw", response_model=WithdrawalRequest)
async def request_withdrawal(
    payload: WithdrawalRequestCreate,
    user: dict = Depends(get_current_user),
    x_otp_token: Optional[str] = Header(None, alias="x-otp-token"),
):
    from services import email_otp as _email_otp
    try:
        await _email_otp.consume_token(db, user["id"], "withdrawal", x_otp_token)
    except ValueError as e:
        raise HTTPException(403, str(e))
    settings = await get_settings()
    min_wd = settings.get("min_withdrawal", 10.0)
    if payload.amount < min_wd:
        raise HTTPException(400, f"Minimum withdrawal is ${min_wd}")
    # Read fresh balance so we don't authorise on a stale user dict.
    fresh = await db.users.find_one(
        {"id": user["id"]}, {"_id": 0, "wallet_balance": 1}
    ) or {}
    if payload.amount > float(fresh.get("wallet_balance", 0.0) or 0.0):
        raise HTTPException(400, "Insufficient balance")

    mode = settings.get("withdrawal_mode", "manual")
    threshold = settings.get("semi_threshold", 100.0)
    initial_status = "pending"
    if mode == "auto":
        initial_status = "paid"
    elif mode == "semi" and payload.amount <= threshold:
        initial_status = "paid"

    wd = WithdrawalRequest(
        user_id=user["id"], user_name=user["username"],
        amount=payload.amount, method=payload.method, account_info=payload.account_info,
        status=initial_status,
    )
    if initial_status == "paid":
        wd.processed_at = datetime.now(timezone.utc)
    await db.withdrawals.insert_one(wd.model_dump())

    if initial_status == "paid":
        # debit wallet immediately — atomic with an available-balance guard so
        # two concurrent auto-approved withdrawals can't overdraw the user.
        try:
            await ledger.apply_entry(
                db,
                user_id=user["id"],
                delta=-payload.amount,
                tx_type="withdrawal",
                description=f"Withdrawal #{wd.id[:8]}",
                related_id=wd.id,
                require_available=True,
            )
        except ledger.InsufficientFunds:
            # Roll the request back so the withdrawal is not orphaned.
            await db.withdrawals.delete_one({"id": wd.id})
            raise HTTPException(400, "Insufficient balance")

    return wd


# =========================
# DEPOSITS (Crypto + Manual)
# =========================
@api_router.get("/wallet/payment-methods")
async def get_payment_methods(_user: dict = Depends(get_current_user)):
    """User-facing: active crypto addresses & active manual methods for deposits."""
    s = await get_settings()
    crypto = {k: v for k, v in (s.get("crypto_addresses") or {}).items() if v}
    assets = [a for a in (s.get("crypto_assets") or []) if a.get("active", True) and a.get("address")]
    manual = [m for m in (s.get("manual_payment_methods") or []) if m.get("active", True)]
    return {"crypto_addresses": crypto, "crypto_assets": assets, "manual_payment_methods": manual}


@api_router.get("/admin/settings/payment-methods")
async def admin_get_payment_methods(_admin: dict = Depends(require_admin)):
    s = await get_settings()
    return {
        "crypto_addresses": s.get("crypto_addresses") or {"BTC": "", "ETH": "", "USDC": "", "USDT": ""},
        "crypto_assets": s.get("crypto_assets") or [],
        "manual_payment_methods": s.get("manual_payment_methods") or [],
    }


@api_router.put("/admin/settings/payment-methods")
async def admin_update_payment_methods(payload: dict, _admin: dict = Depends(require_admin)):
    updates: dict = {}
    if "crypto_addresses" in payload:
        ca = payload["crypto_addresses"]
        if not isinstance(ca, dict):
            raise HTTPException(400, "crypto_addresses must be an object")
        updates["crypto_addresses"] = {str(k).upper()[:10]: str(v).strip() for k, v in ca.items()}
    if "crypto_assets" in payload:
        ca_list = payload["crypto_assets"]
        if not isinstance(ca_list, list):
            raise HTTPException(400, "crypto_assets must be a list")
        clean_assets = []
        for a in ca_list:
            if not isinstance(a, dict):
                continue
            symbol = str(a.get("symbol", "")).strip().upper()[:10]
            network = str(a.get("network", "")).strip()[:24]
            if not symbol or not network:
                continue
            clean_assets.append({
                "id": str(a.get("id") or f"{symbol.lower()}_{network.lower().replace('-', '').replace(' ', '')}"),
                "symbol": symbol,
                "network": network,
                "address": str(a.get("address", "")).strip()[:200],
                "active": bool(a.get("active", True)),
            })
        updates["crypto_assets"] = clean_assets
    if "manual_payment_methods" in payload:
        mpm = payload["manual_payment_methods"]
        if not isinstance(mpm, list):
            raise HTTPException(400, "manual_payment_methods must be a list")
        clean = []
        for m in mpm:
            if not isinstance(m, dict):
                continue
            name = str(m.get("name", "")).strip()
            if not name:
                continue
            clean.append({
                "id": str(m.get("id") or uuid.uuid4().hex[:10]),
                "name": name[:120],
                "instructions": str(m.get("instructions", "")).strip()[:2000],
                "icon": str(m.get("icon", "")).strip()[:60],
                "active": bool(m.get("active", True)),
            })
        updates["manual_payment_methods"] = clean
    if not updates:
        raise HTTPException(400, "Nothing to update")
    updates["updated_at"] = datetime.now(timezone.utc)
    await db.settings.update_one({"id": "global"}, {"$set": updates}, upsert=True)
    return await admin_get_payment_methods(_admin=_admin)


@api_router.get("/admin/wallet/audit")
async def admin_wallet_audit(_admin: dict = Depends(require_admin), limit: int = 500):
    """List users whose current `wallet_balance` drifted from the sum of their
    ledger entries in `wallet_txs`. Returns the top |drift| first so admins
    can spot problems fast.
    """
    limit = max(10, min(int(limit or 500), 2000))
    # 1) Ledger totals per user (available bucket only). Uses the explicit
    #    `bucket` tag written by ledger.apply_entry (backfilled at startup
    #    for legacy rows). Filtering by type would double-count sale_released
    #    (frozen debit + available credit share the same type).
    pipeline = [
        {"$match": {"$expr": {"$ne": [{"$ifNull": ["$bucket", "available"]}, "frozen"]}}},
        {"$group": {"_id": "$user_id", "expected": {"$sum": "$amount"}}},
    ]
    ledger_rows = await db.wallet_txs.aggregate(pipeline).to_list(10_000)
    ledger_by_uid = {r["_id"]: round(float(r["expected"]), 2) for r in ledger_rows}

    # 2) Pull user snapshots for the affected + everyone with a non-zero balance.
    user_ids = set(ledger_by_uid.keys())
    users = await db.users.find(
        {"$or": [
            {"id": {"$in": list(user_ids)}},
            {"wallet_balance": {"$gt": 0}},
        ]},
        {"_id": 0, "id": 1, "username": 1, "email": 1, "role": 1,
         "wallet_balance": 1, "wallet_frozen_balance": 1},
    ).to_list(10_000)

    audit = []
    for u in users:
        current = round(float(u.get("wallet_balance", 0.0)), 2)
        expected = ledger_by_uid.get(u["id"], 0.0)
        drift = round(current - expected, 2)
        if abs(drift) < 0.01:
            continue
        audit.append({
            "user_id": u["id"],
            "username": u.get("username"),
            "email": u.get("email"),
            "role": u.get("role"),
            "current_balance": current,
            "expected_balance": expected,
            "drift": drift,
            "frozen_balance": round(float(u.get("wallet_frozen_balance", 0.0)), 2),
        })

    audit.sort(key=lambda r: abs(r["drift"]), reverse=True)
    return {
        "items": audit[:limit],
        "total_drifted": len(audit),
        "sum_drift": round(sum(r["drift"] for r in audit), 2),
    }


@api_router.post("/admin/wallet/reconcile/{user_id}")
async def admin_reconcile_wallet(user_id: str, _admin: dict = Depends(require_admin)):
    """Recompute a user's available balance from the wallet_txs ledger.
    Useful for reseller-earnings sync after out-of-band price updates on
    dropship-source listings, or to self-heal any drift.
    Returns {user_id, delta, balance, reconciled}."""
    exists = await db.users.find_one({"id": user_id}, {"_id": 0, "id": 1})
    if not exists:
        raise HTTPException(404, "User not found")
    try:
        return await ledger.reconcile_reseller(db, user_id=user_id)
    except ledger.LedgerError as e:
        raise HTTPException(500, str(e))


@api_router.post("/wallet/reconcile")
async def user_reconcile_wallet(user: dict = Depends(get_current_user)):
    """Users can trigger a self-reconcile on their own wallet."""
    try:
        return await ledger.reconcile_reseller(db, user_id=user["id"])
    except ledger.LedgerError as e:
        raise HTTPException(500, str(e))


async def _reinvest_quote(user: dict) -> dict:
    """Compute the seller's pending wholesale demand — how much they will
    owe (or have already fronted) to source sellers for in-progress
    dropship orders whose funds haven't been released yet.

    Returns {frozen_balance, pending_wholesale, max_reinvest} where
    max_reinvest is capped at the min of the two so sellers only unlock
    what they realistically need for open fulfillment obligations.
    """
    fresh = await db.users.find_one({"id": user["id"]}, {"_id": 0, "wallet_frozen_balance": 1}) or {}
    frozen = round(float(fresh.get("wallet_frozen_balance", 0.0) or 0.0), 2)

    settings = await get_settings()
    badge = compute_seller_badge(user)
    discounts = settings.get("resell_wholesale_discounts") or {"new": 0.0, "bronze": 5.0, "silver": 10.0, "gold": 15.0}
    discount_pct = float(discounts.get(badge, 0.0))

    # Un-fulfilled incoming orders where this user is the SELLER of a
    # dropship listing. Anything past `funds_released` no longer counts.
    orders = await db.orders.find(
        {
            "seller_id": user["id"],
            "status": {"$in": ["paid", "shipped"]},
            "funds_released": {"$ne": True},
        },
        {"_id": 0, "id": 1, "listing_id": 1, "quantity": 1, "reseller_wholesale_cost": 1,
         "reseller_paid_wholesale": 1, "unit_price": 1},
    ).to_list(500)

    if not orders:
        return {"frozen_balance": frozen, "pending_wholesale": 0.0, "max_reinvest": 0.0, "open_orders": 0}

    listing_ids = list({o["listing_id"] for o in orders})
    listings = {
        d["id"]: d for d in await db.listings.find(
            {"id": {"$in": listing_ids}, "imported_from_id": {"$ne": None}},
            {"_id": 0, "id": 1, "base_price": 1, "imported_from_id": 1},
        ).to_list(len(listing_ids))
    }

    pending = 0.0
    open_count = 0
    for o in orders:
        listing = listings.get(o["listing_id"])
        if not listing:
            continue  # not a dropship listing → no wholesale demand
        # Use recorded wholesale if we already debited it (source of truth),
        # otherwise project it from base_price × qty × (1 - discount).
        if o.get("reseller_paid_wholesale") and float(o.get("reseller_wholesale_cost") or 0) > 0:
            pending += float(o["reseller_wholesale_cost"])
        else:
            base = float(listing.get("base_price") or 0.0) * int(o.get("quantity") or 1)
            pending += round(base * (1 - discount_pct / 100.0), 2)
        open_count += 1
    pending = round(pending, 2)

    return {
        "frozen_balance": frozen,
        "pending_wholesale": pending,
        "max_reinvest": round(min(frozen, pending), 2),
        "open_orders": open_count,
    }


@api_router.get("/wallet/reinvest/quote")
async def reinvest_quote(user: dict = Depends(get_current_user)):
    return await _reinvest_quote(user)


@api_router.post("/wallet/reinvest")
async def wallet_reinvest(payload: dict = Body(...), user: dict = Depends(get_current_user)):
    """Unlock a portion of the seller's frozen balance early so they can use
    the funds to pay wholesale/inventory costs on incoming orders. The
    amount is moved from `wallet_frozen_balance` → `wallet_balance`. Both
    legs go through the unified ledger for a full audit trail.

    Body: {amount: float, order_id?: str}
    """
    try:
        amount = round(float(payload.get("amount") or 0), 2)
    except (TypeError, ValueError):
        amount = 0.0
    if amount < 1:
        raise HTTPException(400, "Enter a valid amount (≥ $1)")

    fresh = await db.users.find_one({"id": user["id"]}, {"_id": 0, "wallet_frozen_balance": 1}) or {}
    frozen = round(float(fresh.get("wallet_frozen_balance", 0.0) or 0.0), 2)
    if amount > frozen:
        raise HTTPException(400, f"Insufficient frozen balance. Available frozen ${frozen:.2f}, requested ${amount:.2f}")

    # Guardrail — cap unlock to open dropship-wholesale demand so sellers
    # only tap escrow when they actually need cash for fulfillment.
    quote = await _reinvest_quote(user)
    max_reinvest = float(quote.get("max_reinvest", 0.0))
    if max_reinvest <= 0:
        raise HTTPException(400, "You have no un-fulfilled dropship orders that need wholesale funding right now.")
    if amount > max_reinvest:
        raise HTTPException(
            400,
            f"Reinvest cap is ${max_reinvest:.2f} — the wholesale cost of your open orders. "
            f"Requested ${amount:.2f}.",
        )

    order_id = payload.get("order_id") or None
    label = f"Reinvest advance{f' for order #{str(order_id)[:8]}' if order_id else ''}"

    # Debit frozen bucket
    try:
        await ledger.apply_entry(
            db,
            user_id=user["id"],
            delta=-amount,
            tx_type="sale_released",
            description=f"[frozen→available] {label}",
            related_id=order_id,
            frozen=True,
            require_available=True,
        )
    except ledger.InsufficientFunds:
        raise HTTPException(400, "Frozen balance changed since load — refresh and try again")

    # Credit available bucket so wholesale/inventory payments can spend it.
    credit_tx = await ledger.apply_entry(
        db,
        user_id=user["id"],
        delta=amount,
        tx_type="sale_released",
        description=label,
        related_id=order_id,
    )

    # Trace the cash flow — allocate the unlocked amount FIFO across the
    # seller's open dropship orders so the UI can render a "Reinvested from
    # frozen · $X" pill on each funded row.
    remaining = amount
    settings2 = await get_settings()
    badge = compute_seller_badge(user)
    discounts = settings2.get("resell_wholesale_discounts") or {"new": 0.0, "bronze": 5.0, "silver": 10.0, "gold": 15.0}
    discount_pct = float(discounts.get(badge, 0.0))
    open_orders = await db.orders.find(
        {
            "seller_id": user["id"],
            "status": {"$in": ["paid", "shipped"]},
            "funds_released": {"$ne": True},
        },
        {"_id": 0, "id": 1, "listing_id": 1, "quantity": 1,
         "reseller_wholesale_cost": 1, "reseller_paid_wholesale": 1,
         "reinvest_funded_amount": 1, "created_at": 1},
    ).sort("created_at", 1).to_list(500)
    listing_ids = list({o["listing_id"] for o in open_orders})
    dropship_ids = {
        d["id"] for d in await db.listings.find(
            {"id": {"$in": listing_ids}, "imported_from_id": {"$ne": None}},
            {"_id": 0, "id": 1, "base_price": 1},
        ).to_list(len(listing_ids))
    }
    listing_by_id = {
        d["id"]: d for d in await db.listings.find(
            {"id": {"$in": list(dropship_ids)}},
            {"_id": 0, "id": 1, "base_price": 1},
        ).to_list(len(dropship_ids))
    } if dropship_ids else {}
    now = datetime.now(timezone.utc)
    funded_orders: List[str] = []
    for o in open_orders:
        if remaining <= 0.005:
            break
        if o["listing_id"] not in dropship_ids:
            continue
        # Wholesale cost for this order (recorded or projected)
        if o.get("reseller_paid_wholesale") and float(o.get("reseller_wholesale_cost") or 0) > 0:
            cost = float(o["reseller_wholesale_cost"])
        else:
            base = float((listing_by_id.get(o["listing_id"]) or {}).get("base_price") or 0.0) * int(o.get("quantity") or 1)
            cost = round(base * (1 - discount_pct / 100.0), 2)
        already_funded = float(o.get("reinvest_funded_amount") or 0)
        need = round(max(0.0, cost - already_funded), 2)
        if need <= 0:
            continue
        alloc = round(min(need, remaining), 2)
        await db.orders.update_one(
            {"id": o["id"]},
            {"$inc": {"reinvest_funded_amount": alloc},
             "$set": {"reinvest_funded_at": now}},
        )
        remaining = round(remaining - alloc, 2)
        funded_orders.append(o["id"])

    # Attach the funded_orders list to the credit tx so the wallet UI can
    # render an expandable trail linking each Reinvest advance to the exact
    # orders it funded.
    if credit_tx and credit_tx.get("id") and funded_orders:
        await db.wallet_txs.update_one(
            {"id": credit_tx["id"]},
            {"$set": {"funded_orders": funded_orders}},
        )

    after = await db.users.find_one({"id": user["id"]}, {"_id": 0, "wallet_balance": 1, "wallet_frozen_balance": 1}) or {}
    await notify(
        user["id"], "wallet",
        f"Reinvest — ${amount:.2f} unlocked",
        f"${amount:.2f} moved from frozen escrow to your available balance. Use it to pay wholesale on incoming orders.",
        "/wallet",
    )
    return {
        "ok": True,
        "amount": amount,
        "balance": round(float(after.get("wallet_balance", 0.0)), 2),
        "frozen_balance": round(float(after.get("wallet_frozen_balance", 0.0)), 2),
        "funded_orders": funded_orders,
        "unallocated": remaining,
    }


@api_router.get("/wallet/deposit-methods")
async def wallet_deposit_methods(_user: dict = Depends(get_current_user)):
    """Unified deposit methods feed — same admin-managed source that
    powers the Checkout Payment page (crypto addresses + manual
    payment methods). Shape matches `WalletDialogs.DepositDialog`."""
    s = await get_settings()
    # Crypto — one entry per (symbol, network) address so buyers can
    # pick the network. Falls back to the flat crypto_addresses map for
    # legacy configs.
    crypto: List[dict] = []
    assets = s.get("crypto_assets") or []
    if assets:
        for a in assets:
            if not a.get("address") or a.get("active") is False:
                continue
            crypto.append({
                "id": a.get("id") or a["symbol"],
                "currency": a["symbol"],
                "network": a.get("network", ""),
                "address": a["address"],
                "label": a.get("label") or f"{a['symbol']}{(' · ' + a['network']) if a.get('network') else ''}",
            })
    else:
        for sym, addr in (s.get("crypto_addresses") or {}).items():
            if not addr:
                continue
            crypto.append({"id": sym, "currency": sym, "network": "", "address": addr, "label": sym})

    manual: List[dict] = []
    for m in s.get("manual_payment_methods") or []:
        if m.get("active", True) is False:
            continue
        manual.append({
            "id": m.get("id"),
            "name": m.get("name", "Manual method"),
            "instructions": m.get("instructions", ""),
            "kind": m.get("kind", "bank"),
        })
    return {"crypto": crypto, "manual": manual}


@api_router.post("/wallet/deposit/pending", response_model=DepositRequest)
async def create_deposit_pending(payload: dict = Body(...), user: dict = Depends(get_current_user)):
    """Preferred deposit-submission endpoint used by the Wallet UI.
    Payload shape matches `WalletDialogs.DepositDialog.submit`.
    Accepts `method` = "crypto" | "manual" and either `currency` or
    `method_id` for the target method. Reuses the same admin-managed
    config as the Checkout Payment page."""
    try:
        amount = float(payload.get("amount") or 0)
    except (TypeError, ValueError):
        amount = 0.0
    method = str(payload.get("method") or "").lower()
    reference = str(payload.get("reference") or "").strip()
    note = str(payload.get("note") or "").strip()
    if amount < 1:
        raise HTTPException(400, "Enter a valid amount (≥ $1)")
    if method not in ("crypto", "manual"):
        raise HTTPException(400, "Invalid deposit method")
    if not reference:
        raise HTTPException(400, "Transaction reference is required")

    s = await get_settings()
    currency_or_id = ""
    if method == "crypto":
        currency = str(payload.get("currency") or "").upper()
        if not currency:
            raise HTTPException(400, "Choose a cryptocurrency")
        # Validate against admin-managed crypto_assets first, fall back to legacy map.
        assets = [a for a in (s.get("crypto_assets") or []) if a.get("active", True)]
        valid = any(a.get("symbol") == currency and a.get("address") for a in assets) \
            or bool((s.get("crypto_addresses") or {}).get(currency))
        if not valid:
            raise HTTPException(400, f"{currency} deposits are not enabled")
        currency_or_id = currency
    else:
        method_id = str(payload.get("method_id") or "")
        if not method_id:
            raise HTTPException(400, "Choose a payment method")
        match = next((m for m in (s.get("manual_payment_methods") or [])
                       if m.get("id") == method_id and m.get("active", True)), None)
        if not match:
            raise HTTPException(400, "Payment method not available")
        currency_or_id = method_id

    dep = DepositRequest(
        user_id=user["id"], user_name=user.get("username", ""),
        amount=round(amount, 2),
        method=method,
        currency=currency_or_id,
        reference=reference,
        note=note,
        screenshot_url=payload.get("screenshot_url"),
    )
    await db.deposits.insert_one(dep.model_dump())
    await notify(
        user["id"], "wallet",
        f"Deposit submitted — ${dep.amount:.2f}",
        "We're reviewing your deposit. You'll be credited once confirmed.",
        "/wallet",
    )
    return dep


@api_router.post("/wallet/deposit", response_model=DepositRequest)
async def create_deposit(payload: DepositRequestCreate, user: dict = Depends(get_current_user)):
    if not payload.amount or payload.amount <= 0:
        raise HTTPException(400, "Enter a valid amount")
    if payload.method == "crypto":
        if not payload.currency:
            raise HTTPException(400, "Choose a cryptocurrency")
        s = await get_settings()
        addr = (s.get("crypto_addresses") or {}).get(payload.currency, "")
        if not addr:
            raise HTTPException(400, f"{payload.currency} deposits are not enabled")
        if not payload.reference.strip():
            raise HTTPException(400, "Transaction hash is required for crypto deposits")
    else:
        if not payload.currency:
            raise HTTPException(400, "Choose a payment method")
        s = await get_settings()
        methods = s.get("manual_payment_methods") or []
        match = next((m for m in methods if m.get("id") == payload.currency and m.get("active", True)), None)
        if not match:
            raise HTTPException(400, "Payment method not available")

    dep = DepositRequest(
        user_id=user["id"], user_name=user.get("username", ""),
        amount=round(float(payload.amount), 2),
        method=payload.method, currency=payload.currency,
        reference=payload.reference.strip(),
        note=(payload.note or "").strip(),
        screenshot_url=payload.screenshot_url,
    )
    await db.deposits.insert_one(dep.model_dump())
    await notify(
        user["id"], "wallet",
        f"Deposit submitted — ${dep.amount:.2f}",
        "We're reviewing your deposit. You'll be credited once confirmed.",
        "/wallet",
    )
    return dep


@api_router.get("/wallet/deposits", response_model=List[DepositRequest])
async def my_deposits(user: dict = Depends(get_current_user)):
    docs = await db.deposits.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return [DepositRequest(**d) for d in docs]


@api_router.get("/admin/deposits/pending", response_model=List[DepositRequest])
async def admin_list_deposits(
    _admin: dict = Depends(require_admin),
    status_filter: Optional[str] = None,
):
    q: dict = {}
    if status_filter:
        q["status"] = status_filter
    docs = await db.deposits.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    from utils.admin_sort import real_users_first
    docs = await real_users_first(db, docs, ("user_id",))
    return [DepositRequest(**d) for d in docs]


@api_router.post("/admin/deposits/{dep_id}/approve")
async def admin_approve_deposit(dep_id: str, _admin: dict = Depends(require_admin)):
    dep = await db.deposits.find_one({"id": dep_id}, {"_id": 0})
    if not dep:
        raise HTTPException(404, "Deposit not found")
    if dep["status"] != "pending":
        raise HTTPException(400, f"Deposit is already {dep['status']}")
    await db.deposits.update_one(
        {"id": dep_id},
        {"$set": {"status": "approved", "processed_at": datetime.now(timezone.utc)}},
    )
    label = dep.get("currency") or dep.get("method", "deposit")
    await ledger.deposit_approved(
        db,
        user_id=dep["user_id"],
        amount=float(dep["amount"]),
        deposit_id=dep_id,
        label=label,
    )
    await notify(
        dep["user_id"], "wallet",
        f"Deposit approved — ${float(dep['amount']):.2f}",
        "Funds have been credited to your wallet.",
        "/wallet",
    )
    return {"ok": True, "status": "approved"}


@api_router.post("/admin/deposits/{dep_id}/reject")
async def admin_reject_deposit(dep_id: str, payload: dict = Body(default={}), _admin: dict = Depends(require_admin)):
    dep = await db.deposits.find_one({"id": dep_id}, {"_id": 0})
    if not dep:
        raise HTTPException(404, "Deposit not found")
    if dep["status"] != "pending":
        raise HTTPException(400, f"Deposit is already {dep['status']}")
    reason = str(payload.get("reason", "")).strip()[:500]
    await db.deposits.update_one(
        {"id": dep_id},
        {"$set": {"status": "rejected", "admin_note": reason, "processed_at": datetime.now(timezone.utc)}},
    )
    await notify(
        dep["user_id"], "wallet",
        f"Deposit rejected — ${float(dep['amount']):.2f}",
        reason or "Please review the payment details and resubmit.",
        "/wallet",
    )
    return {"ok": True, "status": "rejected"}


class BulkDepositAction(BaseModel):
    ids: List[str]
    reason: Optional[str] = None  # only used for bulk reject


@api_router.post("/admin/deposits/bulk-approve")
async def admin_bulk_approve_deposits(payload: BulkDepositAction, _admin: dict = Depends(require_admin)):
    """Approve a batch of pending deposits in one call.

    Iterates sequentially so any single failure (e.g. status has already
    flipped between the queue load and the click) doesn't roll back the rest.
    Returns per-id results so the UI can badge partial successes."""
    if not payload.ids:
        raise HTTPException(400, "No deposit ids supplied")
    if len(payload.ids) > 100:
        raise HTTPException(400, "Bulk actions capped at 100 rows per call")
    results: list[dict] = []
    for dep_id in payload.ids:
        dep = await db.deposits.find_one({"id": dep_id}, {"_id": 0})
        if not dep:
            results.append({"id": dep_id, "ok": False, "error": "not_found"})
            continue
        if dep["status"] != "pending":
            results.append({"id": dep_id, "ok": False, "error": f"already_{dep['status']}"})
            continue
        await db.deposits.update_one({"id": dep_id}, {"$set": {"status": "approved", "processed_at": datetime.now(timezone.utc)}})
        label = dep.get("currency") or dep.get("method", "deposit")
        await ledger.deposit_approved(db, user_id=dep["user_id"], amount=float(dep["amount"]),
                                      deposit_id=dep_id, label=label)
        await notify(dep["user_id"], "wallet", f"Deposit approved — ${float(dep['amount']):.2f}",
                     f"Your {label} deposit has been credited to your wallet.", "/wallet")
        results.append({"id": dep_id, "ok": True})
    approved = sum(1 for r in results if r["ok"])
    return {"ok": True, "approved": approved, "total": len(payload.ids), "results": results}


@api_router.post("/admin/deposits/bulk-reject")
async def admin_bulk_reject_deposits(payload: BulkDepositAction, _admin: dict = Depends(require_admin)):
    """Reject a batch of pending deposits with one shared reason."""
    if not payload.ids:
        raise HTTPException(400, "No deposit ids supplied")
    if len(payload.ids) > 100:
        raise HTTPException(400, "Bulk actions capped at 100 rows per call")
    reason = (payload.reason or "").strip() or "Rejected in bulk review"
    results: list[dict] = []
    for dep_id in payload.ids:
        dep = await db.deposits.find_one({"id": dep_id}, {"_id": 0})
        if not dep:
            results.append({"id": dep_id, "ok": False, "error": "not_found"})
            continue
        if dep["status"] != "pending":
            results.append({"id": dep_id, "ok": False, "error": f"already_{dep['status']}"})
            continue
        await db.deposits.update_one({"id": dep_id},
                                     {"$set": {"status": "rejected", "admin_note": reason,
                                               "processed_at": datetime.now(timezone.utc)}})
        await notify(dep["user_id"], "wallet", f"Deposit rejected — ${float(dep['amount']):.2f}",
                     reason, "/wallet")
        results.append({"id": dep_id, "ok": True})
    rejected = sum(1 for r in results if r["ok"])
    return {"ok": True, "rejected": rejected, "total": len(payload.ids), "results": results}


@api_router.post("/wallet/deposits/{dep_id}/resubmit", response_model=DepositRequest)
async def resubmit_rejected_deposit(
    dep_id: str,
    payload: dict = Body(default={}),
    user: dict = Depends(get_current_user),
):
    """Buyer re-uploads a fresh screenshot (and optionally corrects the
    reference / note) for a previously **rejected** deposit. Flips the
    deposit back to `pending` so the admin queue picks it up again.
    Keeps the original amount / method / currency — those are considered
    immutable to preserve accounting trace."""
    dep = await db.deposits.find_one({"id": dep_id}, {"_id": 0})
    if not dep:
        raise HTTPException(404, "Deposit not found")
    if dep["user_id"] != user["id"]:
        raise HTTPException(403, "You can only resubmit your own deposits")
    if dep.get("status") != "rejected":
        raise HTTPException(400, f"Only rejected deposits can be resubmitted (current: {dep.get('status')})")

    updates: dict = {
        "status": "pending",
        "admin_note": "",
        "processed_at": None,
        "resubmitted_at": datetime.now(timezone.utc),
        "resubmit_count": int(dep.get("resubmit_count") or 0) + 1,
    }
    screenshot_url = (payload.get("screenshot_url") or "").strip()
    if screenshot_url:
        updates["screenshot_url"] = screenshot_url
    reference = (payload.get("reference") or "").strip()
    if reference:
        updates["reference"] = reference
    note = payload.get("note")
    if note is not None:
        updates["note"] = str(note).strip()[:500]

    # A resubmit must include either a new screenshot or a new reference —
    # otherwise the buyer is just re-sending the same info that got rejected.
    if not screenshot_url and not reference and note is None:
        raise HTTPException(400, "Attach a new screenshot or reference before resubmitting.")

    await db.deposits.update_one({"id": dep_id}, {"$set": updates})
    fresh = await db.deposits.find_one({"id": dep_id}, {"_id": 0})
    await notify(
        user["id"], "wallet",
        f"Deposit resubmitted — ${float(dep['amount']):.2f}",
        "We'll review your updated proof and credit your wallet once confirmed.",
        "/wallet",
    )
    return DepositRequest(**fresh)


# =========================
# ADMIN PAYMENT REVIEWS QUEUE
# =========================
def _sla_badge(age_min: float, thresholds: tuple[int, int, int] = (30, 120, 720)) -> dict:
    """Return an SLA severity bucket for a work item.

    Defaults (in minutes):
      * fresh     — < 30m  (green)
      * attention — 30m-2h (amber)
      * urgent    — 2h-12h (orange)
      * overdue   — > 12h  (red)
    """
    fresh, attention, urgent = thresholds
    if age_min < fresh:
        return {"tier": "fresh",     "label": "Fresh",     "color": "green",  "age_min": round(age_min, 1)}
    if age_min < attention:
        return {"tier": "attention", "label": "Attention", "color": "amber",  "age_min": round(age_min, 1)}
    if age_min < urgent:
        return {"tier": "urgent",    "label": "Urgent",    "color": "orange", "age_min": round(age_min, 1)}
    return {"tier": "overdue",       "label": "Overdue",   "color": "red",    "age_min": round(age_min, 1)}


def _minutes_since(ts) -> float:
    if not ts:
        return 0.0
    if isinstance(ts, str):
        try:
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception:
            return 0.0
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - ts).total_seconds() / 60.0)


@api_router.get("/admin/payment-reviews")
async def admin_payment_reviews(_admin: dict = Depends(require_admin)):
    """Unified inbox for admin cash-flow review work. Consolidates:

      * Pending top-up deposits (first-time submissions)
      * Resubmitted deposits (previously rejected, now re-uploaded)
      * Stuck escrow orders (funds frozen past the auto-release window)

    Every row gets an SLA badge (fresh/attention/urgent/overdue) computed from
    its age so admins can attack the oldest work first. Response is capped
    at 200 rows per section — anyone hitting that ceiling should file a
    follow-up backend task."""

    # ---- 1. Deposits (pending) split by resubmit vs first-submission ----
    dep_docs = await db.deposits.find(
        {"status": "pending"}, {"_id": 0}
    ).sort("created_at", 1).to_list(400)

    pending_deposits: list[dict] = []
    resubmitted_deposits: list[dict] = []
    for d in dep_docs:
        # For resubmits, SLA age starts from the last resubmit — admins should
        # respond fast because the user already waited once.
        anchor = d.get("resubmitted_at") if (d.get("resubmit_count") or 0) > 0 else d.get("created_at")
        age = _minutes_since(anchor)
        row = {
            "id": d["id"],
            "amount": float(d.get("amount") or 0.0),
            "method": d.get("method"),
            "currency": d.get("currency"),
            "reference": d.get("reference"),
            "note": d.get("note"),
            "user_id": d.get("user_id"),
            "user_name": d.get("user_name"),
            "screenshot_url": d.get("screenshot_url"),
            "resubmit_count": int(d.get("resubmit_count") or 0),
            "admin_note": d.get("admin_note"),
            "submitted_at": (d.get("resubmitted_at") or d.get("created_at")),
            "sla": _sla_badge(age),
            "deep_link": f"/admin/deposits/{d['id']}",
        }
        if (d.get("resubmit_count") or 0) > 0:
            resubmitted_deposits.append(row)
        else:
            pending_deposits.append(row)

    # ---- 2. Stuck escrow: paid orders whose funds haven't released. ----
    #
    # An order is "stuck" when:
    #   * fulfillment_status is `picked` or `shipped` (or `delivered` from carrier)
    #   * shipping_delivered_at is set (carrier said "delivered") AND the auto-
    #     release cutoff has passed but funds are still frozen, OR
    #   * pickup_deadline has passed and seller never accepted (seller MIA).
    #
    # We surface both flavours with distinct SLA anchors so admins can nudge
    # the right party.
    now = datetime.now(timezone.utc)
    settings = await db.settings.find_one({"id": "public"}, {"_id": 0, "release_after_hours": 1}) or {}
    release_after_h = int(settings.get("release_after_hours") or 72)
    release_cutoff = now - timedelta(hours=release_after_h)

    stuck_docs = await db.orders.find(
        {
            "status": "paid",
            "$or": [
                # Carrier-delivered but buyer never confirmed and auto-release
                # hasn't yet fired (usually a job hiccup).
                {
                    "fulfillment_status": {"$in": ["shipped", "delivered", "picked"]},
                    "shipping_delivered_at": {"$lte": release_cutoff},
                    "delivered_at": None,
                },
                # Seller never accepted a Pick & Deliver order — buyer's money
                # is trapped in escrow with no one working the pickup.
                {
                    "fulfillment_status": "pending_pickup",
                    "pickup_deadline": {"$lte": now},
                },
            ],
        },
        {
            "_id": 0, "id": 1, "buyer_id": 1, "seller_id": 1, "listing_title": 1,
            "amount": 1, "seller_earnings": 1, "fulfillment_status": 1,
            "shipping_delivered_at": 1, "pickup_deadline": 1, "created_at": 1,
        },
    ).sort("shipping_delivered_at", 1).to_list(200)

    stuck_escrow: list[dict] = []
    for o in stuck_docs:
        # Anchor age at whichever milestone should have unblocked the money.
        if o.get("fulfillment_status") == "pending_pickup":
            anchor = o.get("pickup_deadline")
            reason = "Seller missed pickup deadline"
        else:
            anchor = o.get("shipping_delivered_at")
            reason = "Delivered but buyer hasn't confirmed"
        age = _minutes_since(anchor)
        stuck_escrow.append({
            "id": o["id"],
            "listing_title": o.get("listing_title"),
            "amount": float(o.get("amount") or 0.0),
            "seller_earnings": float(o.get("seller_earnings") or 0.0),
            "buyer_id": o.get("buyer_id"),
            "seller_id": o.get("seller_id"),
            "fulfillment_status": o.get("fulfillment_status"),
            "stuck_reason": reason,
            "stuck_since": anchor,
            "sla": _sla_badge(age, thresholds=(60, 24 * 60, 72 * 60)),  # relaxed for escrow
            "deep_link": f"/admin/orders/{o['id']}",
        })

    return {
        "generated_at": now,
        "counts": {
            "pending_deposits": len(pending_deposits),
            "resubmitted_deposits": len(resubmitted_deposits),
            "stuck_escrow": len(stuck_escrow),
            "total": len(pending_deposits) + len(resubmitted_deposits) + len(stuck_escrow),
        },
        "pending_deposits": pending_deposits,
        "resubmitted_deposits": resubmitted_deposits,
        "stuck_escrow": stuck_escrow,
    }




# =========================
# DROPSHIP / IMPORT
# =========================
class ImportPayload(BaseModel):
    listing_id: str
    markup_pct: float  # percentage on top of base price

def compute_seller_badge(user: dict) -> str:
    """Auto-tier a seller based on sales_count + rating. Admin badge override
    (via user.resell_markup_override) skips this and applies a hard cap directly."""
    sales = int(user.get("sales_count", 0) or 0)
    rating = float(user.get("rating", 5.0) or 0.0)
    if sales >= 50 and rating >= 4.7:
        return "gold"
    if sales >= 20 and rating >= 4.5:
        return "silver"
    if sales >= 5 and rating >= 4.0:
        return "bronze"
    return "new"


async def resolve_max_markup(user: dict) -> tuple[float, str]:
    """Return (max_markup_pct, badge_or_override_label) for the given seller."""
    override = user.get("resell_markup_override")
    if override is not None:
        try:
            return float(override), "override"
        except Exception:
            pass
    settings = await get_settings()
    caps = settings.get("resell_markup_caps") or {"new": 25.0, "bronze": 50.0, "silver": 80.0, "gold": 120.0}
    badge = compute_seller_badge(user)
    return float(caps.get(badge, 25.0)), badge


@api_router.get("/seller/resell-info")
async def seller_resell_info(user: dict = Depends(get_current_user)):
    """What's this seller allowed to mark up an imported item by, and why?"""
    max_pct, badge = await resolve_max_markup(user)
    settings = await get_settings()
    return {
        "badge": compute_seller_badge(user),
        "applied": badge,  # "override" if admin set a manual cap, else the badge name
        "max_markup_pct": max_pct,
        "platform_fee_pct": settings.get("platform_fee_pct", 8.0),
        "resell_markup_caps": settings.get("resell_markup_caps"),
        "resell_wholesale_discounts": settings.get("resell_wholesale_discounts") or {"new": 0.0, "bronze": 5.0, "silver": 10.0, "gold": 15.0},
        "wholesale_discount_pct": float((settings.get("resell_wholesale_discounts") or {}).get(compute_seller_badge(user), 0.0)),
        "sales_count": int(user.get("sales_count", 0) or 0),
        "rating": float(user.get("rating", 5.0) or 0.0),
        "override_active": user.get("resell_markup_override") is not None,
    }


@api_router.get("/seller/resell-suggestions")
async def seller_resell_suggestions(
    user: dict = Depends(get_current_user),
    limit: int = Query(10, ge=1, le=20),
):
    """AI-curated bulk resell picks. Scores products by:
       (a) match to the seller's top categories (own listings + sales history),
       (b) popularity (likes + views),
       (c) diversity across the seller's top 3 categories,
       excluding own listings, already-imported items, and already-in-store sources.
    """
    if user.get("role") != "admin" and user.get("seller_status") != "approved":
        raise HTTPException(403, "Complete seller verification and approval to see suggestions")

    # --- (1) Compute category preference weights from seller history ---
    cat_weights: dict = {}
    async for l in db.listings.find({"seller_id": user["id"], "status": "active"}, {"_id": 0, "category_id": 1, "category_name": 1}):
        cid = l.get("category_id")
        if cid:
            cat_weights[cid] = cat_weights.get(cid, 0) + 1.0
    async for o in db.orders.find({"seller_id": user["id"], "status": {"$in": ["paid", "delivered", "completed"]}}, {"_id": 0, "listing_id": 1}):
        lst = await db.listings.find_one({"id": o["listing_id"]}, {"_id": 0, "category_id": 1})
        if lst and lst.get("category_id"):
            cat_weights[lst["category_id"]] = cat_weights.get(lst["category_id"], 0) + 2.5

    # Fallback for brand-new sellers: use catalog-wide popular categories
    fallback = False
    if not cat_weights:
        fallback = True
        popular_cats = await db.listings.aggregate([
            {"$match": {"status": "active"}},
            {"$group": {"_id": "$category_id", "count": {"$sum": 1}, "likes": {"$sum": "$likes_count"}}},
            {"$sort": {"likes": -1, "count": -1}},
            {"$limit": 4},
        ]).to_list(4)
        for pc in popular_cats:
            if pc["_id"]:
                cat_weights[pc["_id"]] = float(pc["likes"] or 0) + float(pc["count"] or 0) * 0.1

    top_cats = [c for c, _ in sorted(cat_weights.items(), key=lambda x: -x[1])[:4]]
    if not top_cats:
        return {"suggestions": [], "reason": "No suggestions yet — publish a couple of listings first.", "fallback": True, "top_categories": []}

    # --- (2) Fetch candidate products from top cats, exclude own + already imported ---
    already_source = {d["imported_from_id"] async for d in db.listings.find(
        {"seller_id": user["id"], "imported_from_id": {"$ne": None}},
        {"_id": 0, "imported_from_id": 1},
    ) if d.get("imported_from_id")}

    pool_by_cat: dict = {}
    for cid in top_cats:
        docs = await db.listings.find(
            {
                "status": "active",
                "category_id": cid,
                "seller_id": {"$ne": user["id"]},
                "imported_from_id": None,
                "id": {"$nin": list(already_source)} if already_source else {"$exists": True},
            },
            {"_id": 0, "id": 1, "title": 1, "price": 1, "images": 1, "brand": 1, "category_id": 1,
             "category_name": 1, "likes_count": 1, "views_count": 1, "created_at": 1},
        ).sort([("likes_count", -1), ("views_count", -1)]).limit(20).to_list(20)
        pool_by_cat[cid] = docs

    # --- (3) Score + weave for diversity across top 3 categories ---
    settings = await get_settings()
    discounts = settings.get("resell_wholesale_discounts") or {"new": 0.0, "bronze": 5.0, "silver": 10.0, "gold": 15.0}
    ws_pct = float(discounts.get(compute_seller_badge(user), 0.0))

    weight_sum = sum(cat_weights.values()) or 1.0
    picks: List[dict] = []
    picked_ids: set = set()
    # Round-robin across top cats to ensure diversity
    idx = 0
    while len(picks) < limit and any(pool_by_cat[c] for c in top_cats):
        cid = top_cats[idx % len(top_cats)]
        idx += 1
        pool = pool_by_cat[cid]
        while pool:
            candidate = pool.pop(0)
            if candidate["id"] in picked_ids:
                continue
            pop = float(candidate.get("likes_count", 0) or 0) * 1.0 + float(candidate.get("views_count", 0) or 0) * 0.05
            cat_score = (cat_weights.get(cid, 0.0) / weight_sum) * 100.0
            score = round(cat_score + pop, 2)
            price = float(candidate.get("price", 0) or 0)
            picks.append({
                "id": candidate["id"],
                "title": candidate.get("title", ""),
                "price": price,
                "image": (candidate.get("images") or [None])[0],
                "brand": candidate.get("brand", ""),
                "category_id": candidate.get("category_id"),
                "category_name": candidate.get("category_name", ""),
                "likes_count": int(candidate.get("likes_count", 0) or 0),
                "views_count": int(candidate.get("views_count", 0) or 0),
                "wholesale_cost": round(price * (1 - ws_pct / 100.0), 2),
                "score": score,
                "reason": _pick_reason(cid, cat_weights, candidate, fallback),
            })
            picked_ids.add(candidate["id"])
            break  # move to next cat in round-robin

    # Build human-readable summary
    cat_names = {}
    async for c in db.categories.find({"id": {"$in": top_cats}}, {"_id": 0, "id": 1, "name": 1}):
        cat_names[c["id"]] = c.get("name", "")
    friendly = [cat_names.get(c, c) for c in top_cats[:3] if cat_names.get(c)]

    if fallback:
        summary = "Trending picks to get you started — you can un-select any before publishing."
    elif len(friendly) >= 2:
        summary = f"Top-selling items in {', '.join(friendly)} — your best categories so far."
    elif friendly:
        summary = f"Top-selling items in {friendly[0]} — your best category so far."
    else:
        summary = "Curated picks based on your store activity."

    return {
        "suggestions": picks,
        "reason": summary,
        "top_categories": [{"id": c, "name": cat_names.get(c, "")} for c in top_cats[:3]],
        "wholesale_discount_pct": ws_pct,
        "fallback": fallback,
    }


def _pick_reason(cid: str, cat_weights: dict, listing: dict, fallback: bool) -> str:
    likes = int(listing.get("likes_count", 0) or 0)
    if fallback:
        if likes > 5: return f"Trending — {likes} favorites"
        return "Popular pick"
    is_top = cid == max(cat_weights, key=cat_weights.get)
    if is_top and likes >= 3:
        return f"Your top category · {likes} favorites"
    if is_top:
        return "Your top category"
    if likes >= 3:
        return f"Hot in this category · {likes} favorites"
    return "Fits your store's mix"


@api_router.post("/listings/import", response_model=Listing)
async def import_listing(payload: ImportPayload, user: dict = Depends(get_current_user)):
    # Gate: only approved sellers (or admins) can resell/import listings.
    if user.get("role") != "admin" and user.get("seller_status") != "approved":
        raise HTTPException(403, "Complete seller verification and approval to resell listings")
    # Cap by the seller's badge OR admin override; never above the global dropship_max_markup_pct.
    settings = await get_settings()
    global_cap = float(settings.get("dropship_max_markup_pct", 100.0))
    seller_cap, applied = await resolve_max_markup(user)
    max_mk = min(global_cap, seller_cap)
    if payload.markup_pct < 0 or payload.markup_pct > max_mk:
        # Neutral wording when the cap comes from an admin override so we don't leak the exact value to the seller.
        if applied == "override":
            raise HTTPException(400, "Markup exceeds your allowed cap.")
        raise HTTPException(400, f"Markup must be between 0 and {max_mk:g}% for your seller tier")
    original = await db.listings.find_one({"id": payload.listing_id, "status": "active"}, {"_id": 0})
    if not original:
        raise HTTPException(404, "Source listing not available")
    if original["seller_id"] == user["id"]:
        raise HTTPException(400, "Cannot import your own listing")
    if original.get("imported_from_id"):
        raise HTTPException(400, "Cannot import an already imported listing")
    base_price = float(original["price"])
    new_price = round(base_price * (1 + payload.markup_pct / 100.0), 2)
    # Safety net: ensure the seller has a storefront to receive the imported listing.
    store_id = user.get("store_id")
    if not store_id and user.get("role") != "admin":
        s = await ensure_store_for_user(user["id"])
        store_id = s["id"] if s else None
    imported = Listing(
        seller_id=user["id"],
        seller_name=user["username"],
        title=original["title"],
        description=original["description"] + "\n\n(Fulfilled by original seller.)",
        price=new_price,
        original_price=original.get("original_price"),
        category_id=original["category_id"],
        category_name=original["category_name"],
        condition=original["condition"],
        brand=original.get("brand", ""),
        size=original.get("size", ""),
        color=original.get("color", ""),
        images=original.get("images", []),
        shipping_paid_by=original.get("shipping_paid_by", "seller"),
        shipping_method=original.get("shipping_method", "Standard"),
        store_id=store_id,
        imported_from_id=original["id"],
        base_price=base_price,
    )
    await db.listings.insert_one(imported.model_dump())
    await _notify_store_followers(store_id, imported.title, imported.id)
    return imported


class BulkImportItem(BaseModel):
    listing_id: str
    markup_pct: float = 20.0

class BulkImportPayload(BaseModel):
    items: List[BulkImportItem]
    default_markup_pct: Optional[float] = None  # applied when an item has no markup

@api_router.post("/listings/import/bulk")
async def import_listings_bulk(payload: BulkImportPayload, user: dict = Depends(get_current_user)):
    """One-tap publish of up to 20 catalog products as reseller listings."""
    if user.get("role") != "admin" and user.get("seller_status") != "approved":
        raise HTTPException(403, "Complete seller verification and approval to resell listings")
    if not payload.items:
        raise HTTPException(400, "Select at least one product")
    if len(payload.items) > 20:
        raise HTTPException(400, "Publish up to 20 products at a time")

    settings = await get_settings()
    global_cap = float(settings.get("dropship_max_markup_pct", 100.0))
    seller_cap, applied = await resolve_max_markup(user)
    max_mk = min(global_cap, seller_cap)
    default_mk = float(payload.default_markup_pct if payload.default_markup_pct is not None else 20.0)
    default_mk = max(0.0, min(default_mk, max_mk))

    published: List[dict] = []
    skipped: List[dict] = []
    # Safety net: ensure a storefront exists so all bulk-imported items are auto-attached.
    store_id = user.get("store_id")
    if not store_id and user.get("role") != "admin":
        s = await ensure_store_for_user(user["id"])
        store_id = s["id"] if s else None
    for it in payload.items:
        mk = float(it.markup_pct if it.markup_pct is not None else default_mk)
        if mk < 0 or mk > max_mk:
            skipped.append({"listing_id": it.listing_id, "reason": "markup_exceeds_cap"}); continue
        original = await db.listings.find_one({"id": it.listing_id, "status": "active"}, {"_id": 0})
        if not original:
            skipped.append({"listing_id": it.listing_id, "reason": "not_found_or_inactive"}); continue
        if original["seller_id"] == user["id"]:
            skipped.append({"listing_id": it.listing_id, "reason": "own_listing"}); continue
        if original.get("imported_from_id"):
            skipped.append({"listing_id": it.listing_id, "reason": "already_imported"}); continue
        # Avoid re-importing the same source into this seller's store
        dup = await db.listings.find_one(
            {"seller_id": user["id"], "imported_from_id": original["id"], "status": "active"},
            {"_id": 0, "id": 1},
        )
        if dup:
            skipped.append({"listing_id": it.listing_id, "reason": "already_in_your_store"}); continue

        base_price = float(original["price"])
        new_price = round(base_price * (1 + mk / 100.0), 2)
        imported = Listing(
            seller_id=user["id"],
            seller_name=user["username"],
            title=original["title"],
            description=original["description"] + "\n\n(Fulfilled by original seller.)",
            price=new_price,
            original_price=original.get("original_price"),
            category_id=original["category_id"],
            category_name=original["category_name"],
            condition=original["condition"],
            brand=original.get("brand", ""),
            size=original.get("size", ""),
            color=original.get("color", ""),
            images=original.get("images", []),
            shipping_paid_by=original.get("shipping_paid_by", "seller"),
            shipping_method=original.get("shipping_method", "Standard"),
            store_id=store_id,
            imported_from_id=original["id"],
            base_price=base_price,
        )
        await db.listings.insert_one(imported.model_dump())
        published.append({"id": imported.id, "title": imported.title, "price": imported.price, "markup_pct": mk})

    if published and store_id:
        await _notify_store_followers(store_id, f"{len(published)} new items", None, bulk=True)

    return {"published_count": len(published), "skipped_count": len(skipped), "published": published, "skipped": skipped, "applied_cap": max_mk, "cap_source": applied}


# =========================
# ADMIN: Settings, Withdrawals, Stores, Affiliate
# =========================
@api_router.get("/settings/public")
async def public_settings():
    """Non-sensitive settings that anonymous users may need (buyer-facing UI)."""
    s = await get_settings()
    return {
        "delivery_days_estimate": s.get("delivery_days_estimate", 7),
        "delivery_auto_release_days": s.get("delivery_auto_release_days", 14),
        "bulk_discount_tiers": s.get("bulk_discount_tiers") or [
            {"min_qty": 5, "discount_pct": 5.0},
            {"min_qty": 10, "discount_pct": 10.0},
        ],
        "invite_only_signup": bool(s.get("invite_only_signup", False)),
    }


@api_router.get("/admin/settings")
async def admin_get_settings(_admin: dict = Depends(require_admin)):
    return await get_settings()

@api_router.put("/admin/settings")
async def admin_update_settings(updates: dict, _admin: dict = Depends(require_admin)):
    allowed = {
        "platform_fee_pct", "affiliate_commission_pct",
        "referral_l1_pct", "referral_l2_pct", "referral_l3_pct",
        "dropship_max_markup_pct", "min_withdrawal", "signup_bonus",
        "affiliate_mode", "store_mode", "withdrawal_mode", "listing_mode",
        "semi_threshold", "referral_levels_enabled", "dispute_auto_refund_threshold",
        "dispute_auto_refund_excluded_reasons",
        "delivery_days_estimate", "delivery_auto_release_days",
        "resell_markup_caps", "resell_wholesale_discounts", "push_reward_amount",
        "bulk_discount_tiers", "invite_only_signup", "legacy_bypass_enabled",
        # Feb 2026: seller pick & deliver tunables
        "pickup_deadline_hours", "pickup_reminder_hours",
    }
    filtered = {k: v for k, v in updates.items() if k in allowed}
    if "invite_only_signup" in filtered:
        filtered["invite_only_signup"] = bool(filtered["invite_only_signup"])
    if "legacy_bypass_enabled" in filtered:
        filtered["legacy_bypass_enabled"] = bool(filtered["legacy_bypass_enabled"])
    # Validate pickup tunables — deadline 1-168h (1 week max), reminders 1-72h.
    if "pickup_deadline_hours" in filtered:
        try:
            v = int(filtered["pickup_deadline_hours"])
            if not (1 <= v <= 168):
                raise ValueError
            filtered["pickup_deadline_hours"] = v
        except (TypeError, ValueError):
            raise HTTPException(400, "pickup_deadline_hours must be an int in [1, 168]")
    if "pickup_reminder_hours" in filtered:
        raw = filtered["pickup_reminder_hours"]
        if not isinstance(raw, list):
            raise HTTPException(400, "pickup_reminder_hours must be a list of ints (hours before deadline)")
        try:
            cleaned = sorted({int(h) for h in raw if 1 <= int(h) <= 72}, reverse=True)
        except (TypeError, ValueError):
            raise HTTPException(400, "pickup_reminder_hours entries must be ints in [1, 72]")
        filtered["pickup_reminder_hours"] = cleaned
    # Sanitize the exclusion list — only accept known dispute reasons
    if "dispute_auto_refund_excluded_reasons" in filtered:
        raw = filtered["dispute_auto_refund_excluded_reasons"]
        if not isinstance(raw, list):
            raise HTTPException(400, "dispute_auto_refund_excluded_reasons must be a list")
        filtered["dispute_auto_refund_excluded_reasons"] = [
            r for r in raw if r in DISPUTE_REASONS
        ]
    filtered["updated_at"] = datetime.now(timezone.utc)
    await db.settings.update_one({"id": "global"}, {"$set": filtered}, upsert=True)
    return await get_settings()


@api_router.get("/admin/auth-audit")
async def admin_auth_audit(
    _admin: dict = Depends(require_admin),
    kind: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 200,
):
    """Legacy-bypass audit log. Returns the most recent auth_audit rows
    (default: last 200). Supports optional kind + email/user-id substring
    filters so admins can spot patterns."""
    query: dict = {}
    if kind:
        query["kind"] = kind
    if q:
        query["$or"] = [
            {"email": {"$regex": q, "$options": "i"}},
            {"user_id": q},
            {"ip": q},
        ]
    limit = max(1, min(int(limit or 200), 1000))
    docs = await db.auth_audit.find(query, {"_id": 0}).sort("at", -1).to_list(limit)
    # Count total bypass events so the UI can show a headline number
    total_bypass = await db.auth_audit.count_documents({"kind": "legacy_bypass_login"})
    return {"items": docs, "total_bypass": total_bypass}


@api_router.get("/admin/withdrawals", response_model=List[WithdrawalRequest])
async def admin_withdrawals(_admin: dict = Depends(require_admin), status_filter: Optional[str] = None):
    q = {}
    if status_filter:
        q["status"] = status_filter
    docs = await db.withdrawals.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    from utils.admin_sort import real_users_first
    docs = await real_users_first(db, docs, ("user_id",))
    return [WithdrawalRequest(**d) for d in docs]

@api_router.put("/admin/withdrawals/{wd_id}")
async def admin_process_withdrawal(wd_id: str, updates: dict, _admin: dict = Depends(require_admin)):
    wd = await db.withdrawals.find_one({"id": wd_id}, {"_id": 0})
    if not wd:
        raise HTTPException(404, "Withdrawal not found")
    new_status = updates.get("status")
    if new_status not in ("approved", "rejected", "paid"):
        raise HTTPException(400, "Invalid status")
    was_paid = wd["status"] == "paid"
    is_paid = new_status == "paid"
    set_data = {"status": new_status, "notes": updates.get("notes", wd.get("notes", ""))}
    if new_status in ("paid", "rejected"):
        set_data["processed_at"] = datetime.now(timezone.utc)
    await db.withdrawals.update_one({"id": wd_id}, {"$set": set_data})
    # Debit wallet on transition to paid
    if is_paid and not was_paid:
        await credit_wallet(wd["user_id"], -wd["amount"], "withdrawal", f"Withdrawal #{wd_id[:8]} approved", wd_id)
    return {"ok": True, "status": new_status}

@api_router.get("/admin/stores", response_model=List[Store])
async def admin_stores(_admin: dict = Depends(require_admin), real_only: bool = False):
    # Keep featured stores first (admin-controlled hand ordering), then float
    # real-user stores above synthetic/seeded stores within each rank tier.
    docs = await db.stores.find({}, {"_id": 0}).sort([("featured_rank", 1), ("created_at", -1)]).to_list(1000)
    from utils.admin_sort import real_users_first, filter_real_only
    if real_only:
        docs = await filter_real_only(db, docs, ("owner_id",))
        return [Store(**d) for d in docs]
    # Featured stores (rank < 9999) stay where the admin put them; only the
    # unfeatured tail gets re-sorted by real-user ownership.
    featured = [d for d in docs if int(d.get("featured_rank", 9999)) < 9999]
    tail = [d for d in docs if int(d.get("featured_rank", 9999)) >= 9999]
    tail = await real_users_first(db, tail, ("owner_id",))
    return [Store(**d) for d in (featured + tail)]

@api_router.put("/admin/stores/{store_id}")
async def admin_update_store(store_id: str, updates: dict, _admin: dict = Depends(require_admin)):
    allowed = {"verified_tier", "is_active", "name", "tagline", "featured_rank"}
    filtered = {k: v for k, v in updates.items() if k in allowed}
    if not filtered:
        raise HTTPException(400, "No valid updates")
    await db.stores.update_one({"id": store_id}, {"$set": filtered})
    doc = await db.stores.find_one({"id": store_id}, {"_id": 0})
    return Store(**doc) if doc else {"ok": True}


@api_router.post("/admin/stores/reorder")
async def admin_reorder_stores(payload: dict, _admin: dict = Depends(require_admin)):
    """Persist the drag-and-drop order for featured storefronts."""
    ids = payload.get("ids") or []
    if not isinstance(ids, list) or not ids:
        raise HTTPException(400, "Provide ids: [store_id, ...] in desired order")
    for i, sid in enumerate(ids):
        await db.stores.update_one({"id": sid}, {"$set": {"featured_rank": i}})
    return {"ok": True, "count": len(ids)}


@api_router.get("/stores-featured", response_model=List[Store])
async def public_featured_stores(limit: int = 12):
    """Public list of active stores ordered by featured_rank (admin-controlled)."""
    docs = await db.stores.find(
        {"is_active": True}, {"_id": 0}
    ).sort([("featured_rank", 1), ("created_at", -1)]).limit(max(1, min(limit, 50))).to_list(50)
    return [Store(**d) for d in docs]

@api_router.get("/admin/affiliate-links", response_model=List[AffiliateLink])
async def admin_affiliate_links(_admin: dict = Depends(require_admin)):
    docs = await db.affiliate_links.find({}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return [AffiliateLink(**d) for d in docs]


# =========================
# PHASE 2: REVIEWS
# =========================

# =========================
# Reviews / Messages / Notifications routes moved to routers/
# =========================


# =========================
# PHASE 2: STORE ANALYTICS
# =========================
@api_router.get("/store/analytics")
async def store_analytics(user: dict = Depends(get_current_user)):
    """Analytics for the current user's store (or for their listings if no store)."""
    seller_id = user["id"]
    active = await db.listings.count_documents({"seller_id": seller_id, "status": "active"})
    sold = await db.listings.count_documents({"seller_id": seller_id, "status": "sold"})
    total_views_agg = await db.listings.aggregate([
        {"$match": {"seller_id": seller_id}},
        {"$group": {"_id": None, "views": {"$sum": "$views_count"}, "likes": {"$sum": "$likes_count"}}},
    ]).to_list(1)
    views = total_views_agg[0]["views"] if total_views_agg else 0
    likes = total_views_agg[0]["likes"] if total_views_agg else 0

    orders_agg = await db.orders.aggregate([
        {"$match": {"seller_id": seller_id}},
        {"$group": {"_id": None, "count": {"$sum": 1}, "revenue": {"$sum": "$amount"}, "earnings": {"$sum": "$seller_earnings"}}},
    ]).to_list(1)
    order_count = orders_agg[0]["count"] if orders_agg else 0
    revenue = orders_agg[0]["revenue"] if orders_agg else 0
    earnings = orders_agg[0].get("earnings", 0) if orders_agg else 0

    reviews_agg = await db.reviews.aggregate([
        {"$match": {"seller_id": seller_id}},
        {"$group": {"_id": None, "avg": {"$avg": "$rating"}, "count": {"$sum": 1}}},
    ]).to_list(1)
    avg_rating = round(reviews_agg[0]["avg"], 2) if reviews_agg else None
    review_count = reviews_agg[0]["count"] if reviews_agg else 0

    # Top listings by views
    top = await db.listings.find({"seller_id": seller_id}, {"_id": 0, "id": 1, "title": 1, "views_count": 1, "likes_count": 1, "price": 1, "images": 1}).sort("views_count", -1).limit(5).to_list(5)

    # Sales over last 30 days
    thirty_ago = datetime.now(timezone.utc) - timedelta(days=30)
    recent_orders = await db.orders.find({"seller_id": seller_id, "created_at": {"$gte": thirty_ago}}, {"_id": 0, "created_at": 1, "amount": 1}).to_list(500)
    daily: dict = {}
    for o in recent_orders:
        d = o["created_at"].date().isoformat() if hasattr(o["created_at"], "date") else str(o["created_at"])[:10]
        daily[d] = daily.get(d, 0) + o.get("amount", 0)
    sales_series = sorted([{"date": k, "revenue": round(v, 2)} for k, v in daily.items()], key=lambda x: x["date"])

    return {
        "active_listings": active,
        "sold_listings": sold,
        "total_views": views,
        "total_likes": likes,
        "orders": order_count,
        "revenue": round(revenue, 2),
        "earnings": round(earnings, 2),
        "avg_rating": avg_rating,
        "review_count": review_count,
        "top_listings": top,
        "sales_last_30d": sales_series,
    }


class StoreDiscoveryPayload(BaseModel):
    source: Literal["category", "search", "direct"] = "direct"
    category_id: Optional[str] = None


@api_router.post("/stores/{slug}/discovery")
async def track_store_discovery(slug: str, payload: StoreDiscoveryPayload,
                                 user: Optional[dict] = Depends(get_current_user_optional)):
    """Fire-and-forget event: a buyer opened this store from a specific
    discovery surface (e.g. the category-filtered marketplace directory).
    Used by seller analytics to see which category filters send them buyers.
    """
    store = await db.stores.find_one({"slug": slug}, {"_id": 0, "id": 1, "owner_id": 1})
    if not store:
        # Return 200 so beacons never retry — silently swallow.
        return {"ok": True, "skipped": "unknown_store"}
    # Never count the owner clicking their own listing
    if user and user.get("id") == store["owner_id"]:
        return {"ok": True, "skipped": "self"}
    await db.store_discoveries.insert_one({
        "id": str(uuid.uuid4()),
        "store_id": store["id"],
        "owner_id": store["owner_id"],
        "source": payload.source,
        "category_id": payload.category_id,
        "buyer_id": (user or {}).get("id"),
        "at": datetime.now(timezone.utc),
    })
    return {"ok": True}


@api_router.get("/store/analytics/category-discoveries")
async def store_category_discoveries(days: int = 7, user: dict = Depends(get_current_user)):
    """How many buyers found the current user's store via each category filter
    over the last `days` (default 7). Owner-only.
    """
    if not user.get("store_id"):
        return {"items": [], "total": 0, "days": days}
    days = max(1, min(int(days or 7), 90))
    since = datetime.now(timezone.utc) - timedelta(days=days)
    pipeline = [
        {"$match": {
            "owner_id": user["id"],
            "source": "category",
            "at": {"$gte": since},
            "category_id": {"$ne": None},
        }},
        {"$group": {"_id": "$category_id", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    rows = await db.store_discoveries.aggregate(pipeline).to_list(50)
    cat_ids = [r["_id"] for r in rows]
    cats = {c["id"]: c for c in await db.categories.find(
        {"id": {"$in": cat_ids}}, {"_id": 0, "id": 1, "name": 1, "slug": 1}
    ).to_list(len(cat_ids))} if cat_ids else {}
    items = [
        {
            "category_id": r["_id"],
            "name": (cats.get(r["_id"]) or {}).get("name") or "Unknown",
            "slug": (cats.get(r["_id"]) or {}).get("slug"),
            "count": r["count"],
        }
        for r in rows
    ]
    return {"items": items, "total": sum(r["count"] for r in rows), "days": days}


# =========================
# APIFY SYNC (Amazon US)
# =========================
@api_router.post("/admin/sync/apify")
async def admin_sync_apify(payload: dict, _admin: dict = Depends(require_admin)):
    """Trigger Apify Amazon scrape + import. Runs in background."""
    target = int(payload.get("target_count", 30000))
    replace = bool(payload.get("replace_existing", False))
    if target < 100 or target > 50000:
        raise HTTPException(400, "target_count must be between 100 and 50000")

    state = await db.sync_state.find_one({"id": "apify"}, {"_id": 0}) or {}
    if state.get("sync_running"):
        return {"ok": True, "already_running": True}

    async def _run():
        try:
            await import_from_apify(db, target_count=target, replace_existing=replace)
        except Exception as e:
            logger.error(f"Apify sync failed: {e}")
            await db.sync_state.update_one(
                {"id": "apify"}, {"$set": {"sync_running": False, "message": f"Error: {e}"}}
            )
    asyncio.create_task(_run())
    return {"ok": True, "started": True}

@api_router.post("/admin/sync/apify/schedule")
async def admin_sync_apify_schedule(payload: dict, _admin: dict = Depends(require_admin)):
    """Toggle the weekly auto-sync or force the loop to run on the next tick.

    Payload: {enabled: bool, run_now: bool}
    - enabled=false pauses the weekly loop (loop keeps polling once per day).
    - run_now=true clears last_sync_at so the loop kicks off within a minute.
    """
    enabled = payload.get("enabled")
    run_now = bool(payload.get("run_now", False))
    updates: dict = {}
    if enabled is not None:
        updates["auto_schedule_enabled"] = bool(enabled)
    if run_now:
        # Nulling last_sync_at makes the loop treat it as "never synced" → runs asap
        updates["last_sync_at"] = None
        updates["next_scheduled_at"] = datetime.now(timezone.utc)
    if not updates:
        raise HTTPException(400, "Provide `enabled` and/or `run_now`")
    await db.sync_state.update_one({"id": "apify"}, {"$set": updates}, upsert=True)
    return {"ok": True, "updated": {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in updates.items()}}


@api_router.get("/admin/sync/status")
async def admin_sync_status(_admin: dict = Depends(require_admin)):
    return await get_sync_status(db)

@api_router.get("/sync/status")
async def public_sync_status():
    return await get_sync_status(db)


# =========================
# PHASE 1: TRUST & PAYMENTS (MOCKED)
# External services (Resend, Twilio, Stripe Connect) are MOCKED for development.
# Verification tokens are stored in the DB and returned in API responses (dev_mock=true)
# so the frontend can auto-fill them for testing.
# =========================

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)

def _gen_otp() -> str:
    # secrets is cryptographically secure — critical for OTP entropy.
    return f"{secrets.randbelow(1_000_000):06d}"

def _gen_magic_token() -> str:
    return secrets.token_urlsafe(24)

async def _create_verification_token(user_id: str, kind: str, target: str, ttl_minutes: int = 30) -> dict:
    # Invalidate previous unused tokens of same kind for the user
    await db.verification_tokens.update_many(
        {"user_id": user_id, "kind": kind, "used": False},
        {"$set": {"used": True, "attempts": 999}},
    )
    token_value = _gen_magic_token() if kind == "email" else _gen_otp()
    expires = _now_utc() + timedelta(minutes=ttl_minutes)
    doc = VerificationToken(
        user_id=user_id, kind=kind, token=token_value, target=target, expires_at=expires
    ).model_dump()
    await db.verification_tokens.insert_one(doc)
    logger.info(f"[verification] issued {kind} token for {target} user={user_id}")
    return doc


@api_router.post("/verify/email/send")
async def verify_email_send(payload: EmailSendRequest, user: dict = Depends(get_current_user)):
    """Send a real email verification magic link via Hostinger SMTP.

    Kept alongside the newer OTP flow because the /verify page still
    speaks to this endpoint. Previously this stub only logged
    `[MOCK]` and returned the token in the response — meaning no email
    ever went out. That silently broke the /verify page for real users.
    """
    if user.get("email_verified"):
        return {"ok": True, "already_verified": True}
    target_email = payload.email or user["email"]
    doc = await _create_verification_token(user["id"], "email", target_email, ttl_minutes=60)
    frontend_origin = os.environ.get("FRONTEND_ORIGIN") or os.environ.get("BACKEND_PUBLIC_URL") or ""
    verify_link_path = f"/verify?token={doc['token']}"
    absolute_link = f"{frontend_origin.rstrip('/')}{verify_link_path}" if frontend_origin else verify_link_path

    subject, html, text = None, None, None
    from services import mailer_templates
    subject, html, text = mailer_templates.verify_email(user.get("username", ""), absolute_link)
    try:
        from services import mailer
        await mailer.send_email(
            to=target_email, subject=subject, html=html, text=text,
            tags=["verify_email"],
        )
    except Exception as e:
        # Real mailer failure — invalidate the token and surface a 503 so
        # the UI doesn't show a false-positive "email sent" toast. Use 503
        # (not 502) so Cloudflare passes the JSON body through instead of
        # rewriting it into a generic HTML edge error, and so it's clearly
        # a transient origin-side issue rather than a gateway bug.
        logger.error(f"verify/email/send mailer failed for user {user['id']}: {e}")
        try:
            await db.verification_tokens.update_one(
                {"id": doc["id"]}, {"$set": {"used": True, "superseded": True}}
            )
        except Exception:
            pass
        # Detect the specific Hostinger "outbound disabled" error so we can
        # give the operator an actionable message instead of raw SMTP text.
        err_str = str(e)
        friendly = "Verification emails are temporarily unavailable. Please try again in a few minutes."
        if "Outbound sending is disabled" in err_str or "5.7.1" in err_str:
            friendly = (
                "Email sending is disabled on the server's mailbox. "
                "The site admin needs to re-enable outbound SMTP on "
                "mailsupport@blueoceansmarthub.com in Hostinger before "
                "verification emails will send."
            )
        raise HTTPException(503, friendly)

    return {
        "ok": True,
        "message": f"Verification link sent to {target_email}",
        "sent_to_email": target_email,
        "expires_at": doc["expires_at"],
    }

@api_router.post("/verify/email/confirm")
async def verify_email_confirm(payload: EmailConfirmRequest, user: dict = Depends(get_current_user)):
    doc = await db.verification_tokens.find_one(
        {"token": payload.token, "kind": "email", "user_id": user["id"]}, {"_id": 0}
    )
    if not doc:
        raise HTTPException(400, "Invalid or unknown token")
    if doc.get("used"):
        raise HTTPException(400, "Token already used")
    expires = doc["expires_at"]
    if isinstance(expires, str):
        expires = datetime.fromisoformat(expires.replace("Z", "+00:00"))
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < _now_utc():
        raise HTTPException(400, "Token expired")
    await db.verification_tokens.update_one({"id": doc["id"]}, {"$set": {"used": True}})
    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {"email_verified": True, "email_verified_at": _now_utc()}},
    )
    await notify(user["id"], "system", "Email verified", "Your email is now verified.", "/profile")
    return {"ok": True, "email_verified": True}


@api_router.post("/verify/phone/send")
async def verify_phone_send(payload: PhoneSendRequest, user: dict = Depends(get_current_user)):
    """Mocked SMS OTP. Returns the 6-digit code in response for dev use."""
    phone = (payload.phone or "").strip()
    if len(phone) < 6:
        raise HTTPException(400, "Phone number too short")
    doc = await _create_verification_token(user["id"], "phone", phone, ttl_minutes=10)
    return {
        "ok": True,
        "message": f"[MOCK] OTP sent to {phone}",
        "dev_mock": True,
        "code": doc["token"],
        "phone": phone,
        "expires_at": doc["expires_at"],
    }

@api_router.post("/verify/phone/confirm")
async def verify_phone_confirm(payload: PhoneConfirmRequest, user: dict = Depends(get_current_user)):
    phone = (payload.phone or "").strip()
    doc = await db.verification_tokens.find_one(
        {"kind": "phone", "user_id": user["id"], "target": phone, "used": False},
        {"_id": 0},
        sort=[("created_at", -1)],
    )
    if not doc:
        raise HTTPException(400, "No pending OTP for this phone")
    if doc.get("attempts", 0) >= 5:
        raise HTTPException(400, "Too many attempts. Request a new code.")
    expires = doc["expires_at"]
    if isinstance(expires, str):
        expires = datetime.fromisoformat(expires.replace("Z", "+00:00"))
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < _now_utc():
        raise HTTPException(400, "Code expired. Request a new one.")
    if payload.code.strip() != doc["token"]:
        await db.verification_tokens.update_one({"id": doc["id"]}, {"$inc": {"attempts": 1}})
        raise HTTPException(400, "Invalid code")
    await db.verification_tokens.update_one({"id": doc["id"]}, {"$set": {"used": True}})
    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {"phone": phone, "phone_verified": True, "phone_verified_at": _now_utc()}},
    )
    await notify(user["id"], "system", "Phone verified", f"Phone {phone} verified.", "/profile")
    return {"ok": True, "phone_verified": True, "phone": phone}


# ---------- Seller Application ----------
async def _compute_trust_score(user_id: str) -> dict:
    """Trust Score 0-100 with per-signal breakdown. High scores auto-approve seller applications."""
    user = await db.users.find_one({"id": user_id}, {"_id": 0}) or {}
    signals: List[dict] = []

    def add(key: str, label: str, earned: int, weight: int, hint: str = ""):
        signals.append({"key": key, "label": label, "earned": earned, "weight": weight, "hint": hint})

    add("email_verified", "Email verified",
        25 if user.get("email_verified") else 0, 25,
        "Verify your email in /verify")
    add("phone_verified", "Phone verified",
        25 if user.get("phone_verified") else 0, 25,
        "Verify your phone in /verify")

    created = user.get("created_at")
    age_days = 0
    if isinstance(created, datetime):
        # Motor returns tz-naive datetimes by default (BSON strips tzinfo). Normalize to UTC-aware
        # so the subtraction below never raises TypeError.
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        age_days = (datetime.now(timezone.utc) - created).days
    elif isinstance(created, str):
        try:
            parsed = datetime.fromisoformat(created.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            age_days = (datetime.now(timezone.utc) - parsed).days
        except ValueError:
            age_days = 0
    add("account_age", "Account age > 7 days",
        15 if age_days >= 7 else 0, 15,
        f"Account is {age_days} day(s) old")

    open_disputes = await db.disputes.count_documents(
        {"buyer_id": user_id, "status": {"$in": ["open", "reviewing"]}}
    )
    add("no_open_disputes", "No open disputes filed",
        15 if open_disputes == 0 else 0, 15,
        f"{open_disputes} open dispute(s)")

    referral_count = await db.users.count_documents({"referred_by": user_id})
    add("has_referrals", "Referred at least 1 friend",
        10 if referral_count >= 1 else 0, 10,
        f"{referral_count} referral(s)")

    profile_complete = bool((user.get("bio") or "").strip()) and bool(user.get("avatar"))
    add("profile_complete", "Complete profile (bio + avatar)",
        10 if profile_complete else 0, 10,
        "Fill your bio and add an avatar")

    # Auto-approve boost: reward applicants who completed the full email-OTP
    # flow AND supplied a phone (which is auto-verified by the seller_apply
    # endpoint). Pushes a fresh, verified applicant from 40 → 70 so pairing
    # this with `no_open_disputes` (15) crosses the 80 auto-approve line.
    verified_applicant = bool(user.get("email_verified")) and bool(user.get("phone_verified"))
    add("verified_applicant", "Verified applicant (email + phone)",
        30 if verified_applicant else 0, 30,
        "Verify your email via OTP and supply a phone number on the seller application")

    total = sum(s["earned"] for s in signals)
    max_total = sum(s["weight"] for s in signals)
    tier = "elite" if total >= 80 else "trusted" if total >= 60 else "new"
    return {
        "score": total,
        "max": max_total,
        "tier": tier,
        "auto_approve_threshold": 80,
        "auto_approve_eligible": total >= 80 and open_disputes == 0,
        "signals": signals,
    }


@api_router.get("/seller/trust-score")
async def seller_trust_score(user: dict = Depends(get_current_user)):
    """Preview the Trust Score so applicants know if they'll be fast-tracked."""
    return await _compute_trust_score(user["id"])


@api_router.post("/seller/apply", response_model=SellerApplication)
async def seller_apply(
    payload: SellerApplicationCreate,
    user: dict = Depends(get_current_user),
    x_otp_token: Optional[str] = Header(None, alias="x-otp-token"),
):
    from services import email_otp as _email_otp
    try:
        await _email_otp.consume_token(db, user["id"], "seller_apply", x_otp_token)
    except ValueError as e:
        raise HTTPException(403, str(e))
    # Email verification is the ONLY hard gate. Any other info the applicant
    # submits (phone, address, ID doc) is trusted by default so approval is
    # frictionless — the admin can still reject after review if needed.
    fresh_user = await db.users.find_one({"id": user["id"]}, {"_id": 0})
    if not fresh_user.get("email_verified"):
        raise HTTPException(400, "Please verify your email before applying")
    if fresh_user.get("seller_status") == "approved":
        raise HTTPException(400, "You are already an approved seller")

    # If the applicant supplied a phone number and hasn't manually verified
    # it, auto-mark it verified — email OTP already proved control of the
    # account, and phone is now trusted-by-default per product policy.
    submitted_phone = (payload.phone or "").strip()
    if submitted_phone and not fresh_user.get("phone_verified"):
        await db.users.update_one(
            {"id": user["id"]},
            {"$set": {
                "phone": submitted_phone,
                "phone_verified": True,
                "phone_verified_at": _now_utc(),
            }},
        )
        fresh_user["phone"] = submitted_phone
        fresh_user["phone_verified"] = True
    # If there's an existing pending app, block duplicates
    existing = await db.seller_applications.find_one(
        {"user_id": user["id"], "status": "pending"}, {"_id": 0}
    )
    if existing:
        raise HTTPException(400, "You already have a pending application")

    tax_id_last4 = (payload.tax_id or "").strip()[-4:]  # keep only last 4 digits (mock)

    # Compute trust score to decide fast-track vs manual review
    ts = await _compute_trust_score(user["id"])
    auto_approve = ts["auto_approve_eligible"]

    app_doc = SellerApplication(
        user_id=user["id"],
        user_email=user["email"],
        user_username=user["username"],
        legal_name=payload.legal_name,
        business_name=payload.business_name or "",
        business_type=payload.business_type,  # type: ignore
        tax_id=f"****{tax_id_last4}" if tax_id_last4 else "",
        country=payload.country,
        address_line1=payload.address_line1,
        address_line2=payload.address_line2 or "",
        city=payload.city,
        state=payload.state,
        postal_code=payload.postal_code,
        phone=payload.phone or fresh_user.get("phone") or "",
        payout_method=payload.payout_method,  # type: ignore
        id_document_note=payload.id_document_note or "",
        id_document_file_id=payload.id_document_file_id,
        status="approved" if auto_approve else "pending",
        admin_notes=(
            f"Auto-approved via Trust Score ({ts['score']}/{ts['max']}, tier={ts['tier']})"
            if auto_approve else ""
        ),
        reviewed_at=datetime.now(timezone.utc) if auto_approve else None,
        reviewed_by="system:trust_score" if auto_approve else None,
    )
    await db.seller_applications.insert_one(app_doc.model_dump())

    if auto_approve:
        await db.users.update_one(
            {"id": user["id"]},
            {"$set": {"seller_status": "approved", "role": "user"}},
        )
        await ensure_store_for_user(user["id"])
        await notify(
            user["id"], "system", "You're approved to sell! 🎉",
            f"Trust Score {ts['score']}/100 qualified you for instant approval. Start listing now.",
            "/sell",
        )
        # Fire branded approval email (same template as the admin-approve path).
        await _send_seller_review_email(app_doc.model_dump(), "approved", app_doc.admin_notes or "")
    else:
        await db.users.update_one({"id": user["id"]}, {"$set": {"seller_status": "pending"}})
        await notify(
            user["id"], "system", "Seller application submitted",
            f"Trust Score {ts['score']}/100 — we'll review your application shortly.",
            "/profile",
        )
    return app_doc

@api_router.get("/seller/application", response_model=Optional[SellerApplication])
async def my_seller_application(user: dict = Depends(get_current_user)):
    doc = await db.seller_applications.find_one(
        {"user_id": user["id"]}, {"_id": 0}, sort=[("created_at", -1)]
    )
    return SellerApplication(**doc) if doc else None


# ---------- Stripe Connect (removed) ----------
# The Stripe integration was removed to simplify the app for launch.
# The `stripe_account_id` / `stripe_status` user fields are kept as
# harmless legacy so any existing DB rows still deserialize cleanly, but
# no HTTP endpoints reference Stripe any more.


# ---------- Admin: Seller Application Queue ----------
@api_router.get("/admin/mail/resend-domains")
async def admin_resend_domains(_admin: dict = Depends(require_admin)):
    """List every domain registered on the Resend account this API key
    belongs to, plus each domain's verification status. Used by the
    Admin dashboard to confirm blueoceansmarthub.com is verified before
    we flip RESEND_FROM_ADDRESS off the onboarding@resend.dev fallback."""
    api_key = os.environ.get("RESEND_API_KEY", "")
    if not api_key:
        raise HTTPException(400, "RESEND_API_KEY not set in backend/.env")
    try:
        import resend as _resend
        _resend.api_key = api_key
        raw = await asyncio.to_thread(_resend.Domains.list)
        items = raw.get("data") if isinstance(raw, dict) else raw
        out = []
        for d in items or []:
            out.append({
                "id": d.get("id"),
                "name": d.get("name"),
                "region": d.get("region"),
                "status": d.get("status"),
                "created_at": d.get("created_at"),
                "is_verified": d.get("status") == "verified",
            })
        current_from = os.environ.get("RESEND_FROM_ADDRESS", "")
        return {
            "domains": out,
            "current_from_address": current_from,
            "current_from_is_resend_dev": current_from.endswith("@resend.dev"),
            "action_hint": (
                "Add blueoceansmarthub.com in Resend Dashboard → Domains → Add, "
                "paste the SPF + DKIM records into your Hostinger DNS, then "
                "hit this endpoint again. Once status=verified, tell me and "
                "I'll flip RESEND_FROM_ADDRESS to mailsupport@blueoceansmarthub.com."
            ),
        }
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        err = str(e)
        # The user's current API key is a "sending-only" restricted key,
        # so the Domains endpoint returns 401. Return an actionable
        # explanation instead of a raw 503 so operators know exactly
        # what to do.
        if "restricted" in err.lower() or "only send" in err.lower():
            return {
                "domains": [],
                "current_from_address": os.environ.get("RESEND_FROM_ADDRESS", ""),
                "current_from_is_resend_dev": os.environ.get("RESEND_FROM_ADDRESS", "").endswith("@resend.dev"),
                "restricted_api_key": True,
                "action_hint": (
                    "Your RESEND_API_KEY is a 'sending-only' key and can't "
                    "list domains from here. Manage domain verification "
                    "directly in the Resend Dashboard: "
                    "https://resend.com/domains → Add Domain → "
                    "blueoceansmarthub.com. Copy the SPF and DKIM records "
                    "into your Hostinger DNS panel (Domain → DNS Zone). "
                    "Once the domain shows 'Verified' in the Resend UI, "
                    "let me know and I'll flip RESEND_FROM_ADDRESS."
                ),
                "raw_error": err[:200],
            }
        raise HTTPException(503, f"Resend API lookup failed: {err}")


@api_router.get("/admin/seller-applications/{app_id}/preview-email")
async def admin_seller_app_preview_email(
    app_id: str,
    review_status: str = "approved",
    admin_notes: str = "",
    _admin: dict = Depends(require_admin),
):
    """Return the exact subject/html/text an applicant will receive if
    the admin flips their status to `review_status`. Used by the
    "Preview email" button in /admin/seller-applications so admins can
    eyeball tone, formatting, and — for rejects — how their notes
    render."""
    doc = await db.seller_applications.find_one({"id": app_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Application not found")
    if review_status not in ("approved", "rejected"):
        raise HTTPException(400, "review_status must be approved or rejected")
    from services import mailer_templates as _tpl
    username = doc.get("user_username") or doc.get("legal_name") or "there"
    notes_effective = (admin_notes or doc.get("admin_notes") or "").strip()
    if review_status == "approved":
        subject, html, text = _tpl.seller_application_approved(username)
    else:
        subject, html, text = _tpl.seller_application_rejected(username, notes_effective)
    return {
        "ok": True,
        "recipient": doc.get("user_email"),
        "status": review_status,
        "subject": subject,
        "html": html,
        "text": text,
    }


@api_router.get("/admin/seller-applications", response_model=List[SellerApplication])
async def admin_seller_apps(_admin: dict = Depends(require_admin), status_filter: Optional[str] = None):
    q: dict = {}
    if status_filter:
        q["status"] = status_filter
    docs = await db.seller_applications.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    # Resilient deserialize: skip (and log) any single doc that fails Pydantic
    # validation instead of nuking the whole admin list. Historically a legacy
    # `payout_method="stripe_connect"` row broke this endpoint until the enum
    # was widened — leave the belt-and-braces guard so future schema drift
    # can't hide the queue from admins again.
    out: List[SellerApplication] = []
    for d in docs:
        try:
            out.append(SellerApplication(**d))
        except Exception as e:  # noqa: BLE001
            logging.getLogger("seller_apps").warning(
                f"skip malformed seller_application {d.get('id')}: {e}"
            )
    # Sort real-user applications to the top of the queue.
    from utils.admin_sort import real_user_ids, _created_ts as _ts
    all_ids = [a.user_id for a in out]
    reals = await real_user_ids(db, all_ids)
    out.sort(key=lambda a: (a.user_id not in reals, -(_ts({"created_at": a.created_at}))))
    return out

@api_router.put("/admin/seller-applications/{app_id}")
async def admin_review_seller_app(app_id: str, updates: dict, admin: dict = Depends(require_admin)):
    doc = await db.seller_applications.find_one({"id": app_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Application not found")
    new_status = updates.get("status")
    if new_status not in ("approved", "rejected"):
        raise HTTPException(400, "Invalid status")
    notes = updates.get("admin_notes", doc.get("admin_notes", "")) or ""
    await db.seller_applications.update_one(
        {"id": app_id},
        {"$set": {
            "status": new_status,
            "admin_notes": notes,
            "reviewed_at": _now_utc(),
            "reviewed_by": admin["id"],
        }},
    )
    await db.users.update_one({"id": doc["user_id"]}, {"$set": {"seller_status": new_status}})
    if new_status == "approved":
        await ensure_store_for_user(doc["user_id"])
        await notify(doc["user_id"], "system", "Seller application approved",
                     "You can now sell on Ocean. Connect your payout method.", "/verify")
    else:
        await notify(doc["user_id"], "system", "Seller application rejected",
                     notes or "See admin notes.", "/profile")
    # Fire branded email — best-effort, don't block the admin's action on
    # SMTP flakiness. SuppressedRecipient / MailerError are swallowed but
    # logged for the health ticker.
    await _send_seller_review_email(doc, new_status, notes)
    return {"ok": True, "status": new_status}


async def _send_seller_review_email(app_doc: dict, new_status: str, admin_notes: str) -> None:
    """Send the applicant a branded email announcing the decision.
    Called from single-review AND bulk-review handlers. Safe on failure."""
    try:
        from services import mailer_templates as _tpl
        from services import mailer as _mailer
        user_email = app_doc.get("user_email")
        username = app_doc.get("user_username") or app_doc.get("legal_name") or ""
        if not user_email:
            return
        if new_status == "approved":
            subject, html, text = _tpl.seller_application_approved(username)
        else:
            subject, html, text = _tpl.seller_application_rejected(username, admin_notes or "")
        await _mailer.send_email(
            to=user_email,
            subject=subject, html=html, text=text,
            tags=["seller_review", new_status],
            is_transactional=True,  # account-status change — no unsubscribe.
        )
    except Exception as e:  # noqa: BLE001
        logging.getLogger("seller_review").warning(
            f"seller-review email skipped for {app_doc.get('id')}: {e}"
        )


@api_router.post("/admin/seller-applications/bulk-review")
async def admin_bulk_review_seller_apps(payload: dict, admin: dict = Depends(require_admin)):
    """Approve or reject a batch of pending seller applications in one call."""
    ids = payload.get("ids") or []
    new_status = payload.get("status")
    notes = str(payload.get("admin_notes", "")).strip()[:500]
    if new_status not in ("approved", "rejected"):
        raise HTTPException(400, "Invalid status")
    if not isinstance(ids, list) or not ids:
        raise HTTPException(400, "Select at least one application")
    if len(ids) > 100:
        raise HTTPException(400, "Review up to 100 applications at a time")

    processed = 0
    skipped: List[dict] = []
    for app_id in ids:
        doc = await db.seller_applications.find_one({"id": app_id}, {"_id": 0})
        if not doc:
            skipped.append({"id": app_id, "reason": "not_found"}); continue
        if doc.get("status") != "pending":
            skipped.append({"id": app_id, "reason": f"already_{doc.get('status')}"}); continue
        await db.seller_applications.update_one(
            {"id": app_id},
            {"$set": {
                "status": new_status,
                "admin_notes": notes,
                "reviewed_at": _now_utc(),
                "reviewed_by": admin["id"],
            }},
        )
        await db.users.update_one({"id": doc["user_id"]}, {"$set": {"seller_status": new_status}})
        if new_status == "approved":
            await ensure_store_for_user(doc["user_id"])
        if new_status == "approved":
            await notify(doc["user_id"], "system", "Seller application approved",
                         "You can now sell on Ocean. Connect your payout method.", "/verify")
        else:
            await notify(doc["user_id"], "system", "Seller application rejected",
                         notes or "See admin notes.", "/profile")
        # Branded email per applicant, safe on failure.
        await _send_seller_review_email(doc, new_status, notes)
        processed += 1
    return {"processed": processed, "skipped_count": len(skipped), "skipped": skipped, "status": new_status}


# =========================
# PHASE 2: OBJECT STORAGE (Emergent) — file upload for IDs, listing images
# =========================
def init_storage(force: bool = False) -> str:
    global _storage_key
    if _storage_key and not force:
        return _storage_key
    resp = _requests.post(f"{STORAGE_URL}/init", json={"emergent_key": EMERGENT_LLM_KEY}, timeout=30)
    resp.raise_for_status()
    _storage_key = resp.json()["storage_key"]
    return _storage_key

def put_object(path: str, data: bytes, content_type: str) -> dict:
    key = init_storage()
    resp = _requests.put(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key, "Content-Type": content_type},
        data=data,
        timeout=120,
    )
    if resp.status_code in (403, 404):
        key = init_storage(force=True)
        resp = _requests.put(
            f"{STORAGE_URL}/objects/{path}",
            headers={"X-Storage-Key": key, "Content-Type": content_type},
            data=data,
            timeout=120,
        )
    resp.raise_for_status()
    return resp.json()

def get_object(path: str):
    key = init_storage()
    resp = _requests.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key}, timeout=60)
    if resp.status_code == 404:
        key = init_storage(force=True)
        resp = _requests.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key}, timeout=60)
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")


ALLOWED_EXT = {"jpg", "jpeg", "png", "webp", "gif", "pdf"}
MAX_UPLOAD_BYTES = 12 * 1024 * 1024  # 12 MB
PUBLIC_IMAGE_EXT = {"jpg", "jpeg", "png", "webp", "gif"}


@api_router.post("/upload/public-image")
async def upload_public_image(
    file: UploadFile = File(...),
    kind: str = Form("misc"),
    user: dict = Depends(get_current_user),
):
    """Upload a publicly-viewable image (avatar / store logo / store banner).

    Unlike /upload which returns a `/api/files/{id}` URL that requires auth,
    this endpoint writes the bytes to the local media root that FastAPI
    serves at `/api/uploads/…`. The returned URL is fully-qualified and can
    be embedded directly in `<img>` tags by any visitor.
    """
    from services.r2_storage import LOCAL_ROOT, _local_public_url, r2_enabled, _r2_client, _env, _r2_public_url  # noqa: WPS437
    filename = file.filename or "image"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in PUBLIC_IMAGE_EXT:
        raise HTTPException(400, f"Unsupported image type .{ext} — use jpg, png, webp or gif")
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, f"File too large (max {MAX_UPLOAD_BYTES // (1024*1024)}MB)")
    if not data:
        raise HTTPException(400, "Empty file")

    kind_slug = "".join(c for c in kind if c.isalnum() or c in ("-", "_")).lower()[:32] or "misc"
    import hashlib as _hl
    digest = _hl.sha256(data).hexdigest()[:24]
    key = f"public/{kind_slug}/{user['id'][:8]}/{digest}.{ext}"

    content_type = file.content_type or f"image/{ext}"

    # Prefer R2 if configured (already public), otherwise write to local disk.
    if r2_enabled():
        try:
            _r2_client().put_object(
                Bucket=_env("R2_BUCKET"),
                Key=key,
                Body=data,
                ContentType=content_type,
                CacheControl="public, max-age=31536000, immutable",
            )
            return {"url": _r2_public_url(key), "kind": kind_slug, "size": len(data)}
        except Exception as e:
            logger.error(f"R2 upload failed, falling back to local: {e}")

    dest = LOCAL_ROOT / key
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        dest.write_bytes(data)
    return {"url": _local_public_url(key), "kind": kind_slug, "size": len(data)}


@api_router.post("/upload")
async def upload_file(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    filename = file.filename or "file"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, f"Unsupported file type .{ext}")
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, f"File too large (max {MAX_UPLOAD_BYTES // (1024*1024)}MB)")
    file_id = str(uuid.uuid4())
    path = f"{APP_NAME}/uploads/{user['id']}/{file_id}.{ext}"
    ct = file.content_type or "application/octet-stream"
    try:
        result = put_object(path, data, ct)
    except Exception as e:
        logger.error(f"Storage upload failed: {e}")
        raise HTTPException(500, "Upload failed. Please try again.")
    doc = {
        "id": file_id,
        "user_id": user["id"],
        "storage_path": result["path"],
        "original_filename": filename,
        "content_type": ct,
        "size": result.get("size", len(data)),
        "is_deleted": False,
        "created_at": _now_utc(),
    }
    await db.files.insert_one(doc)
    return {"id": file_id, "url": f"/api/files/{file_id}", "size": doc["size"], "content_type": ct}


@api_router.get("/files/{file_id}")
async def download_file(file_id: str, auth: Optional[str] = Query(None), authorization: Optional[str] = Header(None)):
    token = auth
    if not token and authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(None, 1)[1]
    if not token:
        raise HTTPException(401, "Auth required")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        user_id = payload.get("sub")
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid token")
    user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not user:
        raise HTTPException(401, "User not found")
    record = await db.files.find_one({"id": file_id, "is_deleted": False}, {"_id": 0})
    if not record:
        raise HTTPException(404, "File not found")
    if record["user_id"] != user_id and user.get("role") != "admin":
        raise HTTPException(403, "Not allowed")
    data, ct = get_object(record["storage_path"])
    return Response(content=data, media_type=record.get("content_type") or ct)


# =========================
# PHASE 3: AI LISTING ASSISTANT (GPT vision via Emergent LLM Key)
# =========================
class AIListingSuggestRequest(BaseModel):
    image_base64: Optional[str] = None
    image_url: Optional[str] = None
    hints: Optional[str] = ""


def _extract_json(text: str) -> dict:
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```\s*$", "", text)
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError("no JSON object found in AI response")
    return _json.loads(m.group(0))


@api_router.post("/ai/listing-suggest")
async def ai_listing_suggest(payload: AIListingSuggestRequest, user: dict = Depends(get_current_user)):
    if not payload.image_base64 and not payload.image_url:
        raise HTTPException(400, "Provide image_base64 or image_url")
    if not EMERGENT_LLM_KEY:
        raise HTTPException(500, "AI service not configured")

    image_b64 = payload.image_base64
    if not image_b64:
        from services.url_safety import is_safe_public_url
        ok, reason = is_safe_public_url(payload.image_url or "")
        if not ok:
            raise HTTPException(400, f"Invalid image_url: {reason}")
        try:
            r = _requests.get(payload.image_url, timeout=25)
            r.raise_for_status()
            image_b64 = base64.b64encode(r.content).decode()
        except Exception as e:
            raise HTTPException(400, f"Could not fetch image_url: {e}")
    if image_b64.startswith("data:") and "," in image_b64:
        image_b64 = image_b64.split(",", 1)[1]

    categories = await db.categories.find({}, {"_id": 0, "slug": 1, "name": 1, "id": 1}).to_list(50)
    if not categories:
        raise HTTPException(500, "No categories configured")
    cat_slugs = [c["slug"] for c in categories]
    cat_list = ", ".join([f"{c['slug']} ({c['name']})" for c in categories])

    system_msg = (
        "You are an expert Ocean listing assistant. Analyze the product photo and return "
        "STRICT JSON only (no prose, no code fences) with keys: "
        "title (string, max 60 chars, catchy), "
        "description (string, 3-5 short lines, buyer-friendly, up to 400 chars), "
        f"category_slug (one of: {cat_list}), "
        "condition (one of: new|like_new|good|fair|poor), "
        "brand (string, empty if unknown), "
        "color (string, empty if unknown), "
        "size (string, empty if not applicable), "
        "suggested_price_usd (number), "
        "original_price_usd (number, optional retail price). "
        "Do not include any keys other than those listed. Do not wrap the JSON in code fences."
    )
    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=f"listing-suggest-{user['id']}-{uuid.uuid4().hex[:8]}",
        system_message=system_msg,
    ).with_model(AI_MODEL_PROVIDER, AI_MODEL_NAME)

    hint_text = f"\n\nSeller hint: {payload.hints}" if payload.hints else ""
    try:
        response_text = await chat.send_message(UserMessage(
            text=f"Analyze this product photo and generate the JSON listing.{hint_text}",
            file_contents=[ImageContent(image_base64=image_b64)],
        ))
    except Exception as e:
        logger.error(f"AI listing suggest failed: {e}")
        raise HTTPException(500, f"AI request failed: {e}")

    try:
        data = _extract_json(response_text)
    except Exception as e:
        logger.error(f"AI JSON parse failed. Raw: {response_text!r}")
        raise HTTPException(500, f"AI returned invalid JSON: {e}")

    slug = str(data.get("category_slug", "other")).lower()
    if slug not in cat_slugs:
        slug = "other"
    cat = next((c for c in categories if c["slug"] == slug), None) or categories[-1]
    data["category_slug"] = slug
    data["category_id"] = cat["id"]
    data["category_name"] = cat["name"]
    for k in ("suggested_price_usd", "original_price_usd"):
        v = data.get(k)
        if v is not None:
            try:
                data[k] = float(v)
            except Exception:
                data[k] = None
    return data


# =========================
# Vibe Search — LLM-powered vibe → filter translation
# =========================
class VibeSearchRequest(BaseModel):
    vibe: str
    limit: int = 24


class ImageSearchRequest(BaseModel):
    image_base64: str
    limit: int = 24


@api_router.post("/search/image")
async def search_by_image(payload: ImageSearchRequest):
    """Reverse-image style search. Sends the photo to the LLM to extract 3-5
    broad search keywords + a category slug, then runs a listings search."""
    if not EMERGENT_LLM_KEY:
        raise HTTPException(500, "AI service not configured")
    b64 = (payload.image_base64 or "").strip()
    if not b64:
        raise HTTPException(400, "image_base64 is required")
    if b64.startswith("data:") and "," in b64:
        b64 = b64.split(",", 1)[1]

    categories = await db.categories.find({}, {"_id": 0, "id": 1, "slug": 1, "name": 1}).to_list(50)
    cat_list = ", ".join([c["slug"] for c in categories])

    system_msg = (
        "You are a visual product identifier. Look at the photo and return STRICT JSON "
        "only (no prose, no code fences) with keys: "
        "keywords (array of 2-5 broad single-word or 2-word terms that appear in similar product titles), "
        f"category_slug (one slug from: {cat_list}), "
        "description (short 1-sentence description of what you see, max 90 chars). "
        "Do not include any other keys."
    )
    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=f"img-search-{uuid.uuid4().hex[:10]}",
        system_message=system_msg,
    ).with_model(AI_MODEL_PROVIDER, AI_MODEL_NAME)
    try:
        raw = await chat.send_message(UserMessage(
            text="Identify this product and return the JSON.",
            file_contents=[ImageContent(image_base64=b64)],
        ))
    except Exception as e:
        logger.error(f"Image search LLM failed: {e}")
        raise HTTPException(500, f"AI request failed: {e}")
    try:
        parsed = _extract_json(raw)
    except Exception as e:
        raise HTTPException(500, f"AI returned invalid JSON: {e}")

    keywords = [str(k).strip() for k in (parsed.get("keywords") or []) if str(k).strip()][:5]
    slug = str(parsed.get("category_slug") or "").lower()
    cat = next((c for c in categories if c["slug"] == slug), None)
    description = str(parsed.get("description") or "").strip()[:100]

    # Build query
    q: dict = {"status": "active"}
    if keywords:
        ors = []
        for k in keywords:
            rx = {"$regex": re.escape(k), "$options": "i"}
            ors.extend([{"title": rx}, {"brand": rx}])
        q["$or"] = ors
    if cat:
        q["category_id"] = cat["id"]

    limit = max(1, min(int(payload.limit or 24), 60))
    docs = await db.listings.find(q, {"_id": 0}).sort(
        [("views_count", -1), ("likes_count", -1)]
    ).limit(limit).to_list(limit)
    if len(docs) < 6 and cat:
        # Fallback: category only
        docs = await db.listings.find(
            {"status": "active", "category_id": cat["id"]}, {"_id": 0}
        ).sort([("views_count", -1)]).limit(limit).to_list(limit)

    return {
        "description": description,
        "keywords": keywords,
        "category": {"id": cat["id"], "name": cat["name"], "slug": cat["slug"]} if cat else None,
        "items": docs,
        "total": len(docs),
    }


# ---- Currency live FX rates (USD base). Uses open.er-api.com with in-memory cache and static fallback. ----
_fx_cache: dict = {}
@api_router.get("/currency/rates")
async def currency_rates():
    """Live FX rates with 1-hour in-memory cache, falling back to the static
    table on network / provider failure so the app never shows raw prices."""
    global _fx_cache
    now = datetime.now(timezone.utc)
    cached = _fx_cache.get("data")
    cached_at = _fx_cache.get("at")
    if cached and cached_at and (now - cached_at).total_seconds() < 3600:
        return cached

    static_rates = {
        "USD": 1.0, "EUR": 0.92, "GBP": 0.78, "JPY": 155.0,
        "INR": 83.2, "CAD": 1.36, "AUD": 1.52, "BRL": 5.05,
        "MXN": 17.1, "CNY": 7.18, "KRW": 1345.0, "SGD": 1.34,
        "AED": 3.673,
    }

    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            resp = await client.get("https://open.er-api.com/v6/latest/USD")
        if resp.status_code == 200:
            data = resp.json() or {}
            live = data.get("rates") or {}
            rates = {code: float(live.get(code, static_rates[code])) for code in static_rates}
            payload = {
                "base": "USD",
                "updated_at": now.isoformat(),
                "source": "open.er-api.com",
                "rates": rates,
            }
            _fx_cache = {"data": payload, "at": now}
            return payload
    except Exception as e:
        logger.warning(f"FX fetch failed, using static rates: {e}")

    # Fallback path — never leaves the client without rates
    payload = {
        "base": "USD",
        "updated_at": now.isoformat(),
        "source": "static-fallback",
        "rates": static_rates,
    }
    # Cache the fallback briefly (5 min) so we retry the live API sooner
    _fx_cache = {"data": payload, "at": now - timedelta(seconds=3300)}
    return payload


@api_router.post("/search/vibe")
async def search_vibe(payload: VibeSearchRequest, request: Request):
    """Translate a natural-language vibe ('cozy', 'minimalist retro', 'y2k glam') into
    concrete filters using the Emergent LLM key, then return matching active listings.
    Anonymous-friendly (no auth required)."""
    vibe = (payload.vibe or "").strip()
    if len(vibe) < 2:
        raise HTTPException(400, "Vibe must be at least 2 characters")
    if not EMERGENT_LLM_KEY:
        raise HTTPException(500, "AI service not configured")

    categories = await db.categories.find({}, {"_id": 0, "id": 1, "slug": 1, "name": 1}).to_list(50)
    cat_slugs = [c["slug"] for c in categories]
    cat_list = ", ".join(cat_slugs)

    system_msg = (
        "You translate free-form shopping 'vibes' into concrete Ocean filters. "
        "Return STRICT JSON only (no prose, no code fences) with keys: "
        "keywords (array of 2-5 BROAD single-word or 2-word search terms that commonly appear in product titles for this vibe — favor generic words like 'watch', 'sweater', 'lamp' over niche phrases), "
        f"category_slugs (array of 1-3 slugs from this exact list: {cat_list}), "
        "brand_hints (array of 0-4 brand names likely to match the vibe, empty array if unsure), "
        "min_price (number or null), max_price (number or null), "
        "explanation (short single-sentence summary of the vibe under 90 chars). "
        "Do not include any other keys."
    )
    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=f"vibe-{uuid.uuid4().hex[:10]}",
        system_message=system_msg,
    ).with_model(AI_MODEL_PROVIDER, AI_MODEL_NAME)

    try:
        response_text = await chat.send_message(UserMessage(text=f"Vibe: {vibe}"))
    except Exception as e:
        logger.error(f"Vibe LLM failed: {e}")
        raise HTTPException(500, f"AI request failed: {e}")

    try:
        parsed = _extract_json(response_text)
    except Exception as e:
        logger.error(f"Vibe JSON parse failed. Raw: {response_text!r}")
        raise HTTPException(500, f"AI returned invalid JSON: {e}")

    keywords = [str(k).strip() for k in (parsed.get("keywords") or []) if str(k).strip()][:4]
    slug_list = [str(s).strip().lower() for s in (parsed.get("category_slugs") or [])]
    picked_cat_ids = [c["id"] for c in categories if c["slug"] in slug_list][:3]
    brand_hints = [str(b).strip() for b in (parsed.get("brand_hints") or []) if str(b).strip()][:4]
    min_price = parsed.get("min_price")
    max_price = parsed.get("max_price")
    explanation = str(parsed.get("explanation") or "").strip()[:120]

    # Build mongo query with graceful fallback if the strict combo yields too little
    def build_query(include_or: bool, include_keywords: bool, include_price: bool) -> dict:
        q: dict = {"status": "active"}
        if include_or:
            ors: list = []
            if include_keywords:
                for k in keywords:
                    rx = {"$regex": re.escape(k), "$options": "i"}
                    ors.extend([{"title": rx}, {"description": rx}])
            for b in brand_hints:
                ors.append({"brand": {"$regex": re.escape(b), "$options": "i"}})
            if ors:
                q["$or"] = ors
        if picked_cat_ids:
            q["category_id"] = {"$in": picked_cat_ids}
        if include_price and (isinstance(min_price, (int, float)) or isinstance(max_price, (int, float))):
            pr: dict = {}
            if isinstance(min_price, (int, float)) and min_price > 0:
                pr["$gte"] = float(min_price)
            if isinstance(max_price, (int, float)) and max_price > 0:
                pr["$lte"] = float(max_price)
            if pr:
                q["price"] = pr
        return q

    limit = max(1, min(int(payload.limit or 24), 60))
    # Levels: strict → no price → no keywords → category only
    levels = [
        ("strict", True, True, True),
        ("no-price", True, True, False),
        ("no-keywords", True, False, False),
        ("category-only", False, False, False),
    ]
    fallback_used = "strict"
    docs: list = []
    for name, inc_or, inc_kw, inc_pr in levels:
        query = build_query(include_or=inc_or, include_keywords=inc_kw, include_price=inc_pr)
        docs = await db.listings.find(query, {"_id": 0}).sort(
            [("views_count", -1), ("likes_count", -1)]
        ).limit(limit).to_list(limit)
        fallback_used = name
        if len(docs) >= max(6, limit // 3) or name == "category-only":
            break

    picked_categories = [
        {"id": c["id"], "name": c["name"], "slug": c["slug"]}
        for c in categories if c["slug"] in slug_list
    ]

    return {
        "vibe": vibe,
        "explanation": explanation,
        "keywords": keywords,
        "categories": picked_categories,
        "brand_hints": brand_hints,
        "price_range": {"min": min_price, "max": max_price},
        "fallback": fallback_used,
        "items": docs,
        "total": len(docs),
    }


# =========================
# PHASE 4: AI Photo Cleanup (Nano Banana image editing) + Flash Deals
# =========================
NANO_BANANA_MODEL = "gemini-3.1-flash-image-preview"


class PhotoEnhanceRequest(BaseModel):
    file_id: Optional[str] = None
    image_base64: Optional[str] = None
    image_url: Optional[str] = None
    prompt: Optional[str] = "Remove the background, produce a clean centered product photo with a soft studio-white backdrop, crisp lighting, high resolution, no watermarks."


@api_router.post("/ai/photo-enhance")
async def ai_photo_enhance(payload: PhotoEnhanceRequest, user: dict = Depends(get_current_user)):
    """One-click photo cleanup with Gemini Nano Banana. Returns a NEW uploaded file id + URL."""
    if not EMERGENT_LLM_KEY:
        raise HTTPException(500, "AI service not configured")

    # Resolve input bytes
    image_bytes: Optional[bytes] = None
    if payload.file_id:
        rec = await db.files.find_one({"id": payload.file_id, "is_deleted": False}, {"_id": 0})
        if not rec:
            raise HTTPException(404, "File not found")
        if rec["user_id"] != user["id"] and user.get("role") != "admin":
            raise HTTPException(403, "Not allowed")
        image_bytes, _ct = get_object(rec["storage_path"])
    elif payload.image_base64:
        b = payload.image_base64
        if b.startswith("data:") and "," in b:
            b = b.split(",", 1)[1]
        try:
            image_bytes = base64.b64decode(b)
        except Exception:
            raise HTTPException(400, "Invalid base64 image")
    elif payload.image_url:
        from services.url_safety import is_safe_public_url
        ok, reason = is_safe_public_url(payload.image_url)
        if not ok:
            raise HTTPException(400, f"Invalid image_url: {reason}")
        try:
            r = _requests.get(payload.image_url, timeout=30)
            r.raise_for_status()
            image_bytes = r.content
        except Exception as e:
            raise HTTPException(400, f"Could not fetch image_url: {e}")
    else:
        raise HTTPException(400, "Provide file_id, image_base64, or image_url")

    b64_in = base64.b64encode(image_bytes).decode("utf-8")
    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=f"photo-enhance-{user['id']}-{uuid.uuid4().hex[:8]}",
        system_message="You are a professional product-photo editor. Return only the enhanced image.",
    ).with_model("gemini", NANO_BANANA_MODEL).with_params(modalities=["image", "text"])

    try:
        text, images = await chat.send_message_multimodal_response(
            UserMessage(text=payload.prompt or "Enhance this product photo.", file_contents=[ImageContent(b64_in)])
        )
    except Exception as e:
        logger.error(f"Nano Banana enhance failed: {e}")
        raise HTTPException(500, f"AI enhance failed: {e}")

    if not images:
        raise HTTPException(500, "AI returned no image")
    enhanced_b64 = images[0]["data"]
    enhanced_mime = images[0].get("mime_type") or "image/png"
    try:
        enhanced_bytes = base64.b64decode(enhanced_b64)
    except Exception:
        raise HTTPException(500, "AI returned an invalid image payload")

    # Save enhanced to object storage under new file id
    ext = "png" if "png" in enhanced_mime else ("jpg" if "jpeg" in enhanced_mime else "png")
    new_id = str(uuid.uuid4())
    new_path = f"{APP_NAME}/uploads/{user['id']}/{new_id}.{ext}"
    try:
        result = put_object(new_path, enhanced_bytes, enhanced_mime)
    except Exception as e:
        logger.error(f"Storage put enhanced failed: {e}")
        raise HTTPException(502, "Enhanced image storage failed. Please try again.")

    doc = {
        "id": new_id,
        "user_id": user["id"],
        "storage_path": result["path"],
        "original_filename": f"enhanced_{new_id[:8]}.{ext}",
        "content_type": enhanced_mime,
        "size": result.get("size", len(enhanced_bytes)),
        "is_deleted": False,
        "source": "ai_enhance",
        "created_at": _now_utc(),
    }
    await db.files.insert_one(doc)
    return {
        "id": new_id,
        "url": f"/api/files/{new_id}",
        "content_type": enhanced_mime,
        "size": doc["size"],
        "prompt_used": payload.prompt,
    }


# ---- FLASH DEALS -----------------------------------------------------------
FLASH_DEAL_COUNT = 10

def _today_midnight_utc() -> datetime:
    now = _now_utc()
    return (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)


async def rotate_flash_deals():
    """Pick FLASH_DEAL_COUNT random active listings, mark them as flash deals until midnight UTC."""
    now = _now_utc()
    # Clear any expired flash deals
    await db.listings.update_many(
        {"is_flash_deal": True, "flash_deal_ends_at": {"$lt": now}},
        {"$set": {"is_flash_deal": False, "flash_deal_ends_at": None, "flash_deal_discount_pct": None}},
    )
    # Count current active flash deals
    active_count = await db.listings.count_documents({"is_flash_deal": True})
    needed = max(0, FLASH_DEAL_COUNT - active_count)
    if needed == 0:
        return {"selected": 0, "active": active_count}

    ends_at = _today_midnight_utc()
    pipeline = [
        {"$match": {"status": "active", "is_flash_deal": {"$ne": True}}},
        {"$sample": {"size": needed}},
        {"$project": {"_id": 0, "id": 1}},
    ]
    picks = []
    async for d in db.listings.aggregate(pipeline):
        picks.append(d["id"])
    if not picks:
        return {"selected": 0, "active": active_count, "reason": "no active listings available"}
    for lid in picks:
        pct = 20 + int((sum(bytearray(lid.encode())) % 55))  # deterministic per id, 20-74%
        await db.listings.update_one(
            {"id": lid},
            {"$set": {
                "is_flash_deal": True,
                "flash_deal_ends_at": ends_at,
                "flash_deal_discount_pct": pct,
            }},
        )
        # Notify every user who favorited this listing
        listing_snap = await db.listings.find_one({"id": lid}, {"_id": 0, "title": 1, "price": 1})
        fav_users = await db.favorites.find({"listing_id": lid}, {"_id": 0, "user_id": 1}).to_list(500)
        for f in fav_users:
            await notify(
                f["user_id"], "system",
                f"Flash Deal: -{pct}% on a favourite",
                f"{(listing_snap or {}).get('title','Your favourite')} is now on Flash Deals until midnight UTC.",
                f"/listing/{lid}",
            )
    logger.info(f"[flash-deals] activated {len(picks)} new deals until {ends_at.isoformat()}")
    return {"selected": len(picks), "active": active_count + len(picks), "ends_at": ends_at.isoformat()}


async def wishlist_digest_loop():
    """Weekly wishlist digest — collates price drops from the last 7 days per user
    and MOCK-sends via Resend (logged to backend console + persisted to db.email_log)."""
    await asyncio.sleep(10)
    while True:
        try:
            since = _now_utc() - timedelta(days=7)
            # Group favorites by user, resolve current listings, filter recent price drops
            users_seen = set()
            async for f in db.favorites.find({}, {"_id": 0, "user_id": 1, "listing_id": 1}):
                users_seen.add(f["user_id"])
            for uid in users_seen:
                favs = await db.favorites.find({"user_id": uid}, {"_id": 0, "listing_id": 1}).to_list(500)
                lids = [x["listing_id"] for x in favs]
                if not lids:
                    continue
                drops = await db.listings.find(
                    {"id": {"$in": lids}, "price_drop_at": {"$gte": since}},
                    {"_id": 0, "id": 1, "title": 1, "price": 1, "previous_price": 1, "price_drop_at": 1},
                ).to_list(50)
            if not drops:
                continue
            user = await db.users.find_one({"id": uid}, {"_id": 0, "email": 1, "username": 1, "weekly_digest_opt_in": 1})
            if not user:
                continue
            # Respect opt-out
            if user.get("weekly_digest_opt_in", True) is False:
                continue
                subject = f"Weekly wishlist digest: {len(drops)} price drop(s) on your favourites"
                lines = [f"- {d['title']}: ${d['previous_price']:.2f} -> ${d['price']:.2f}" for d in drops[:20]]
                body = "Hi " + user.get("username", "there") + ",\n\n" + "\n".join(lines) + "\n\nShop now on Ocean!"
                logger.info(f"[MOCK Resend] to={user['email']} subject={subject!r}")
                await db.email_log.insert_one({
                    "id": str(uuid.uuid4()),
                    "user_id": uid, "to": user["email"], "kind": "wishlist_digest",
                    "subject": subject, "body": body, "drops": len(drops),
                    "sent_at": _now_utc(), "provider": "mock_resend",
                })
                await notify(uid, "system", subject, f"{len(drops)} price drops in your favourites this week.", "/favorites")
        except Exception as e:
            logger.warning(f"wishlist_digest_loop error: {e}")
        # Run once a week (dev: every 6 hours to make it observable during testing)
        interval = int(os.environ.get("WISHLIST_DIGEST_INTERVAL_SEC", str(6 * 3600)))
        await asyncio.sleep(max(60, interval))


async def newsletter_digest_loop():
    """Weekly newsletter digest — pulls top listings + recent price drops and
    MOCK-sends a Resend email to every active subscriber in db.newsletter_subscribers.
    Interval controlled by NEWSLETTER_DIGEST_INTERVAL_SEC (default 7 days)."""
    await asyncio.sleep(15)
    while True:
        try:
            since = _now_utc() - timedelta(days=7)
            top_listings = await db.listings.find(
                {"status": "active"},
                {"_id": 0, "id": 1, "title": 1, "price": 1, "images": 1, "likes_count": 1, "views_count": 1},
            ).sort([("likes_count", -1), ("views_count", -1)]).to_list(6)
            drops = await db.listings.find(
                {"status": "active", "price_drop_at": {"$gte": since}, "previous_price": {"$gt": 0}},
                {"_id": 0, "id": 1, "title": 1, "price": 1, "previous_price": 1, "price_drop_at": 1},
            ).sort("price_drop_at", -1).to_list(6)

            if not top_listings and not drops:
                # Nothing worth sending this cycle
                interval = int(os.environ.get("NEWSLETTER_DIGEST_INTERVAL_SEC", str(7 * 24 * 3600)))
                await asyncio.sleep(max(60, interval))
                continue

            subject_bits = []
            if drops:
                subject_bits.append(f"{len(drops)} price drop(s)")
            if top_listings:
                subject_bits.append(f"{len(top_listings)} trending pick(s)")
            subject = "Weekly Ocean digest: " + " · ".join(subject_bits)

            body_lines = ["Hi there,", ""]
            if drops:
                body_lines.append("🔥 Price drops this week:")
                for d in drops:
                    body_lines.append(f"  - {d['title']}: ${d['previous_price']:.2f} → ${d['price']:.2f}")
                body_lines.append("")
            if top_listings:
                body_lines.append("✨ Trending on Ocean:")
                for t in top_listings:
                    body_lines.append(f"  - {t['title']} — ${t['price']:.2f}")
                body_lines.append("")
            body_lines.append("Shop everything at Ocean.")
            body_lines.append("To unsubscribe, POST /api/newsletter/unsubscribe with your email.")
            body = "\n".join(body_lines)

            sent = 0
            async for sub in db.newsletter_subscribers.find(
                {"unsubscribed": {"$ne": True}},
                {"_id": 0, "email": 1},
            ):
                email_to = sub.get("email")
                if not email_to:
                    continue
                logger.info(f"[MOCK Resend] to={email_to} subject={subject!r}")
                await db.email_log.insert_one({
                    "id": str(uuid.uuid4()),
                    "to": email_to,
                    "kind": "newsletter_digest",
                    "subject": subject,
                    "body": body,
                    "drops": len(drops),
                    "top_picks": len(top_listings),
                    "sent_at": _now_utc(),
                    "provider": "mock_resend",
                })
                sent += 1
            if sent:
                logger.info(f"[Newsletter] mock-sent digest to {sent} subscriber(s)")
        except Exception as e:
            logger.warning(f"newsletter_digest_loop error: {e}")
        interval = int(os.environ.get("NEWSLETTER_DIGEST_INTERVAL_SEC", str(7 * 24 * 3600)))
        await asyncio.sleep(max(60, interval))


# =========================
# Escrow Alerts Digest — weekly email listing seller orders stuck in escrow
# past their ETA. Sellers can nudge buyers to confirm delivery and unlock funds.
# =========================
async def _build_escrow_alerts_for_seller(seller_id: str, threshold_days: int = 0) -> dict:
    """Return {stuck: [...], total_frozen: float} for a single seller.

    A "stuck" order = funds_released is false AND (estimated_delivery_at is
    past OR order is more than 14d old with no ETA). `threshold_days` grants
    a grace period — 0 = anything past ETA, 3 = only ≥3 days overdue.
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=threshold_days)
    orders = await db.orders.find(
        {
            "seller_id": seller_id,
            "funds_released": False,
            "seller_earnings": {"$gt": 0},
        },
        {"_id": 0, "id": 1, "listing_title": 1, "listing_image": 1,
         "seller_earnings": 1, "estimated_delivery_at": 1, "created_at": 1,
         "buyer_name": 1, "shipping_status": 1, "status": 1},
    ).to_list(500)

    def _to_aware(dt):
        if dt is None:
            return None
        if isinstance(dt, str):
            try:
                dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
            except Exception:
                return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    stuck: List[dict] = []
    for o in orders:
        eta = _to_aware(o.get("estimated_delivery_at"))
        created = _to_aware(o.get("created_at"))
        # An order is stuck if ETA has passed by ≥ threshold, or (no ETA and
        # order was created > 14 days ago).
        is_past_eta = eta is not None and eta < cutoff
        is_old_no_eta = eta is None and created is not None and (now - created).days > 14
        if not (is_past_eta or is_old_no_eta):
            continue
        overdue_days = (now - eta).days if eta else (now - created).days if created else 0
        stuck.append({
            "order_id": o["id"],
            "listing_title": o.get("listing_title") or "Order",
            "listing_image": o.get("listing_image"),
            "buyer_name": o.get("buyer_name"),
            "amount": round(float(o.get("seller_earnings", 0.0)), 2),
            "eta": eta.isoformat() if eta else None,
            "overdue_days": max(0, overdue_days),
            "shipping_status": o.get("shipping_status") or o.get("status"),
        })
    stuck.sort(key=lambda r: r["overdue_days"], reverse=True)
    total_frozen = round(sum(r["amount"] for r in stuck), 2)
    return {"stuck": stuck, "total_frozen": total_frozen}


def _render_escrow_digest_html(username: str, stuck: List[dict], total_frozen: float) -> str:
    """Compose the digest body HTML using the standard branded shell."""
    from services.email_templates import _shell, FRONTEND
    rows = []
    for s in stuck[:20]:
        eta_line = ""
        if s.get("eta"):
            try:
                eta_dt = datetime.fromisoformat(s["eta"].replace("Z", "+00:00"))
                eta_line = eta_dt.strftime("%b %d, %Y")
            except Exception:
                eta_line = s["eta"]
        thumb = (
            f'<img src="{s["listing_image"]}" width="48" height="48" '
            f'style="border-radius:8px;object-fit:cover;vertical-align:middle;margin-right:12px;" alt="">'
            if s.get("listing_image") else ""
        )
        rows.append(
            f'<tr><td style="padding:10px 0;border-bottom:1px solid #F1F5F9;">'
            f'<div style="display:flex;align-items:center;">{thumb}'
            f'<div style="display:inline-block;vertical-align:middle;">'
            f'<div style="font-weight:600;color:#111827;">{s["listing_title"]}</div>'
            f'<div style="font-size:12px;color:#6B7280;">'
            f'Buyer: {s.get("buyer_name") or "—"} · '
            f'ETA {eta_line or "n/a"} · '
            f'<span style="color:#B45309;font-weight:600;">{s["overdue_days"]} day(s) overdue</span>'
            f'</div></div>'
            f'<div style="float:right;font-weight:700;color:#059669;">${s["amount"]:.2f}</div>'
            f'</div></td></tr>'
        )
    body = (
        f"<p>Hi {username or 'there'},</p>"
        f"<p>You have <b>{len(stuck)}</b> order(s) still holding "
        f"<b>${total_frozen:.2f}</b> in escrow past their expected delivery date. "
        f"Buyers can confirm delivery from their orders page — a quick nudge often "
        f"unlocks funds within hours.</p>"
        f"<table role='presentation' width='100%' cellpadding='0' cellspacing='0' "
        f"style='margin-top:12px;'>"
        + "".join(rows)
        + "</table>"
    )
    if len(stuck) > 20:
        body += f"<p style='color:#6B7280;font-size:12px;'>+ {len(stuck) - 20} more not shown</p>"
    return _shell(
        f"{len(stuck)} order(s) stuck in escrow",
        body,
        f"{FRONTEND}/wallet",
        "Review escrow →",
    )


async def _dispatch_escrow_digest(threshold_days: int = 3, dry_run: bool = False) -> dict:
    """Run one pass of the escrow-alerts digest across every seller who has
    stuck orders. Returns counters for the admin trigger endpoint."""
    from services import mailer

    # If the mailer circuit-breaker is already open there is no point in
    # scanning 200+ orders and trying (and failing) to send an email for
    # each — that burns 30–60s of DB work on the event loop and can starve
    # concurrent admin API requests (users saw the seller-applications page
    # returning 502 during exactly these windows). Bail out immediately;
    # the next scheduled tick will retry once the breaker closes.
    if not dry_run and mailer._circuit_open():
        logger.warning(
            "[escrow-digest] mailer circuit-breaker is open — skipping this run"
        )
        return {
            "scanned": 0,
            "sent": 0,
            "skipped_opt_out": 0,
            "skipped_no_stuck": 0,
            "skipped_circuit_open": True,
            "dry_run": dry_run,
        }

    seller_ids: set = set()
    async for o in db.orders.find(
        {"funds_released": False, "seller_earnings": {"$gt": 0}},
        {"_id": 0, "seller_id": 1},
    ):
        if o.get("seller_id"):
            seller_ids.add(o["seller_id"])

    scanned = 0
    sent = 0
    skipped_opt_out = 0
    skipped_no_stuck = 0
    for sid in seller_ids:
        scanned += 1
        seller = await db.users.find_one(
            {"id": sid},
            {"_id": 0, "id": 1, "email": 1, "username": 1,
             "weekly_digest_opt_in": 1, "email_prefs": 1},
        )
        if not seller or not seller.get("email"):
            continue
        if seller.get("weekly_digest_opt_in", True) is False:
            skipped_opt_out += 1
            continue
        prefs = seller.get("email_prefs") or {}
        # Reuse the existing "payout" opt-out lane — escrow is payout-adjacent.
        if prefs.get("payout") is False:
            skipped_opt_out += 1
            continue

        report = await _build_escrow_alerts_for_seller(sid, threshold_days=threshold_days)
        if not report["stuck"]:
            skipped_no_stuck += 1
            continue

        subject = (
            f"{len(report['stuck'])} order(s) stuck in escrow · "
            f"${report['total_frozen']:.2f} awaiting release"
        )
        html = _render_escrow_digest_html(
            seller.get("username", "there"),
            report["stuck"],
            report["total_frozen"],
        )

        if dry_run:
            sent += 1
            continue

        try:
            result = await mailer.send_email(
                to=seller["email"], subject=subject, html=html,
                tags=["escrow_digest"],
            )
        except Exception as e:
            logger.warning(f"escrow_digest send failed for {sid}: {e}")
            result = {"ok": False, "error": str(e), "provider": "unknown"}

        await db.email_log.insert_one({
            "id": str(uuid.uuid4()),
            "user_id": sid,
            "to": seller["email"],
            "kind": "escrow_digest",
            "subject": subject,
            "orders_count": len(report["stuck"]),
            "total_frozen": report["total_frozen"],
            "provider": result.get("provider"),
            "ok": result.get("ok"),
            "error": result.get("error"),
            "sent_at": datetime.now(timezone.utc),
        })
        # In-app notification too so sellers who skip email still see it.
        await notify(
            sid, "payout", subject,
            f"{len(report['stuck'])} order(s) with ${report['total_frozen']:.2f} in escrow "
            f"are past their delivery ETA. Nudge buyers to confirm and unlock funds.",
            "/wallet",
        )
        sent += 1

    logger.info(
        f"[escrow-digest] scanned={scanned} sent={sent} "
        f"skipped_opt_out={skipped_opt_out} skipped_no_stuck={skipped_no_stuck} "
        f"dry_run={dry_run}"
    )
    return {
        "scanned": scanned,
        "sent": sent,
        "skipped_opt_out": skipped_opt_out,
        "skipped_no_stuck": skipped_no_stuck,
        "dry_run": dry_run,
    }


async def escrow_digest_loop():
    """Weekly loop that dispatches escrow alert digests to sellers with orders
    past their delivery ETA. Interval controlled by ESCROW_DIGEST_INTERVAL_SEC
    (default 7 days). Threshold controlled by ESCROW_DIGEST_THRESHOLD_DAYS
    (default 3 — only orders ≥3d overdue trigger a digest email).

    Persists last_run_at in db.settings so hot-reloads / restarts don't
    re-blast every ~20s — a huge event-loop hog that caused 502s on
    admin endpoints during rapid dev iteration."""
    await asyncio.sleep(20)
    while True:
        try:
            interval = int(os.environ.get("ESCROW_DIGEST_INTERVAL_SEC", str(7 * 24 * 3600)))
            threshold = int(os.environ.get("ESCROW_DIGEST_THRESHOLD_DAYS", "3"))
            # Skip if we already ran within the interval on a previous
            # process (hot reload / redeploy / pod restart).
            state = await db.settings.find_one({"key": "escrow_digest_state"}, {"_id": 0})
            last_ts = None
            if state and state.get("last_run_at"):
                last = state["last_run_at"]
                if isinstance(last, str):
                    try:
                        last_ts = datetime.fromisoformat(last.replace("Z", "+00:00")).timestamp()
                    except Exception:
                        last_ts = None
                elif isinstance(last, datetime):
                    last_ts = last.timestamp()
            now_ts = datetime.now(timezone.utc).timestamp()
            if last_ts and (now_ts - last_ts) < max(60, interval):
                # Not yet due — wait for the remaining window instead of running.
                wait_left = max(60.0, interval - (now_ts - last_ts))
                await asyncio.sleep(wait_left)
                continue
            await _dispatch_escrow_digest(threshold_days=threshold, dry_run=False)
            await db.settings.update_one(
                {"key": "escrow_digest_state"},
                {"$set": {"key": "escrow_digest_state", "last_run_at": datetime.now(timezone.utc)}},
                upsert=True,
            )
        except Exception as e:
            logger.warning(f"escrow_digest_loop error: {e}")
        interval = int(os.environ.get("ESCROW_DIGEST_INTERVAL_SEC", str(7 * 24 * 3600)))
        await asyncio.sleep(max(60, interval))


@api_router.post("/admin/escrow-digest/dispatch")
async def admin_escrow_digest_dispatch(
    payload: dict = Body(default={}),
    _admin: dict = Depends(require_admin),
):
    """One-click admin trigger for the escrow alert digest.
    Body: {threshold_days?: int (default 3), dry_run?: bool (default false)}.
    Returns per-seller counters. Use dry_run=true to preview without sending."""
    threshold = int(payload.get("threshold_days", 3) or 3)
    dry_run = bool(payload.get("dry_run", False))
    return await _dispatch_escrow_digest(threshold_days=threshold, dry_run=dry_run)


@api_router.get("/wallet/escrow-alerts")
async def wallet_escrow_alerts(
    user: dict = Depends(get_current_user),
    threshold_days: int = 0,
):
    """Per-seller preview of the escrow-alerts digest — powers the in-wallet
    "Stuck escrow" tile and lets sellers see exactly which orders would be
    listed in the next weekly digest email."""
    threshold_days = max(0, min(int(threshold_days or 0), 30))
    return await _build_escrow_alerts_for_seller(user["id"], threshold_days=threshold_days)


async def flash_deals_rotation_loop():
    """Refill the flash-deal pool at startup and shortly after midnight UTC each day."""
    await asyncio.sleep(3)
    try:
        await rotate_flash_deals()
    except Exception as e:
        logger.warning(f"initial flash rotation failed: {e}")
    while True:
        # Sleep until next midnight + 30s
        now = _now_utc()
        next_run = _today_midnight_utc() + timedelta(seconds=30)
        await asyncio.sleep(max(30, (next_run - now).total_seconds()))
        try:
            await rotate_flash_deals()
        except Exception as e:
            logger.warning(f"scheduled flash rotation failed: {e}")


@api_router.get("/flash-deals", response_model=List[Listing])
async def flash_deals(limit: int = 12):
    now = _now_utc()
    # Auto-refill if depleted (e.g., first hit after a listing was deleted)
    active = await db.listings.count_documents(
        {"is_flash_deal": True, "flash_deal_ends_at": {"$gt": now}, "status": "active"}
    )
    if active < FLASH_DEAL_COUNT:
        try:
            await rotate_flash_deals()
        except Exception as e:
            logger.warning(f"on-demand flash refill failed: {e}")
    docs = await db.listings.find(
        {"is_flash_deal": True, "flash_deal_ends_at": {"$gt": now}, "status": "active"},
        {"_id": 0},
    ).sort("flash_deal_ends_at", 1).limit(limit).to_list(limit)
    return [Listing(**d) for d in docs]


@api_router.post("/admin/flash-deals/rotate")
async def admin_rotate_flash_deals(_admin: dict = Depends(require_admin)):
    return await rotate_flash_deals()


# ============================================================================
# Shipping label + tracking routes moved to routers/shipping.py
# (ShippingLabelResponse, AdvanceShippingRequest, _render_label_svg helper,
# and the four /orders/*/shipping-* + /orders/*/tracking + label.svg routes)
# ============================================================================


async def shipping_progress_loop():
    """Background: auto-advance MOCK shipping timelines and notify buyers on transitions.
    Only affects orders whose shipping_provider == 'mock' and status < delivered.
    """
    await asyncio.sleep(5)  # let startup complete
    while True:
        try:
            cursor = db.orders.find(
                {"shipping_provider": "mock", "shipping_status": {"$nin": ["delivered", None]}, "tracking_number": {"$ne": None}},
                {"_id": 0, "id": 1, "shipping_status": 1, "label_created_at": 1, "carrier": 1, "buyer_id": 1},
            )
            async for o in cursor:
                created = o.get("label_created_at")
                if not created:
                    continue
                if isinstance(created, str):
                    try:
                        created = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    except Exception:
                        continue
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
                age = (_now_utc() - created).total_seconds()
                nxt = next_stage_for_age(o.get("shipping_status", "label_created"), age)
                if not nxt:
                    continue
                ev = event_details(nxt, o.get("carrier", "Carrier"))
                order_updates: dict = {"shipping_status": nxt}
                # Stamp a real delivery timestamp so the buyer auto-confirm
                # loop can decide when to release escrow. Without this we'd
                # have to scan shipping_events on every pass.
                if nxt == "delivered":
                    order_updates["shipping_delivered_at"] = _now_utc()
                await db.orders.update_one(
                    {"id": o["id"]},
                    {"$set": order_updates, "$push": {"shipping_events": ev}},
                )
                await notify(o["buyer_id"], "order",
                             f"Shipping update: {nxt.replace('_',' ').title()}",
                             ev["description"], f"/order/{o['id']}")
                logger.info(f"[shipping:auto] order {o['id']} advanced to {nxt}")
        except Exception as e:
            logger.warning(f"shipping_progress_loop error: {e}")
        await asyncio.sleep(30)


async def _send_pickup_email(
    seller_id: str, order_id: str, listing_title: str,
    cost: float, profit: float, pickup_hours: int, *, kind: str = "new"
) -> None:
    """Send a pickup-required email to the seller. `kind` = "new" | "reminder_6h" | "reminder_1h"."""
    try:
        from services.mailer import send_email
        from services.email_templates import _shell, FRONTEND
        seller = await db.users.find_one({"id": seller_id}, {"_id": 0, "email": 1, "username": 1, "email_preferences": 1})
        if not seller or not seller.get("email"):
            return
        email = (seller.get("email") or "").lower()
        # Skip test-fixture / e2e emails so the reminder loop doesn't hammer
        # the SMTP relay with rejected recipients (Hostinger returns 5.7.1
        # for unknown mailboxes). Real deployments never hit these domains.
        TEST_EMAIL_DOMAINS = ("@e2e.com", "@example.com", "@test.local", "@demo.local", "@localhost")
        if email.startswith("e2e_") or any(email.endswith(d) for d in TEST_EMAIL_DOMAINS):
            return
        # Respect opt-outs for the "sale" lane.
        prefs = seller.get("email_preferences") or {}
        if prefs.get("sale") is False:
            return

        if kind == "reminder_30m":
            headline = "You have a new order waiting"
            urgency = "You haven't opened the pickup yet — accept now to lock in your profit."
        elif kind == "reminder_6h":
            headline = "Reminder: 6 hours left to accept your order"
            urgency = "Your buyer is waiting — accept before the pickup window closes."
        elif kind == "reminder_1h":
            headline = "Last hour to accept your order"
            urgency = "This order will auto-cancel and refund the buyer in about an hour."
        else:
            headline = "New order — please Pick & Deliver"
            urgency = f"You have {pickup_hours}h to accept and pay the source cost."

        cta_url = f"{FRONTEND.rstrip('/')}/profile?tab=sales&pickup={order_id}"
        cost_line = f"<div>Source cost: <b>${cost:.2f}</b></div>" if cost > 0 else "<div>Source cost: <b>$0.00</b></div>"
        body_html = f"""
<h1 style="margin:0 0 8px 0;font-size:22px;color:#111;">{headline}</h1>
<p style="margin:0 0 12px 0;color:#555;">{urgency}</p>
<div style="border:1px solid #eee;border-radius:8px;padding:14px 16px;background:#fafafa;margin:12px 0;">
  <div style="font-weight:600;color:#111;margin-bottom:6px;">{listing_title}</div>
  {cost_line}
  <div>Your profit (held until delivery): <b style="color:#0a7c3e;">${profit:.2f}</b></div>
</div>
<p style="margin:16px 0;">
  <a href="{cta_url}" style="background:#FF211F;color:#fff;padding:10px 22px;border-radius:999px;text-decoration:none;font-weight:600;">
    Pick &amp; Deliver →
  </a>
</p>
<p style="color:#888;font-size:12px;">Not accepted in time = the order auto-cancels and the buyer is refunded.</p>
""".strip()
        html = _shell(seller.get("username") or "Seller", body_html)
        await send_email(
            to=seller["email"],
            subject=f"[Ocean] {headline}",
            html=html,
            tags=["pickup", kind],
        )
    except Exception as e:
        logger.warning(f"_send_pickup_email({kind}) failed for order {order_id}: {e}")


async def pickup_reminder_loop():
    """Fire escalating pickup reminders (default T-6h and T-1h) before auto-cancel.

    Also fires a T+30-minute "bump" for any order still `pending_pickup`
    30-60 minutes after checkout — the seller hasn't clicked into the
    original email yet, so we nudge them once more with the profit
    number restated. Cadence is driven by `settings.pickup_reminder_hours`
    (list of hours before the deadline) — admins can tune this from
    the dashboard. We mark each reminder as sent on the order doc so
    we never spam the seller twice. Runs every 5 minutes."""
    await asyncio.sleep(30)
    while True:
        try:
            now = datetime.now(timezone.utc)
            settings = await get_settings()
            # ---- T+30m post-checkout bump ------------------------------
            # Fire once per order between 30-60 minutes after checkout if
            # the order is still `pending_pickup`. Uses `created_at` as
            # the anchor since that's the moment the buyer paid.
            bump_lo = now - timedelta(minutes=60)
            bump_hi = now - timedelta(minutes=30)
            pickup_hours = int(settings.get("pickup_deadline_hours", 48))
            bump_cursor = db.orders.find(
                {
                    "fulfillment_status": "pending_pickup",
                    "created_at": {"$gte": bump_lo, "$lte": bump_hi},
                    "pickup_bump_30m_sent_at": {"$exists": False},
                },
                {"_id": 0, "id": 1, "seller_id": 1, "listing_title": 1,
                 "reseller_wholesale_cost": 1, "seller_earnings": 1, "created_at": 1},
            ).limit(100)
            due_bumps = await bump_cursor.to_list(length=100)
            for o in due_bumps:
                try:
                    await _send_pickup_email(
                        o["seller_id"], o["id"], o.get("listing_title", "order"),
                        float(o.get("reseller_wholesale_cost") or 0.0),
                        float(o.get("seller_earnings") or 0.0),
                        pickup_hours, kind="reminder_30m",
                    )
                    await notify(
                        o["seller_id"], "sale",
                        "You have a new order waiting",
                        f"'{o.get('listing_title','order')}' is still pending pickup — accept now to keep the sale.",
                        f"/profile?tab=sales&pickup={o['id']}",
                    )
                    await db.orders.update_one(
                        {"id": o["id"]},
                        {
                            "$set": {"pickup_bump_30m_sent_at": now},
                            "$push": {
                                "pickup_events": {
                                    "type": "reminder",
                                    "minutes_after_checkout": 30,
                                    "at": now,
                                    "channel": "email+notify",
                                }
                            },
                        },
                    )
                except Exception as e:
                    logger.warning(f"pickup 30m-bump failed for {o.get('id')}: {e}")

            # ---- T-Nh pre-deadline reminders (unchanged) ---------------
            reminder_hours = settings.get("pickup_reminder_hours") or [6, 1]
            for h in reminder_hours:
                try:
                    h = int(h)
                except (TypeError, ValueError):
                    continue
                if h < 1 or h > 72:
                    continue
                # Window: pickup_deadline lies within [now + (h - 0.5h), now + (h + 0.5h)]
                cutoff_lo = timedelta(hours=h - 0.5)
                cutoff_hi = timedelta(hours=h + 0.5)
                flag = f"pickup_reminder_{h}h_sent_at"
                cursor = db.orders.find(
                    {
                        "fulfillment_status": "pending_pickup",
                        "pickup_deadline": {
                            "$gte": now + cutoff_lo,
                            "$lte": now + cutoff_hi,
                        },
                        flag: {"$exists": False},
                    },
                    {"_id": 0, "id": 1, "seller_id": 1, "listing_title": 1,
                     "reseller_wholesale_cost": 1, "seller_earnings": 1, "pickup_deadline": 1},
                ).limit(100)
                due = await cursor.to_list(length=100)
                pickup_hours = int(settings.get("pickup_deadline_hours", 48))
                for o in due:
                    try:
                        kind = f"reminder_{h}h"
                        await _send_pickup_email(
                            o["seller_id"], o["id"], o.get("listing_title", "order"),
                            float(o.get("reseller_wholesale_cost") or 0.0),
                            float(o.get("seller_earnings") or 0.0),
                            pickup_hours, kind=kind,
                        )
                        headline = f"{h} hour{'s' if h != 1 else ''} left to accept"
                        await notify(
                            o["seller_id"], "sale", headline,
                            f"'{o.get('listing_title','order')}' — accept now or it auto-cancels.",
                            f"/profile?tab=orders&pickup={o['id']}",
                        )
                        await db.orders.update_one(
                            {"id": o["id"]},
                            {
                                "$set": {flag: now},
                                "$push": {
                                    "pickup_events": {
                                        "type": "reminder",
                                        "hours_before": h,
                                        "at": now,
                                        "channel": "email+notify",
                                    }
                                },
                            },
                        )
                    except Exception as e:
                        logger.warning(f"pickup_reminder({h}h) failed for {o.get('id')}: {e}")
        except Exception as e:
            logger.exception(f"pickup_reminder_loop error: {e}")
        await asyncio.sleep(int(os.environ.get("PICKUP_REMINDER_INTERVAL_SEC", "300")))


async def pickup_expiry_loop():
    """Auto-cancel orders whose `pickup_deadline` has elapsed without the
    seller accepting. Refunds the buyer (the payment sat in escrow — since
    the seller never picked, no wholesale was debited, so we simply mark
    the order cancelled + refund the buyer). Runs every 10 minutes."""
    await asyncio.sleep(20)
    while True:
        try:
            now = datetime.now(timezone.utc)
            cursor = db.orders.find(
                {
                    "fulfillment_status": "pending_pickup",
                    "pickup_deadline": {"$lte": now},
                },
                {"_id": 0},
            ).limit(50)
            expired = await cursor.to_list(length=50)
            for o in expired:
                # Refund buyer (no wholesale to refund since seller never picked).
                try:
                    refund_amount = float(o.get("amount", 0.0)) + float(o.get("shipping_fee", 0.0))
                    if refund_amount > 0:
                        await credit_wallet(
                            o["buyer_id"], refund_amount, "refund",
                            f"Auto-refund: seller did not accept order in time — {o.get('listing_title','')}",
                            o["id"],
                        )
                    await db.orders.update_one(
                        {"id": o["id"]},
                        {
                            "$set": {
                                "fulfillment_status": "auto_cancelled",
                                "status": "cancelled",
                                "auto_cancelled_at": now,
                            },
                            "$push": {
                                "pickup_events": {
                                    "type": "auto_cancelled",
                                    "at": now,
                                    "reason": "pickup_deadline_expired",
                                    "channel": "system",
                                }
                            },
                        },
                    )
                    # Return the listing to "active" so someone else can buy it.
                    if o.get("listing_id"):
                        await db.listings.update_one(
                            {"id": o["listing_id"], "status": "sold"},
                            {"$set": {"status": "active"}},
                        )
                    # Notify all parties.
                    await notify(o["buyer_id"], "order",
                                 f"Refund issued: seller didn't accept",
                                 f"Your ${refund_amount:.2f} for '{o.get('listing_title','')}' is back in your wallet.",
                                 "/wallet")
                    await notify(o["seller_id"], "sale",
                                 f"Order auto-cancelled",
                                 f"You didn't accept '{o.get('listing_title','')}' within the pickup window. The buyer was refunded.",
                                 "/profile?tab=orders")
                    # Alert admins so they can nudge the seller on the store page.
                    admin_cursor = db.users.find({"role": "admin"}, {"_id": 0, "id": 1})
                    async for admin_row in admin_cursor:
                        await notify(admin_row["id"], "admin",
                                     f"Order auto-cancelled — seller did not pick",
                                     f"Order #{o['id'][:8]} was auto-cancelled. Consider urging seller {o.get('seller_name','?')} on their store page.",
                                     f"/admin/users?q={o.get('seller_id','')}")
                except Exception as e:
                    logger.exception(f"pickup_expiry_loop: failed to expire order {o.get('id')}: {e}")
        except Exception as e:
            logger.exception(f"pickup_expiry_loop error: {e}")
        await asyncio.sleep(int(os.environ.get("PICKUP_EXPIRY_INTERVAL_SEC", "600")))



async def auto_confirm_delivery_loop():
    """Buyer Auto-Confirm — release escrow N days after tracking reports the
    parcel as delivered, if the buyer hasn't manually confirmed. Keeps seller
    cash flow moving without a manual nudge.

    * Threshold (default 72h) tunable via `AUTO_CONFIRM_AFTER_HOURS`.
    * Loop interval (default 1h) tunable via `AUTO_CONFIRM_INTERVAL_SEC`.
    * Only orders with `shipping_delivered_at` set (i.e. carrier-confirmed
      delivery from the shipping loop) qualify. Orders confirmed manually
      have `funds_released: True` and are naturally excluded.
    """
    await asyncio.sleep(30)
    while True:
        try:
            hours = int(os.environ.get("AUTO_CONFIRM_AFTER_HOURS", "24"))
            cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
            cursor = db.orders.find(
                {
                    "shipping_status": "delivered",
                    "shipping_delivered_at": {"$lte": cutoff},
                    "funds_released": {"$ne": True},
                    "seller_earnings": {"$gt": 0},
                },
                {"_id": 0, "id": 1, "seller_id": 1, "buyer_id": 1,
                 "seller_earnings": 1, "listing_title": 1,
                 "dropship_source_seller_id": 1, "dropship_source_earnings": 1},
            )
            released_count = 0
            async for o in cursor:
                now = datetime.now(timezone.utc)
                # Atomic idempotency guard: only proceed if we're the first
                # worker to flip funds_released — cheap protection against
                # racing this loop against a manual /confirm-delivery.
                res = await db.orders.update_one(
                    {"id": o["id"], "funds_released": {"$ne": True}},
                    {"$set": {
                        "funds_released": True,
                        "delivery_confirmed_at": now.isoformat(),
                        "auto_confirmed": True,
                        "auto_confirmed_at": now,
                        "status": "delivered",
                    }},
                )
                if res.modified_count == 0:
                    continue
                try:
                    if float(o.get("seller_earnings", 0.0)) > 0:
                        await release_frozen(
                            o["seller_id"], float(o["seller_earnings"]),
                            f"Auto-released (buyer inactivity): {o.get('listing_title','sale')}",
                            o["id"], tx_type="sale_released",
                        )
                        await notify(
                            o["seller_id"], "wallet",
                            f"Funds released: {o.get('listing_title','')}",
                            f"${float(o['seller_earnings']):.2f} auto-released after "
                            f"{hours}h of buyer inactivity on order #{o['id'][:8]}.",
                            "/wallet",
                        )
                    if o.get("dropship_source_seller_id") and float(o.get("dropship_source_earnings", 0.0)) > 0:
                        await release_frozen(
                            o["dropship_source_seller_id"], float(o["dropship_source_earnings"]),
                            f"Auto-released dropship earnings: {o.get('listing_title','sale')}",
                            o["id"], tx_type="dropship_released",
                        )
                        await notify(
                            o["dropship_source_seller_id"], "wallet",
                            f"Dropship funds released: {o.get('listing_title','')}",
                            f"${float(o['dropship_source_earnings']):.2f} auto-released.",
                            "/wallet",
                        )
                    released_count += 1
                except Exception as inner:
                    logger.error(f"auto_confirm release failed for {o['id']}: {inner}")
            if released_count:
                logger.info(f"[auto-confirm] released {released_count} order(s) past {hours}h")
        except Exception as e:
            logger.warning(f"auto_confirm_delivery_loop error: {e}")
        interval = int(os.environ.get("AUTO_CONFIRM_INTERVAL_SEC", "3600"))
        await asyncio.sleep(max(60, interval))


async def auto_confirm_nudge_loop():
    """Buyer pre-release reminder — 24h before an order's escrow auto-releases,
    email + notify the buyer so they can either confirm early or flag a real
    problem. Fires exactly once per order (guarded by `pre_auto_confirm_nudge_sent`).

    Ticks every 30 min so a nudge lands in a tight ~30-min band around the
    24h-remaining mark.
    """
    await asyncio.sleep(45)
    while True:
        try:
            release_after_h = int(os.environ.get("AUTO_CONFIRM_AFTER_HOURS", "72"))
            nudge_before_h = int(os.environ.get("AUTO_CONFIRM_NUDGE_BEFORE_HOURS", "24"))
            # target: delivered_at + (release_after - nudge_before) has passed
            # → delivered_at <= now - (release_after - nudge_before)
            target_offset = release_after_h - nudge_before_h  # e.g. 72 - 24 = 48h
            now = datetime.now(timezone.utc)
            target_cutoff = now - timedelta(hours=target_offset)
            cursor = db.orders.find(
                {
                    "shipping_status": "delivered",
                    "shipping_delivered_at": {"$lte": target_cutoff},
                    "funds_released": {"$ne": True},
                    "pre_auto_confirm_nudge_sent": {"$ne": True},
                    "seller_earnings": {"$gt": 0},
                },
                {"_id": 0, "id": 1, "buyer_id": 1, "seller_id": 1,
                 "listing_title": 1, "listing_image": 1, "seller_name": 1,
                 "shipping_delivered_at": 1, "seller_earnings": 1},
            )
            sent = 0
            async for o in cursor:
                # Atomic guard so two workers can't nudge the same order twice.
                res = await db.orders.update_one(
                    {"id": o["id"], "pre_auto_confirm_nudge_sent": {"$ne": True}},
                    {"$set": {
                        "pre_auto_confirm_nudge_sent": True,
                        "pre_auto_confirm_nudge_at": now,
                    }},
                )
                if res.modified_count == 0:
                    continue
                # Compute the exact auto-release time to render in the email.
                delivered_at = o.get("shipping_delivered_at")
                if isinstance(delivered_at, datetime) and delivered_at.tzinfo is None:
                    delivered_at = delivered_at.replace(tzinfo=timezone.utc)
                release_at = (delivered_at + timedelta(hours=release_after_h)) if delivered_at else None
                release_str = release_at.strftime("%b %d at %H:%M UTC") if release_at else "in ~24h"
                title = f"Auto-releasing soon: {o.get('listing_title','your order')}"
                body = (
                    f"Your seller's earnings for this order auto-release on {release_str} "
                    f"(≈24h from now) if you haven't confirmed delivery. If everything arrived "
                    f"as expected, confirming now unlocks their payout immediately. Not delivered "
                    f"or an issue? Open a dispute and the release will be paused."
                )
                await notify(o["buyer_id"], "order", title, body, f"/profile?tab=orders")
                sent += 1
            if sent:
                logger.info(f"[auto-confirm-nudge] sent {sent} pre-release reminders")
        except Exception as e:
            logger.warning(f"auto_confirm_nudge_loop error: {e}")
        interval = int(os.environ.get("AUTO_CONFIRM_NUDGE_INTERVAL_SEC", "1800"))
        await asyncio.sleep(max(60, interval))


# =========================
# Live Cash-Out Ticker — extracted to `routers/wallet.py`
# (see wire()/include_router below). The route + its 15-second in-process
# cache both live in that module now; nothing in server.py references
# them anymore.
# =========================


async def _dispatch_auto_confirm(hours: int, dry_run: bool = False) -> dict:
    """Manual one-pass runner for the auto-confirm logic. Extracted so the
    admin trigger endpoint and the background loop share exactly one
    implementation."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    q = {
        "shipping_status": "delivered",
        "shipping_delivered_at": {"$lte": cutoff},
        "funds_released": {"$ne": True},
        "seller_earnings": {"$gt": 0},
    }
    matched = await db.orders.count_documents(q)
    if dry_run:
        return {"matched": matched, "released": 0, "dry_run": True, "threshold_hours": hours}
    released = 0
    cursor = db.orders.find(q, {"_id": 0})
    async for o in cursor:
        now = datetime.now(timezone.utc)
        res = await db.orders.update_one(
            {"id": o["id"], "funds_released": {"$ne": True}},
            {"$set": {
                "funds_released": True,
                "delivery_confirmed_at": now.isoformat(),
                "auto_confirmed": True,
                "auto_confirmed_at": now,
                "status": "delivered",
            }},
        )
        if res.modified_count == 0:
            continue
        try:
            if float(o.get("seller_earnings", 0.0)) > 0:
                await release_frozen(
                    o["seller_id"], float(o["seller_earnings"]),
                    f"Auto-released (buyer inactivity): {o.get('listing_title','sale')}",
                    o["id"], tx_type="sale_released",
                )
                await notify(
                    o["seller_id"], "wallet",
                    f"Funds released: {o.get('listing_title','')}",
                    f"${float(o['seller_earnings']):.2f} auto-released after "
                    f"{hours}h of buyer inactivity on order #{o['id'][:8]}.",
                    "/wallet",
                )
            if o.get("dropship_source_seller_id") and float(o.get("dropship_source_earnings", 0.0)) > 0:
                await release_frozen(
                    o["dropship_source_seller_id"], float(o["dropship_source_earnings"]),
                    f"Auto-released dropship earnings: {o.get('listing_title','sale')}",
                    o["id"], tx_type="dropship_released",
                )
                await notify(
                    o["dropship_source_seller_id"], "wallet",
                    f"Dropship funds released: {o.get('listing_title','')}",
                    f"${float(o['dropship_source_earnings']):.2f} auto-released.",
                    "/wallet",
                )
            released += 1
        except Exception as inner:
            logger.error(f"auto_confirm release failed for {o['id']}: {inner}")
    return {"matched": matched, "released": released, "dry_run": False, "threshold_hours": hours}


@api_router.post("/admin/auto-confirm/dispatch")
async def admin_auto_confirm_dispatch(
    payload: dict = Body(default={}),
    _admin: dict = Depends(require_admin),
):
    """One-click admin trigger for the buyer auto-confirm sweep.
    Body: {threshold_hours?: int (default from env 72), dry_run?: bool}."""
    hours = int(payload.get("threshold_hours", os.environ.get("AUTO_CONFIRM_AFTER_HOURS", "72")))
    dry_run = bool(payload.get("dry_run", False))
    return await _dispatch_auto_confirm(hours=hours, dry_run=dry_run)


# =========================
# Phase 12: Disputes & Returns (routes moved to routers/disputes.py)
# =========================



# =========================
# Seed
# =========================
@api_router.post("/seed")
async def seed_data():
    """Idempotent seed. Only seeds when categories collection is empty."""
    existing = await db.categories.count_documents({})
    if existing > 0:
        return {"ok": True, "seeded": False, "message": "Already seeded"}

    categories_data = [
        {"name": "Women", "slug": "women", "icon": "shirt", "order": 1},
        {"name": "Men", "slug": "men", "icon": "shirt", "order": 2},
        {"name": "Kids", "slug": "kids", "icon": "baby", "order": 3},
        {"name": "Electronics", "slug": "electronics", "icon": "smartphone", "order": 4},
        {"name": "Home", "slug": "home", "icon": "home", "order": 5},
        {"name": "Beauty", "slug": "beauty", "icon": "sparkles", "order": 6},
        {"name": "Sports", "slug": "sports", "icon": "dumbbell", "order": 7},
        {"name": "Toys", "slug": "toys", "icon": "gamepad-2", "order": 8},
        {"name": "Books", "slug": "books", "icon": "book", "order": 9},
        {"name": "Handmade", "slug": "handmade", "icon": "palette", "order": 10},
        {"name": "Vintage", "slug": "vintage", "icon": "clock", "order": 11},
        {"name": "Other", "slug": "other", "icon": "package", "order": 12},
        {"name": "Shoes", "slug": "shoes", "icon": "footprints", "order": 13},
        {"name": "Bags & Accessories", "slug": "bags-accessories", "icon": "briefcase", "order": 14},
        {"name": "Jewelry & Watches", "slug": "jewelry-watches", "icon": "gem", "order": 15},
        {"name": "Pet Supplies", "slug": "pet-supplies", "icon": "paw-print", "order": 16},
        {"name": "Automotive", "slug": "automotive", "icon": "car", "order": 17},
        {"name": "Garden & Outdoor", "slug": "garden-outdoor", "icon": "flower-2", "order": 18},
        {"name": "Musical Instruments", "slug": "musical-instruments", "icon": "music", "order": 19},
        {"name": "Office & Craft", "slug": "office-craft", "icon": "pen-tool", "order": 20},
        {"name": "Collectibles", "slug": "collectibles", "icon": "medal", "order": 21},
    ]
    cat_docs = [Category(**c).model_dump() for c in categories_data]
    await db.categories.insert_many(cat_docs)

    # Admin user
    admin_id = str(uuid.uuid4())
    admin = {
        "id": admin_id,
        "email": "admin@ocean.local",
        "username": "admin",
        "role": "admin",
        "avatar": None,
        "bio": "Platform administrator",
        "rating": 5.0,
        "sales_count": 0,
        "is_active": True,
        "created_at": datetime.now(timezone.utc),
        "password_hash": hash_password("admin123"),
    }
    await db.users.insert_one(admin)

    # Demo sellers
    sellers = []
    for i, uname in enumerate(["sophia_style", "urban_finds", "vintage_maven", "tech_haven", "cozy_home"]):
        uid = str(uuid.uuid4())
        sellers.append({
            "id": uid,
            "email": f"{uname}@demo.local",
            "username": uname,
            "role": "user",
            "avatar": None,
            "bio": f"Passionate reseller — {uname.replace('_', ' ').title()}",
            "rating": round(4.5 + (i * 0.1), 1),
            "sales_count": 10 + i * 15,
            "is_active": True,
            "created_at": datetime.now(timezone.utc),
            "password_hash": hash_password("demo1234"),
        })
    await db.users.insert_many(sellers)

    # Real product listings come from the Apify Amazon crawler, not this seed.
    # Trigger the sync via /api/admin/sync/apify (auto-runs weekly and on empty startup too).

    return {
        "ok": True,
        "seeded": True,
        "categories": len(cat_docs),
        "users": len(sellers) + 1,
        "listings": 0,
        "note": "Categories, admin, and demo sellers seeded. Listings come from Apify — trigger /api/admin/sync/apify to import real Amazon products.",
        "admin_credentials": {"email": "admin@ocean.local", "password": "admin123"},
    }


@api_router.get("/")
async def root():
    return {"message": "Ocean Clone API", "status": "ok"}


# =========================
# Language-aware SEO — /sitemap.xml + /robots.txt
# =========================
# We ship one HTML bundle with client-side i18n, so instead of duplicating
# every URL under `/en/`, `/ja/`, etc. we emit sitemap entries with an
# xhtml:link rel="alternate" hreflang="..." row per language. Google, Bing,
# and Yandex all consume this format and each localized snippet ranks in
# its own regional SERP without cannibalising.
_SITEMAP_LANGS = ["en", "es", "fr", "de", "pt", "it", "ja", "zh", "ar", "hi", "ko", "ru"]


def _xml_escape(s: str) -> str:
    return (
        (s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def _sitemap_url_block(path: str, lastmod: Optional[str], origin: str, changefreq: str = "weekly", priority: str = "0.5") -> str:
    """Emit one <url> block with all language alternates."""
    default = f"{origin}{path}"
    alts = "".join(
        f'<xhtml:link rel="alternate" hreflang="{lang}" href="{_xml_escape(default)}?lang={lang}"/>'
        for lang in _SITEMAP_LANGS
    )
    alts += f'<xhtml:link rel="alternate" hreflang="x-default" href="{_xml_escape(default)}"/>'
    lm = f"<lastmod>{_xml_escape(lastmod)}</lastmod>" if lastmod else ""
    return (
        f"<url><loc>{_xml_escape(default)}</loc>{lm}"
        f"<changefreq>{changefreq}</changefreq><priority>{priority}</priority>"
        f"{alts}</url>"
    )


_SITEMAP_LISTINGS_PER_SHARD = 40_000  # under Google's 50k / 50MB per-file limit


def _resolve_origin(request: Request) -> str:
    fwd_host = request.headers.get("x-forwarded-host")
    fwd_proto = request.headers.get("x-forwarded-proto", "https")
    if fwd_host:
        return f"{fwd_proto}://{fwd_host}".rstrip("/")
    origin = os.environ.get("BACKEND_PUBLIC_URL") or os.environ.get("FRONTEND_ORIGIN")
    if not origin:
        from services.email_templates import FRONTEND as _FE
        origin = _FE
    return origin.rstrip("/")


async def _listings_total() -> int:
    return await db.listings.count_documents({"status": "active"})


@app.get("/api/sitemap_index.xml")
async def sitemap_index(request: Request):
    """Sitemap index (RFC-compliant) — always returned regardless of catalog
    size so bots have a single stable discovery URL. Points at:
      * `/api/sitemap-core.xml`         (homepage + marketplace + stores)
      * `/api/sitemap-categories.xml`   (all category pages)
      * `/api/sitemap-storefronts.xml`  (up to 5k storefronts)
      * `/api/sitemap-listings-{N}.xml` (40k listings per shard — as many
        shards as active listings require, scales past 45k / 50k / infinity)
    """
    origin = _resolve_origin(request)
    now_iso = datetime.now(timezone.utc).date().isoformat()
    total = await _listings_total()
    shard_count = max(1, (total + _SITEMAP_LISTINGS_PER_SHARD - 1) // _SITEMAP_LISTINGS_PER_SHARD)

    entries = [
        f"<sitemap><loc>{origin}/api/sitemap-core.xml</loc><lastmod>{now_iso}</lastmod></sitemap>",
        f"<sitemap><loc>{origin}/api/sitemap-categories.xml</loc><lastmod>{now_iso}</lastmod></sitemap>",
        f"<sitemap><loc>{origin}/api/sitemap-storefronts.xml</loc><lastmod>{now_iso}</lastmod></sitemap>",
    ]
    for n in range(1, shard_count + 1):
        entries.append(
            f"<sitemap><loc>{origin}/api/sitemap-listings-{n}.xml</loc>"
            f"<lastmod>{now_iso}</lastmod></sitemap>"
        )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + "".join(entries) + "</sitemapindex>"
    )
    return Response(content=xml, media_type="application/xml",
                    headers={"Cache-Control": "public, max-age=3600, s-maxage=3600"})


def _wrap_urlset(blocks: List[str]) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
        'xmlns:xhtml="http://www.w3.org/1999/xhtml">'
        + "".join(blocks) + "</urlset>"
    )


@app.get("/api/sitemap-core.xml")
async def sitemap_core(request: Request):
    origin = _resolve_origin(request)
    now_iso = datetime.now(timezone.utc).date().isoformat()
    blocks = [
        _sitemap_url_block("/", now_iso, origin, "daily", "1.0"),
        _sitemap_url_block("/marketplace", now_iso, origin, "daily", "0.9"),
        _sitemap_url_block("/marketplace/stores", now_iso, origin, "daily", "0.9"),
    ]
    return Response(content=_wrap_urlset(blocks), media_type="application/xml",
                    headers={"Cache-Control": "public, max-age=3600, s-maxage=3600"})


@app.get("/api/sitemap-categories.xml")
async def sitemap_categories(request: Request):
    origin = _resolve_origin(request)
    now_iso = datetime.now(timezone.utc).date().isoformat()
    blocks: List[str] = []
    async for c in db.categories.find({}, {"_id": 0, "id": 1, "slug": 1}):
        slug = c.get("slug") or c.get("id")
        blocks.append(_sitemap_url_block(f"/search?category={slug}", now_iso, origin, "daily", "0.7"))
    return Response(content=_wrap_urlset(blocks), media_type="application/xml",
                    headers={"Cache-Control": "public, max-age=3600, s-maxage=3600"})


@app.get("/api/sitemap-storefronts.xml")
async def sitemap_storefronts(request: Request):
    origin = _resolve_origin(request)
    now_iso = datetime.now(timezone.utc).date().isoformat()
    blocks: List[str] = []
    async for s in db.stores.find({"status": {"$ne": "banned"}}, {"_id": 0, "slug": 1, "updated_at": 1}).limit(5000):
        if not s.get("slug"):
            continue
        lm = s.get("updated_at")
        if isinstance(lm, datetime):
            lm = lm.date().isoformat()
        blocks.append(_sitemap_url_block(f"/store/{s['slug']}", lm or now_iso, origin, "weekly", "0.6"))
    return Response(content=_wrap_urlset(blocks), media_type="application/xml",
                    headers={"Cache-Control": "public, max-age=3600, s-maxage=3600"})


@app.get("/api/sitemap-listings-{shard}.xml")
async def sitemap_listings_shard(shard: int, request: Request):
    """One shard of ≤40k listing URLs. Cursor paginated (skip/limit) so we
    stay well under Google's 50k / 50MB per-file limit forever."""
    if shard < 1:
        raise HTTPException(400, "shard must be >= 1")
    origin = _resolve_origin(request)
    now_iso = datetime.now(timezone.utc).date().isoformat()
    skip = (shard - 1) * _SITEMAP_LISTINGS_PER_SHARD
    blocks: List[str] = []
    async for l in db.listings.find(
        {"status": "active"},
        {"_id": 0, "id": 1, "updated_at": 1, "created_at": 1},
    ).sort("updated_at", -1).skip(skip).limit(_SITEMAP_LISTINGS_PER_SHARD):
        lm = l.get("updated_at") or l.get("created_at")
        if isinstance(lm, datetime):
            lm = lm.date().isoformat()
        blocks.append(_sitemap_url_block(f"/listing/{l['id']}", lm or now_iso, origin, "weekly", "0.7"))
    if not blocks:
        # Empty shard → return an empty urlset with 404 so bots stop trying
        # to fetch out-of-range shard numbers.
        raise HTTPException(404, "empty shard")
    return Response(content=_wrap_urlset(blocks), media_type="application/xml",
                    headers={"Cache-Control": "public, max-age=3600, s-maxage=3600"})


@app.get("/api/sitemap.xml")
async def sitemap_xml(request: Request):
    """Legacy single-file sitemap kept for backwards-compat with any bots
    that discovered it before the index existed. It emits the first
    shard's worth of listings + core + categories + storefronts. For the
    canonical modern discovery URL, see `/api/sitemap_index.xml` (which is
    what our robots.txt advertises)."""
    origin = _resolve_origin(request)
    now_iso = datetime.now(timezone.utc).date().isoformat()

    blocks: List[str] = []
    for path in ("/", "/marketplace", "/marketplace/stores"):
        blocks.append(_sitemap_url_block(path, now_iso, origin, "daily", "1.0" if path == "/" else "0.9"))
    async for c in db.categories.find({}, {"_id": 0, "id": 1, "slug": 1}):
        slug = c.get("slug") or c.get("id")
        blocks.append(_sitemap_url_block(f"/search?category={slug}", now_iso, origin, "daily", "0.7"))
    async for s in db.stores.find({"status": {"$ne": "banned"}}, {"_id": 0, "slug": 1, "updated_at": 1}).limit(5000):
        if not s.get("slug"):
            continue
        lm = s.get("updated_at")
        if isinstance(lm, datetime):
            lm = lm.date().isoformat()
        blocks.append(_sitemap_url_block(f"/store/{s['slug']}", lm or now_iso, origin, "weekly", "0.6"))
    async for l in db.listings.find(
        {"status": "active"},
        {"_id": 0, "id": 1, "updated_at": 1, "created_at": 1},
    ).sort("updated_at", -1).limit(_SITEMAP_LISTINGS_PER_SHARD):
        lm = l.get("updated_at") or l.get("created_at")
        if isinstance(lm, datetime):
            lm = lm.date().isoformat()
        blocks.append(_sitemap_url_block(f"/listing/{l['id']}", lm or now_iso, origin, "weekly", "0.7"))
    return Response(content=_wrap_urlset(blocks), media_type="application/xml",
                    headers={"Cache-Control": "public, max-age=3600, s-maxage=3600"})


@app.get("/api/robots.txt")
async def robots_txt(request: Request):
    origin = _resolve_origin(request)
    body = (
        "User-agent: *\n"
        "Disallow: /admin\n"
        "Disallow: /api/\n"
        "Allow: /api/sitemap_index.xml\n"
        "Allow: /api/sitemap.xml\n"
        "Allow: /api/sitemap-\n"
        f"Sitemap: {origin}/api/sitemap_index.xml\n"
    )
    return Response(content=body, media_type="text/plain", headers={"Cache-Control": "public, max-age=3600"})


app.include_router(api_router)

# --- Extracted routers ---------------------------------------------------
# Each of these modules lives in `routers/` and reaches back for the DB
# handle (and other shared refs) via a small `wire(...)` call so we don't
# have circular imports. Keep new extractions grouped here.
from routers import wallet as _wallet_ext_router  # noqa: E402
_wallet_ext_router.wire(db=db)
app.include_router(_wallet_ext_router.router, prefix="/api")


# =========================
# Sitemap Search Console Ping — auto-ping Google + Bing when the sitemap
# meaningfully changes (a new/updated/deleted listing) so newly-published
# products get indexed within minutes instead of days.
#
# The ping URLs are the classic public endpoints — they don't require an
# API key. We hard rate-limit to at most one round-trip per 15 min per
# origin (persisted in the `settings` doc) so a burst of imports doesn't
# spam either search engine. Fires in an asyncio task so the caller's HTTP
# request returns immediately.
# =========================
_SITEMAP_PING_MIN_INTERVAL_SEC = int(os.environ.get("SITEMAP_PING_MIN_INTERVAL_SEC", "900"))


async def _get_indexnow_key() -> str:
    """Fetch (or lazily create) the IndexNow verification key. Stored in the
    settings singleton so it persists across restarts and is served at
    /api/indexnow-key.txt for the ownership check."""
    settings = await db.settings.find_one({"_id": "singleton"}, {"_id": 0, "indexnow_key": 1}) or {}
    key = settings.get("indexnow_key")
    if key:
        return key
    key = uuid.uuid4().hex  # 32 char hex → satisfies IndexNow's 8-128 char rule
    await db.settings.update_one(
        {"_id": "singleton"}, {"$set": {"indexnow_key": key}}, upsert=True,
    )
    return key


@app.get("/api/indexnow-key.txt", include_in_schema=False)
async def indexnow_key_file():
    """Ownership verification file for the IndexNow protocol. Bing/Yandex
    fetch this exact URL and match the body against the `key` in each
    submission before honoring it."""
    key = await _get_indexnow_key()
    return Response(content=key, media_type="text/plain",
                    headers={"Cache-Control": "public, max-age=86400"})


async def _ping_sitemap_now(origin: str, changed_urls: Optional[List[str]] = None) -> Dict[str, Any]:
    """Notify search engines that the sitemap changed.

    Real-world state (Feb 2026):
      * Google removed its classic `/ping?sitemap=…` endpoint in June 2023.
        Modern discovery is via robots.txt (already advertised) + Search
        Console API (OAuth-gated, not in scope here).
      * Bing removed the classic ping too, but honors IndexNow POSTs.
      * IndexNow is a shared protocol — one POST to api.indexnow.org
        propagates to Bing, Yandex, Seznam, Naver, Yep, and any other
        participating engine.

    We POST to IndexNow with the sitemap index URL (and any recently-changed
    listing URLs). Falls back gracefully if the network call fails.
    """
    import httpx
    results: Dict[str, Any] = {"origin": origin, "targets": {}}
    key = await _get_indexnow_key()
    urls = [f"{origin}/api/sitemap_index.xml"]
    if changed_urls:
        urls.extend([u for u in changed_urls if u.startswith(origin)][:9000])
    payload = {
        "host": origin.split("://", 1)[-1],
        "key": key,
        "keyLocation": f"{origin}/api/indexnow-key.txt",
        "urlList": urls,
    }
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        # Primary IndexNow endpoint (propagates to all participating engines).
        try:
            r = await client.post("https://api.indexnow.org/indexnow", json=payload,
                                  headers={"Content-Type": "application/json; charset=utf-8"})
            results["targets"]["indexnow"] = {"status": r.status_code, "ok": r.status_code in (200, 202)}
        except Exception as e:
            results["targets"]["indexnow"] = {"status": None, "ok": False, "error": str(e)[:200]}
        # Bing's own endpoint as a belt-and-braces backup (same payload).
        try:
            r = await client.post("https://www.bing.com/indexnow", json=payload,
                                  headers={"Content-Type": "application/json; charset=utf-8"})
            results["targets"]["bing_indexnow"] = {"status": r.status_code, "ok": r.status_code in (200, 202)}
        except Exception as e:
            results["targets"]["bing_indexnow"] = {"status": None, "ok": False, "error": str(e)[:200]}
    results["urls_submitted"] = len(urls)
    now = datetime.now(timezone.utc)
    await db.settings.update_one(
        {"_id": "singleton"},
        {"$set": {
            "sitemap_ping_last_at": now,
            "sitemap_ping_last_result": results,
            "sitemap_ping_pending": False,
        }},
        upsert=True,
    )
    logger.info(f"[sitemap-ping] {origin} → IndexNow: " + ", ".join(
        f"{k}={v.get('status')}" for k, v in results["targets"].items()
    ))
    return results


async def schedule_sitemap_ping(origin: Optional[str] = None, changed_listing_id: Optional[str] = None) -> None:
    """Rate-limited entry point. Call from listing create/update/delete —
    coalesces bursts into a single ping per interval."""
    if os.environ.get("SITEMAP_PING_ENABLED", "1") in ("0", "false", "no"):
        return
    if not origin:
        origin = os.environ.get("BACKEND_PUBLIC_URL")
        if not origin:
            try:
                from services.email_templates import FRONTEND as _FE
                origin = _FE
            except Exception:
                return
    origin = origin.rstrip("/")
    changed_urls: List[str] = []
    if changed_listing_id:
        changed_urls.append(f"{origin}/listing/{changed_listing_id}")

    settings = await db.settings.find_one({"_id": "singleton"}, {"_id": 0, "sitemap_ping_last_at": 1, "sitemap_ping_pending": 1}) or {}
    last = settings.get("sitemap_ping_last_at")
    if isinstance(last, datetime):
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        elapsed = (datetime.now(timezone.utc) - last).total_seconds()
        if elapsed < _SITEMAP_PING_MIN_INTERVAL_SEC:
            # Coalesce: mark pending so the periodic sweep picks it up when the
            # window expires, don't fire right now.
            update: dict = {"sitemap_ping_pending": True}
            if changed_urls:
                # Buffer up to 1000 changed URLs for the next flush so bots
                # get precise re-crawl targets, not just the index.
                await db.settings.update_one(
                    {"_id": "singleton"},
                    {"$set": update, "$addToSet": {"sitemap_ping_pending_urls": {"$each": changed_urls}}},
                    upsert=True,
                )
            else:
                await db.settings.update_one({"_id": "singleton"}, {"$set": update}, upsert=True)
            return
    # Fire in background so the calling request stays snappy.
    asyncio.create_task(_ping_sitemap_now(origin, changed_urls or None))


async def sitemap_ping_sweeper():
    """Periodic sweep to fire any coalesced ping that was queued during a
    rate-limit window. Runs every 5 min — safe overhead."""
    await asyncio.sleep(120)
    while True:
        try:
            settings = await db.settings.find_one(
                {"_id": "singleton"},
                {"_id": 0, "sitemap_ping_pending": 1, "sitemap_ping_last_at": 1,
                 "sitemap_ping_pending_urls": 1},
            ) or {}
            if settings.get("sitemap_ping_pending"):
                last = settings.get("sitemap_ping_last_at")
                elapsed = _SITEMAP_PING_MIN_INTERVAL_SEC + 1
                if isinstance(last, datetime):
                    if last.tzinfo is None:
                        last = last.replace(tzinfo=timezone.utc)
                    elapsed = (datetime.now(timezone.utc) - last).total_seconds()
                if elapsed >= _SITEMAP_PING_MIN_INTERVAL_SEC:
                    origin = os.environ.get("BACKEND_PUBLIC_URL")
                    if not origin:
                        try:
                            from services.email_templates import FRONTEND as _FE
                            origin = _FE
                        except Exception:
                            origin = None
                    if origin:
                        pending_urls = settings.get("sitemap_ping_pending_urls") or []
                        await _ping_sitemap_now(origin.rstrip("/"), pending_urls or None)
                        # Clear the buffer once flushed.
                        await db.settings.update_one(
                            {"_id": "singleton"},
                            {"$unset": {"sitemap_ping_pending_urls": ""}},
                        )
        except Exception as e:
            logger.warning(f"sitemap_ping_sweeper error: {e}")
        await asyncio.sleep(300)


@app.post("/api/admin/sitemap/ping")
async def admin_sitemap_ping(_admin: dict = Depends(require_admin)):
    """Force an immediate sitemap ping (bypasses the rate limit) and returns
    the raw response from Google + Bing for debugging."""
    origin = os.environ.get("BACKEND_PUBLIC_URL")
    if not origin:
        try:
            from services.email_templates import FRONTEND as _FE
            origin = _FE
        except Exception:
            raise HTTPException(500, "No public origin configured")
    return await _ping_sitemap_now(origin.rstrip("/"))


@app.get("/api/admin/sitemap/ping/status")
async def admin_sitemap_ping_status(_admin: dict = Depends(require_admin)):
    """Introspection endpoint — surfaces the last ping timestamp, pending
    flag, and last per-target status codes so admins can debug indexing."""
    doc = await db.settings.find_one(
        {"_id": "singleton"},
        {"_id": 0, "sitemap_ping_last_at": 1, "sitemap_ping_last_result": 1, "sitemap_ping_pending": 1},
    ) or {}
    last = doc.get("sitemap_ping_last_at")
    if isinstance(last, datetime):
        doc["sitemap_ping_last_at"] = last.isoformat()
    doc["min_interval_sec"] = _SITEMAP_PING_MIN_INTERVAL_SEC
    return doc
app.include_router(search_router, prefix="/api")
app.include_router(discovery_router, prefix="/api")
app.include_router(users_router, prefix="/api")
app.include_router(newsletter_router, prefix="/api")
app.include_router(google_auth_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(onboarding_nudges_router, prefix="/api")
app.include_router(stores_search_router, prefix="/api")
app.include_router(shopping_router, prefix="/api")
app.include_router(listings_router, prefix="/api")
app.include_router(personalized_router, prefix="/api")
app.include_router(checkout_router, prefix="/api")
app.include_router(coupons_router, prefix="/api")
app.include_router(scraper_router, prefix="/api")
app.include_router(store_boosts_router, prefix="/api")
app.include_router(products_router, prefix="/api")
app.include_router(apify_runs_router, prefix="/api")
app.include_router(support_router, prefix="/api")
app.include_router(otp_router, prefix="/api")
# Deliverability plumbing: bounce webhook, one-click unsubscribe,
# suppression-list admin. Also wires services.mailer to consult
# suppression_list before every send and persists every send to
# email_delivery_log for admin audit.
from routers.mailops import router as _mailops_router, is_suppressed as _is_suppressed
from services import mailer as _mailer_module
_mailer_module.register_suppression_check(_is_suppressed)

# Professional-grade email delivery log — every send + failure recorded
async def _email_delivery_writer(entry: dict) -> None:
    try:
        await db.email_delivery_log.insert_one(entry)
    except Exception:
        pass

async def _email_idempotency_lookup(key: str):
    if not key:
        return None
    from datetime import datetime as _dt, timezone as _tz, timedelta as _td
    cutoff = _dt.now(_tz.utc) - _td(seconds=60)
    return await db.email_delivery_log.find_one(
        {"idempotency_key": key, "status": "sent", "at": {"$gte": cutoff}},
        {"_id": 0},
    )

_mailer_module.register_delivery_writer(_email_delivery_writer)
_mailer_module.register_idempotency_lookup(_email_idempotency_lookup)
app.include_router(_mailops_router, prefix="/api")
app.include_router(reviews_router, prefix="/api")
app.include_router(messaging_router, prefix="/api")
app.include_router(notifications_router, prefix="/api")
app.include_router(affiliate_router, prefix="/api")
app.include_router(disputes_router, prefix="/api")
app.include_router(shipping_router, prefix="/api")

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@app.on_event("startup")
async def startup():
    await db.users.create_index("email", unique=True)
    await db.users.create_index("username", unique=True)
    await db.users.create_index("referral_code")
    # Email OTP indexes (TTL + lookup)
    from services import email_otp as _email_otp
    try:
        await _email_otp.ensure_indexes(db)
    except Exception as e:
        logger.warning(f"OTP index setup skipped: {e}")
    await db.listings.create_index("seller_id")
    await db.listings.create_index("category_id")
    await db.listings.create_index("status")
    await db.listings.create_index("store_id")
    await db.favorites.create_index([("user_id", 1), ("listing_id", 1)], unique=True)
    await db.cart_items.create_index([("user_id", 1), ("listing_id", 1)], unique=True)
    await db.stores.create_index("slug", unique=True)
    await db.stores.create_index("owner_id")
    await db.affiliate_links.create_index("code", unique=True)
    await db.affiliate_links.create_index("affiliate_user_id")
    await db.wallet_txs.create_index([("user_id", 1), ("created_at", -1)])
    await db.withdrawals.create_index("user_id")
    await db.withdrawals.create_index("status")
    await db.reviews.create_index("seller_id")
    await db.reviews.create_index("listing_id")
    await db.reviews.create_index([("order_id", 1), ("reviewer_id", 1)], unique=True)
    await db.messages.create_index([("listing_id", 1), ("sender_id", 1), ("receiver_id", 1)])
    await db.recently_viewed.create_index([("user_id", 1), ("viewed_at", -1)])
    await db.recently_viewed.create_index([("user_id", 1), ("listing_id", 1)], unique=True)
    await db.notifications.create_index([("user_id", 1), ("created_at", -1)])
    # Permanent products catalog (webhook-ingested; no TTL by design)
    await db.products.create_index("id", unique=True)
    await db.products.create_index("sku", sparse=True)
    await db.products.create_index("source_url", sparse=True)
    await db.products.create_index([("is_active", 1), ("created_at", -1)])
    await db.products.create_index("category")

    # Migrate existing users: add referral_code, wallet_balance if missing
    async for u in db.users.find({"referral_code": {"$exists": False}}, {"_id": 0, "id": 1}):
        await db.users.update_one(
            {"id": u["id"]},
            {"$set": {
                "referral_code": uuid.uuid4().hex[:8].upper(),
                "wallet_balance": 0.0,
                "referred_by": None,
                "store_id": None,
            }},
        )
    # Migrate: add Phase 1 verification fields for existing users
    await db.users.update_many(
        {"email_verified": {"$exists": False}},
        {"$set": {
            "email_verified": False,
            "email_verified_at": None,
            "phone": None,
            "phone_verified": False,
            "phone_verified_at": None,
            "seller_status": "none",
            "stripe_account_id": None,
            "stripe_status": "none",
        }},
    )
    # Admin account should be treated as verified by default
    await db.users.update_many(
        {"role": "admin", "email_verified": False},
        {"$set": {"email_verified": True, "email_verified_at": datetime.now(timezone.utc), "seller_status": "approved"}},
    )
    # Ensure settings doc exists
    await get_settings()

    # Ledger backfill: tag legacy wallet_txs docs with an explicit `bucket`
    # field so reconciliation aggregations can filter frozen vs available
    # without double-counting sale_released pairs. Idempotent.
    try:
        result = await ledger.backfill_bucket_tags(db)
        if any(result.values()):
            logger.info(f"[startup] wallet_txs bucket backfill: {result}")
    except Exception as e:
        logger.error(f"[startup] wallet_txs bucket backfill failed: {e}")

    # Start background live-sync simulation
    async def live_sync_loop():
        # Wait a bit to let the app finish initializing
        await asyncio.sleep(30)
        while True:
            try:
                await simulate_live_update(db)
            except Exception as e:
                logger.error(f"live_sync tick failed: {e}")
            await asyncio.sleep(60)  # tick every 60 seconds

    async def apify_auto_sync_loop():
        """Monthly Apify auto-sync, resume-safe across container restarts.

        On startup: reads last_sync_at from `sync_state`; if overdue, kicks off
        immediately, else sleeps only until the next 30-day mark.
        """
        INTERVAL_DAYS = 30
        INTERVAL_SECONDS = 60 * 60 * 24 * INTERVAL_DAYS
        # Small startup delay so DB, other loops, and health checks settle first.
        await asyncio.sleep(60)
        while True:
            try:
                state = await db.sync_state.find_one({"id": "apify"}, {"_id": 0}) or {}
                if not state.get("auto_schedule_enabled", True):
                    # Feature is off — check again in a day
                    await asyncio.sleep(60 * 60 * 24)
                    continue

                # Auto-recover a stuck sync_running lock (e.g. after a crash /
                # a container restart in the middle of an Apify actor call).
                # Cleared after 30 minutes with no progress so the front-end
                # status endpoint doesn't misleadingly say "Sync in progress"
                # for hours after a real orphan.
                if state.get("sync_running"):
                    started = state.get("started_at")
                    if started and started.tzinfo is None:
                        started = started.replace(tzinfo=timezone.utc)
                    if not started or (datetime.now(timezone.utc) - started).total_seconds() > 60 * 30:
                        logger.warning("Clearing stuck Apify sync_running lock (>30m old)")
                        await db.sync_state.update_one(
                            {"id": "apify"},
                            {"$set": {"sync_running": False, "message": "Auto-cleared stuck lock"}},
                        )
                        state["sync_running"] = False

                last = state.get("last_sync_at")
                last_attempt = state.get("last_attempt_at")
                now = datetime.now(timezone.utc)
                # Honor a persisted next_scheduled_at from the previous
                # (possibly-failed) attempt — prevents tight retry loops when
                # Apify credits are exhausted / actor errors keep firing.
                next_scheduled = state.get("next_scheduled_at")
                if next_scheduled:
                    if hasattr(next_scheduled, "tzinfo") and next_scheduled.tzinfo is None:
                        next_scheduled = next_scheduled.replace(tzinfo=timezone.utc)
                    if next_scheduled > now:
                        wait = (next_scheduled - now).total_seconds()
                    elif last:
                        if last.tzinfo is None:
                            last = last.replace(tzinfo=timezone.utc)
                        elapsed = (now - last).total_seconds()
                        wait = max(0, INTERVAL_SECONDS - elapsed)
                    else:
                        wait = 0
                elif last:
                    # Handle both naive and aware
                    if last.tzinfo is None:
                        last = last.replace(tzinfo=timezone.utc)
                    elapsed = (now - last).total_seconds()
                    wait = max(0, INTERVAL_SECONDS - elapsed)
                else:
                    # Never synced — run right away
                    wait = 0

                # Additional guard: if the last actor attempt failed within the
                # last hour, back off 6h to avoid spamming a quota-exhausted API
                if last_attempt and not last:
                    if hasattr(last_attempt, "tzinfo") and last_attempt.tzinfo is None:
                        last_attempt = last_attempt.replace(tzinfo=timezone.utc)
                    since_attempt = (now - last_attempt).total_seconds()
                    if since_attempt < 6 * 3600:
                        wait = max(wait, 6 * 3600 - since_attempt)

                if wait > 0:
                    next_scheduled_at = now + timedelta(seconds=wait)
                    await db.sync_state.update_one(
                        {"id": "apify"},
                        {"$set": {
                            "next_scheduled_at": next_scheduled_at,
                            "schedule_interval_days": INTERVAL_DAYS,
                            "auto_schedule_enabled": True,
                        }},
                        upsert=True,
                    )
                    logger.info(f"Next Apify auto-sync scheduled at {next_scheduled_at.isoformat()}")
                    await asyncio.sleep(wait)

                # Time to run — but only if not already running
                state = await db.sync_state.find_one({"id": "apify"}, {"_id": 0}) or {}
                if not state.get("sync_running"):
                    logger.info(f"Starting scheduled Apify auto-sync (every {INTERVAL_DAYS} days)")
                    # Stamp the attempt BEFORE calling so a hard failure still
                    # advances the cooldown clock even if the actor throws.
                    await db.sync_state.update_one(
                        {"id": "apify"},
                        {"$set": {
                            "last_attempt_at": datetime.now(timezone.utc),
                            "next_scheduled_at": datetime.now(timezone.utc) + timedelta(hours=6),
                        }},
                        upsert=True,
                    )
                    result = await import_from_apify(db, target_count=20000, replace_existing=False)
                    if isinstance(result, dict) and not result.get("ok", True):
                        # Actor failed (quota exhausted, etc.) — persist 6h cooldown
                        logger.warning(f"Scheduled Apify auto-sync failed: {result.get('error') or result}")
                        await db.sync_state.update_one(
                            {"id": "apify"},
                            {"$set": {"next_scheduled_at": datetime.now(timezone.utc) + timedelta(hours=6)}},
                        )
                        await asyncio.sleep(6 * 3600)
                        continue
            except Exception as e:
                logger.error(f"apify auto-sync loop failed: {e}")
                # Back off a day before retrying on hard error
                await asyncio.sleep(60 * 60 * 24)
                continue

            # Schedule the next run marker
            next_scheduled_at = datetime.now(timezone.utc) + timedelta(seconds=INTERVAL_SECONDS)
            await db.sync_state.update_one(
                {"id": "apify"},
                {"$set": {"next_scheduled_at": next_scheduled_at}},
                upsert=True,
            )

    asyncio.create_task(live_sync_loop())
    asyncio.create_task(apify_auto_sync_loop())
    asyncio.create_task(shipping_progress_loop())
    asyncio.create_task(flash_deals_rotation_loop())
    asyncio.create_task(wishlist_digest_loop())
    asyncio.create_task(newsletter_digest_loop())
    asyncio.create_task(escrow_digest_loop())
    asyncio.create_task(auto_confirm_delivery_loop())
    asyncio.create_task(auto_confirm_nudge_loop())
    asyncio.create_task(pickup_expiry_loop())
    asyncio.create_task(pickup_reminder_loop())
    asyncio.create_task(store_health_sweep_loop())
    asyncio.create_task(sitemap_ping_sweeper())
    asyncio.create_task(_self_ping_loop())


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
