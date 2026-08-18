from fastapi import FastAPI, APIRouter, HTTPException, Depends, Query, status, UploadFile, File, Header, Response, Request, Body
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import base64
import secrets
import random
import re
import json as _json
import httpx
from pathlib import Path
from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional, Literal
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
from routers.stores_search import router as stores_search_router
from routers.shopping import router as shopping_router
from routers.listings import router as listings_router
from routers.personalized import router as personalized_router
from routers.checkout import router as checkout_router
from routers.coupons import router as coupons_router
from routers.stripe_payments import router as stripe_payments_router
from routers.scraper import router as scraper_router
from routers.store_boosts import router as store_boosts_router


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
APP_NAME = "mercari-clone"
_storage_key: Optional[str] = None

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)

app = FastAPI(title="Mercari Clone API")
api_router = APIRouter(prefix="/api")

# Static mount for scraper/local media uploads — served at /api/uploads/*
# so it flows through the same Kubernetes ingress rule as the rest of the API.
from fastapi.staticfiles import StaticFiles
_UPLOADS_DIR = Path(os.environ.get("MEDIA_LOCAL_ROOT") or "/app/backend/uploads")
_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/api/uploads", StaticFiles(directory=str(_UPLOADS_DIR)), name="uploads")


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
    created_at: datetime

class AuthResponse(BaseModel):
    token: str
    user: UserPublic

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
    title: str
    description: str
    price: float
    original_price: Optional[float] = None
    category_id: str
    category_name: str
    condition: Literal["new", "like_new", "good", "fair", "poor"] = "good"
    brand: Optional[str] = ""
    size: Optional[str] = ""
    color: Optional[str] = ""
    images: List[str] = []
    shipping_paid_by: Literal["seller", "buyer"] = "seller"
    shipping_method: str = "Standard"
    status: Literal["active", "sold", "reserved", "removed"] = "active"
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
    delivery_confirmed_at: Optional[datetime] = None  # set when buyer or auto-release marks delivery
    funds_released: bool = False  # true once seller/dropship-source frozen earnings are released to available balance
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class OrderCreate(BaseModel):
    listing_id: str
    quantity: int = 1
    shipping_address: dict = {}
    affiliate_code: Optional[str] = None
    share_ref: Optional[str] = None  # e.g. "push" when the buyer arrived from a Storefront Push share link
    payment_method: Optional[str] = None  # card | wallet | crypto | bank
    payment_currency: Optional[str] = None  # crypto symbol (ETH/SOL/…) or manual method id


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
    category_ids: Optional[List[str]] = None

class StoreUpdate(BaseModel):
    name: Optional[str] = None
    tagline: Optional[str] = None
    bio: Optional[str] = None
    logo: Optional[str] = None
    banner: Optional[str] = None
    category_ids: Optional[List[str]] = None

class AffiliateLink(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    code: str = Field(default_factory=lambda: uuid.uuid4().hex[:10])
    affiliate_user_id: str
    listing_id: Optional[str] = None
    store_id: Optional[str] = None
    clicks: int = 0
    conversions: int = 0
    earnings: float = 0.0
    status: Literal["active", "disabled"] = "active"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class AffiliateLinkCreate(BaseModel):
    listing_id: Optional[str] = None
    store_id: Optional[str] = None

class WalletTransaction(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    type: Literal["sale", "sale_frozen", "sale_released", "affiliate", "referral", "dropship", "dropship_frozen", "dropship_released", "withdrawal", "adjustment", "bonus", "refund", "deposit", "purchase", "wholesale_debit"]
    amount: float  # positive = credit, negative = debit
    balance_after: float
    description: str = ""
    related_id: Optional[str] = None
    status: Literal["completed", "pending"] = "completed"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    # Bucket the row belongs to — either affects wallet_balance (available)
    # or wallet_frozen_balance (frozen). Populated by ledger.apply_entry so
    # frontends can render the two buckets separately and reconcile is
    # unambiguous.
    bucket: Optional[Literal["available", "frozen"]] = None
    # Populated on Reinvest-advance credit rows so the UI can render an
    # expandable trail of which orders each advance funded.
    funded_orders: List[str] = Field(default_factory=list)

class WithdrawalRequest(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    user_name: str
    amount: float
    method: str = "bank_transfer"  # mocked
    account_info: str = ""
    status: Literal["pending", "approved", "rejected", "paid"] = "pending"
    notes: Optional[str] = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    processed_at: Optional[datetime] = None

class WithdrawalRequestCreate(BaseModel):
    amount: float
    method: str = "bank_transfer"
    account_info: str = ""

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
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DepositRequest(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    user_name: str
    amount: float
    method: Literal["crypto", "manual"] = "crypto"
    currency: Optional[str] = None  # BTC/ETH/USDC/USDT for crypto, or manual method id
    reference: str = ""  # tx hash for crypto, or bank reference / payment id for manual
    note: str = ""
    screenshot_url: Optional[str] = None
    status: Literal["pending", "approved", "rejected"] = "pending"
    admin_note: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    processed_at: Optional[datetime] = None

class DepositRequestCreate(BaseModel):
    amount: float
    method: Literal["crypto", "manual"] = "crypto"
    currency: Optional[str] = None
    reference: str = ""
    note: Optional[str] = ""
    screenshot_url: Optional[str] = None


class Message(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    listing_id: str
    sender_id: str
    sender_name: str
    receiver_id: str
    content: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class MessageCreate(BaseModel):
    listing_id: str
    receiver_id: str
    content: str


# =========================
# Phase 12: Disputes & Returns
# =========================
DISPUTE_REASONS = ("not_as_described", "damaged", "not_received", "counterfeit", "other")
DISPUTE_STATUSES = ("open", "reviewing", "refunded", "rejected")

class Dispute(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    order_id: str
    buyer_id: str
    buyer_name: str
    seller_id: str
    listing_id: str
    listing_title: str
    listing_image: Optional[str] = None
    amount: float
    reason: Literal["not_as_described", "damaged", "not_received", "counterfeit", "other"]
    description: str
    photos: List[str] = []  # list of /api/files/<id> URLs
    status: Literal["open", "reviewing", "refunded", "rejected"] = "open"
    admin_notes: str = ""
    resolution: Optional[str] = None  # short resolution summary shown to buyer
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: Optional[datetime] = None

class DisputeCreate(BaseModel):
    order_id: str
    reason: Literal["not_as_described", "damaged", "not_received", "counterfeit", "other"]
    description: str
    photos: List[str] = []

class DisputeResolveIn(BaseModel):
    action: Literal["refund", "reject", "review"]
    admin_notes: Optional[str] = ""
    resolution: Optional[str] = ""


class DisputeMessage(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    dispute_id: str
    sender_id: str
    sender_name: str
    sender_role: Literal["buyer", "seller", "admin"]
    body: str
    photos: List[str] = []
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DisputeMessageCreate(BaseModel):
    body: str = ""
    photos: List[str] = []


# =========================
# Phase 2: Reviews & Notifications
# =========================
class Review(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    order_id: str
    reviewer_id: str
    reviewer_name: str
    seller_id: str
    listing_id: str
    listing_title: str
    rating: int  # 1..5
    comment: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ReviewCreate(BaseModel):
    order_id: str
    rating: int
    comment: Optional[str] = ""

NOTIFICATION_TYPES = ("order", "sale", "message", "review", "payout", "system", "dispute", "shipping", "wallet", "verification")


class Notification(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    type: str = "system"
    title: str
    body: str = ""
    link: Optional[str] = None
    read: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


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
    payout_method: Literal["stripe_connect", "bank_transfer"] = "stripe_connect"
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
    payout_method: Literal["stripe_connect", "bank_transfer"] = "stripe_connect"
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
    return pwd_context.verify(plain, hashed)

def create_token(user_id: str, role: str) -> str:
    payload = {
        "sub": user_id,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRE_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALG])
        user_id = payload.get("sub")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="Account disabled")
    return user

async def get_current_user_optional(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Optional[dict]:
    if not credentials:
        return None
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALG])
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
        await db.settings.insert_one(defaults)
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
        html = _shell(title, f"<p>Hi {user.get('username','')},</p><p>{body}</p>", cta_url, "Open Mercari")
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
    limit = max(1, min(int(limit), 96))
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
    if q:
        query["$or"] = [
            {"title": {"$regex": q, "$options": "i"}},
            {"description": {"$regex": q, "$options": "i"}},
            {"brand": {"$regex": q, "$options": "i"}},
        ]
    if category_id:
        query["category_id"] = category_id
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

    # Payment method validation — wallet payments must have sufficient balance.
    method = (payload.payment_method or "").strip().lower() or None
    if method and method not in ("card", "wallet", "crypto", "bank"):
        raise HTTPException(400, "Invalid payment method")
    total_due = round(amount + shipping_fee, 2)
    if method == "wallet":
        try:
            await ledger.purchase_debit(
                db,
                user_id=user["id"],
                amount=total_due,
                order_id="pending",  # updated after order id is minted
                description=f"Wallet payment × {quantity}: {listing['title']}",
            )
        except ledger.InsufficientFunds:
            available = float(user.get("wallet_balance", 0.0) or 0.0)
            raise HTTPException(400, f"Insufficient wallet balance. Available ${available:.2f}, need ${total_due:.2f}")

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
    dropship_source_seller_id = None
    dropship_source_earnings = 0.0
    reseller_wholesale_cost = 0.0
    reseller_paid_wholesale = False
    if listing.get("imported_from_id") and listing.get("base_price"):
        original = await db.listings.find_one({"id": listing["imported_from_id"]}, {"_id": 0, "seller_id": 1})
        if original and original.get("seller_id"):
            dropship_source_seller_id = original["seller_id"]
            retail_base = float(listing["base_price"]) * quantity
            reseller_user = await db.users.find_one({"id": listing["seller_id"]}, {"_id": 0})
            if reseller_user:
                badge = compute_seller_badge(reseller_user)
                discounts = settings.get("resell_wholesale_discounts") or {"new": 0.0, "bronze": 5.0, "silver": 10.0, "gold": 15.0}
                discount_pct = float(discounts.get(badge, 0.0))
                wholesale_cost = round(retail_base * (1 - discount_pct / 100.0), 2)
                # Route the wholesale charge through the unified ledger.
                try:
                    await ledger.apply_entry(
                        db,
                        user_id=listing["seller_id"],
                        delta=-wholesale_cost,
                        tx_type="wholesale_debit",
                        description=f"Wholesale cost × {quantity}: {listing['title']}",
                        related_id="pending",
                        require_available=True,
                    )
                    reseller_paid_wholesale = True
                    reseller_wholesale_cost = wholesale_cost
                    dropship_source_earnings = wholesale_cost
                except ledger.InsufficientFunds:
                    dropship_source_earnings = retail_base
            else:
                dropship_source_earnings = retail_base

    # Reseller earnings — if wholesale was pre-paid from wallet, they keep amount - fees.
    if reseller_paid_wholesale:
        seller_earnings = round(amount - platform_fee - affiliate_earnings, 2)
    else:
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
        status=("pending" if method in ("crypto", "bank") else "paid"),
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
    )
    await db.orders.insert_one(order.model_dump())
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
    await notify(listing["seller_id"], "sale", f"You sold {listing['title']}!",
                 f"Earnings ${seller_earnings:.2f} are held until the buyer confirms delivery (est. {eta_days} days).",
                 f"/listing/{listing['id']}")
    await notify(user["id"], "order", f"Order placed: {listing['title']}",
                 f"You paid ${amount + shipping_fee:.2f} · arrives in ~{eta_days} days",
                 f"/profile?tab=orders")
    if affiliate_user_id:
        await notify(affiliate_user_id, "payout", f"Affiliate commission earned", f"+${affiliate_earnings:.2f} from your link", "/affiliate")
    if dropship_source_seller_id:
        await notify(dropship_source_seller_id, "sale",
                     f"Dropship sale: {listing['title']}",
                     f"Earnings ${dropship_source_earnings:.2f} are held until delivery is confirmed.", None)
    if reseller_paid_wholesale and reseller_wholesale_cost > 0:
        await notify(listing["seller_id"], "wallet",
                     f"Wholesale ${reseller_wholesale_cost:.2f} debited",
                     f"Auto-paid to the source seller for: {listing['title']}",
                     "/wallet")

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


# =========================
# Messages
# =========================
@api_router.get("/messages/{listing_id}/{other_user_id}", response_model=List[Message])
async def get_messages(listing_id: str, other_user_id: str, user: dict = Depends(get_current_user)):
    docs = await db.messages.find({
        "listing_id": listing_id,
        "$or": [
            {"sender_id": user["id"], "receiver_id": other_user_id},
            {"sender_id": other_user_id, "receiver_id": user["id"]},
        ],
    }, {"_id": 0}).sort("created_at", 1).to_list(500)
    return [Message(**d) for d in docs]

@api_router.post("/messages", response_model=Message)
async def send_message(payload: MessageCreate, user: dict = Depends(get_current_user)):
    msg = Message(
        listing_id=payload.listing_id,
        sender_id=user["id"],
        sender_name=user["username"],
        receiver_id=payload.receiver_id,
        content=payload.content,
    )
    await db.messages.insert_one(msg.model_dump())
    return msg


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

@api_router.get("/admin/users", response_model=List[UserPublic])
async def admin_list_users(_admin: dict = Depends(require_admin)):
    docs = await db.users.find({}, {"_id": 0, "password_hash": 0}).sort("created_at", -1).to_list(1000)
    return [UserPublic(**d) for d in docs]

@api_router.put("/admin/users/{user_id}")
async def admin_update_user(user_id: str, updates: dict, _admin: dict = Depends(require_admin)):
    allowed = {"role", "is_active", "bio", "avatar", "resell_markup_override"}
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


@api_router.delete("/admin/users/{user_id}")
async def admin_delete_user(user_id: str, _admin: dict = Depends(require_admin)):
    await db.users.delete_one({"id": user_id})
    await db.listings.delete_many({"seller_id": user_id})
    return {"ok": True}

@api_router.get("/admin/orders", response_model=List[Order])
async def admin_orders(_admin: dict = Depends(require_admin)):
    docs = await db.orders.find({}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return [Order(**d) for d in docs]

@api_router.get("/admin/listings", response_model=List[Listing])
async def admin_listings(_admin: dict = Depends(require_admin), status_filter: Optional[str] = None):
    q = {}
    if status_filter:
        q["status"] = status_filter
    docs = await db.listings.find(q, {"_id": 0}).sort("created_at", -1).to_list(2000)
    return [Listing(**d) for d in docs]


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
    docs = await db.listings.find({"store_id": store["id"], "status": "active"}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return [Listing(**d) for d in docs]

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
@api_router.post("/affiliate/links", response_model=AffiliateLink)
async def create_affiliate_link(payload: AffiliateLinkCreate, user: dict = Depends(get_current_user)):
    if not payload.listing_id and not payload.store_id:
        raise HTTPException(400, "Provide listing_id or store_id")
    existing = await db.affiliate_links.find_one({
        "affiliate_user_id": user["id"],
        "listing_id": payload.listing_id,
        "store_id": payload.store_id,
    }, {"_id": 0})
    if existing:
        return AffiliateLink(**existing)
    link = AffiliateLink(affiliate_user_id=user["id"], listing_id=payload.listing_id, store_id=payload.store_id)
    await db.affiliate_links.insert_one(link.model_dump())
    return link

@api_router.get("/affiliate/links", response_model=List[AffiliateLink])
async def my_affiliate_links(user: dict = Depends(get_current_user)):
    docs = await db.affiliate_links.find({"affiliate_user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return [AffiliateLink(**d) for d in docs]

@api_router.get("/affiliate/track/{code}")
async def track_affiliate_click(code: str):
    link = await db.affiliate_links.find_one({"code": code, "status": "active"}, {"_id": 0})
    if not link:
        raise HTTPException(404, "Invalid affiliate code")
    await db.affiliate_links.update_one({"code": code}, {"$inc": {"clicks": 1}})
    return {"ok": True, "listing_id": link.get("listing_id"), "store_id": link.get("store_id"), "code": code}

@api_router.get("/affiliate/stats")
async def affiliate_stats(user: dict = Depends(get_current_user)):
    links = await db.affiliate_links.find({"affiliate_user_id": user["id"]}, {"_id": 0}).to_list(500)
    total_clicks = sum(l.get("clicks", 0) for l in links)
    total_conversions = sum(l.get("conversions", 0) for l in links)
    total_earnings = sum(l.get("earnings", 0.0) for l in links)
    return {
        "links": len(links),
        "clicks": total_clicks,
        "conversions": total_conversions,
        "earnings": round(total_earnings, 2),
        "conversion_rate": round((total_conversions / total_clicks * 100) if total_clicks else 0, 2),
    }


# =========================
# REFERRALS
# =========================
@api_router.get("/referrals/me")
async def my_referrals(user: dict = Depends(get_current_user)):
    l1 = await db.users.find({"referred_by": user["id"]}, {"_id": 0, "id": 1, "username": 1, "created_at": 1}).to_list(1000)
    l1_ids = [u["id"] for u in l1]
    l2 = await db.users.find({"referred_by": {"$in": l1_ids}}, {"_id": 0, "id": 1, "username": 1, "referred_by": 1, "created_at": 1}).to_list(1000) if l1_ids else []
    l2_ids = [u["id"] for u in l2]
    l3 = await db.users.find({"referred_by": {"$in": l2_ids}}, {"_id": 0, "id": 1, "username": 1, "referred_by": 1, "created_at": 1}).to_list(1000) if l2_ids else []
    # Earnings from referral wallet transactions
    txs = await db.wallet_txs.find({"user_id": user["id"], "type": "referral"}, {"_id": 0}).to_list(1000)
    total_earnings = sum(t.get("amount", 0) for t in txs)
    return {
        "referral_code": user.get("referral_code"),
        "levels": {
            "l1": l1,
            "l2": l2,
            "l3": l3,
        },
        "counts": {"l1": len(l1), "l2": len(l2), "l3": len(l3)},
        "total_referral_earnings": round(total_earnings, 2),
    }


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
async def request_withdrawal(payload: WithdrawalRequestCreate, user: dict = Depends(get_current_user)):
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
        "bulk_discount_tiers",
    }
    filtered = {k: v for k, v in updates.items() if k in allowed}
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

@api_router.get("/admin/withdrawals", response_model=List[WithdrawalRequest])
async def admin_withdrawals(_admin: dict = Depends(require_admin), status_filter: Optional[str] = None):
    q = {}
    if status_filter:
        q["status"] = status_filter
    docs = await db.withdrawals.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
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
async def admin_stores(_admin: dict = Depends(require_admin)):
    docs = await db.stores.find({}, {"_id": 0}).sort([("featured_rank", 1), ("created_at", -1)]).to_list(1000)
    return [Store(**d) for d in docs]

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
@api_router.post("/reviews", response_model=Review)
async def create_review(payload: ReviewCreate, user: dict = Depends(get_current_user)):
    if payload.rating < 1 or payload.rating > 5:
        raise HTTPException(400, "Rating must be 1-5")
    order = await db.orders.find_one({"id": payload.order_id}, {"_id": 0})
    if not order:
        raise HTTPException(404, "Order not found")
    if order["buyer_id"] != user["id"]:
        raise HTTPException(403, "Only the buyer can review")
    existing = await db.reviews.find_one({"order_id": payload.order_id, "reviewer_id": user["id"]})
    if existing:
        raise HTTPException(400, "Already reviewed this order")
    review = Review(
        order_id=payload.order_id,
        reviewer_id=user["id"],
        reviewer_name=user["username"],
        seller_id=order["seller_id"],
        listing_id=order["listing_id"],
        listing_title=order["listing_title"],
        rating=payload.rating,
        comment=payload.comment or "",
    )
    await db.reviews.insert_one(review.model_dump())
    # Update seller rating
    agg = await db.reviews.aggregate([
        {"$match": {"seller_id": order["seller_id"]}},
        {"$group": {"_id": None, "avg": {"$avg": "$rating"}, "count": {"$sum": 1}}},
    ]).to_list(1)
    if agg:
        await db.users.update_one({"id": order["seller_id"]}, {"$set": {"rating": round(agg[0]["avg"], 2)}})
    await notify(order["seller_id"], "review", f"New {payload.rating}-star review", (payload.comment or "")[:120], f"/listing/{order['listing_id']}")
    return review

@api_router.get("/reviews/seller/{seller_id}", response_model=List[Review])
async def get_seller_reviews(seller_id: str):
    docs = await db.reviews.find({"seller_id": seller_id}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return [Review(**d) for d in docs]

@api_router.get("/reviews/listing/{listing_id}", response_model=List[Review])
async def get_listing_reviews(listing_id: str):
    docs = await db.reviews.find({"listing_id": listing_id}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return [Review(**d) for d in docs]

@api_router.get("/reviews/order/{order_id}", response_model=Optional[Review])
async def get_order_review(order_id: str, user: dict = Depends(get_current_user)):
    doc = await db.reviews.find_one({"order_id": order_id, "reviewer_id": user["id"]}, {"_id": 0})
    return Review(**doc) if doc else None


# =========================
# PHASE 2: MESSAGES / CHAT
# =========================
@api_router.get("/chat/threads")
async def get_threads(user: dict = Depends(get_current_user)):
    """Return distinct conversation threads for the user."""
    pipeline = [
        {"$match": {"$or": [{"sender_id": user["id"]}, {"receiver_id": user["id"]}]}},
        {"$sort": {"created_at": -1}},
        {"$group": {
            "_id": {
                "listing_id": "$listing_id",
                "other": {"$cond": [{"$eq": ["$sender_id", user["id"]]}, "$receiver_id", "$sender_id"]},
            },
            "last_content": {"$first": "$content"},
            "last_at": {"$first": "$created_at"},
            "sender_id": {"$first": "$sender_id"},
        }},
        {"$sort": {"last_at": -1}},
    ]
    threads = await db.messages.aggregate(pipeline).to_list(200)
    # Enrich with user + listing info
    result = []
    for t in threads:
        other_id = t["_id"]["other"]
        listing_id = t["_id"]["listing_id"]
        other = await db.users.find_one({"id": other_id}, {"_id": 0, "id": 1, "username": 1})
        listing = await db.listings.find_one({"id": listing_id}, {"_id": 0, "id": 1, "title": 1, "images": 1, "price": 1})
        result.append({
            "listing_id": listing_id,
            "other_user_id": other_id,
            "other_username": other.get("username") if other else "Unknown",
            "listing_title": listing.get("title") if listing else "Listing removed",
            "listing_image": (listing.get("images") or [None])[0] if listing else None,
            "last_message": t.get("last_content", "")[:120],
            "last_at": t.get("last_at"),
            "unread": False,
        })
    return result

@api_router.get("/chat/{listing_id}/{other_user_id}", response_model=List[Message])
async def chat_messages(listing_id: str, other_user_id: str, user: dict = Depends(get_current_user)):
    docs = await db.messages.find({
        "listing_id": listing_id,
        "$or": [
            {"sender_id": user["id"], "receiver_id": other_user_id},
            {"sender_id": other_user_id, "receiver_id": user["id"]},
        ],
    }, {"_id": 0}).sort("created_at", 1).to_list(500)
    return [Message(**d) for d in docs]

@api_router.post("/chat", response_model=Message)
async def send_chat_message(payload: MessageCreate, user: dict = Depends(get_current_user)):
    if not payload.content.strip():
        raise HTTPException(400, "Empty message")
    msg = Message(
        listing_id=payload.listing_id,
        sender_id=user["id"],
        sender_name=user["username"],
        receiver_id=payload.receiver_id,
        content=payload.content.strip(),
    )
    await db.messages.insert_one(msg.model_dump())
    await notify(payload.receiver_id, "message", f"New message from {user['username']}", payload.content[:120], f"/chat/{payload.listing_id}/{user['id']}")
    return msg


# =========================
# PHASE 2: NOTIFICATIONS
# =========================
@api_router.get("/notifications", response_model=List[Notification])
async def list_notifications(user: dict = Depends(get_current_user), limit: int = 50):
    docs = await db.notifications.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(limit)
    return [Notification(**d) for d in docs]

@api_router.post("/notifications/read-all")
async def mark_all_read(user: dict = Depends(get_current_user)):
    await db.notifications.update_many({"user_id": user["id"], "read": False}, {"$set": {"read": True}})
    return {"ok": True}

@api_router.post("/notifications/{nid}/read")
async def mark_read(nid: str, user: dict = Depends(get_current_user)):
    await db.notifications.update_one({"id": nid, "user_id": user["id"]}, {"$set": {"read": True}})
    return {"ok": True}


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
    target = int(payload.get("target_count", 5000))
    replace = bool(payload.get("replace_existing", True))
    if target < 100 or target > 20000:
        raise HTTPException(400, "target_count must be between 100 and 20000")

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
    return f"{random.randint(0, 999999):06d}"

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
    logger.info(f"[MOCK] Sent {kind} verification to {target} for user {user_id}: token={token_value}")
    return doc


@api_router.post("/verify/email/send")
async def verify_email_send(payload: EmailSendRequest, user: dict = Depends(get_current_user)):
    """Mocked email verification send. Returns the token in response for dev use."""
    if user.get("email_verified"):
        return {"ok": True, "already_verified": True}
    target_email = payload.email or user["email"]
    doc = await _create_verification_token(user["id"], "email", target_email, ttl_minutes=60)
    verify_link = f"/verify?token={doc['token']}"
    return {
        "ok": True,
        "message": f"[MOCK] Magic link sent to {target_email}",
        "dev_mock": True,
        "token": doc["token"],
        "verify_link": verify_link,
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
async def seller_apply(payload: SellerApplicationCreate, user: dict = Depends(get_current_user)):
    # Require email + phone verification before applying
    fresh_user = await db.users.find_one({"id": user["id"]}, {"_id": 0})
    if not fresh_user.get("email_verified"):
        raise HTTPException(400, "Please verify your email before applying")
    if not fresh_user.get("phone_verified"):
        raise HTTPException(400, "Please verify your phone before applying")
    if fresh_user.get("seller_status") == "approved":
        raise HTTPException(400, "You are already an approved seller")
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
        phone=payload.phone or fresh_user.get("phone", ""),
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


# ---------- Mock Stripe Connect ----------
@api_router.post("/stripe/connect/onboard")
async def stripe_connect_onboard(user: dict = Depends(get_current_user)):
    """Mocked Stripe Connect onboarding. Generates a fake acct_ ID and marks pending -> active."""
    fresh = await db.users.find_one({"id": user["id"]}, {"_id": 0})
    if fresh.get("stripe_status") == "active":
        return {
            "ok": True,
            "already_active": True,
            "stripe_account_id": fresh.get("stripe_account_id"),
        }
    acct_id = fresh.get("stripe_account_id") or f"acct_mock_{uuid.uuid4().hex[:16]}"
    # In mock mode, we simulate immediate active status once onboarding is "completed"
    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {"stripe_account_id": acct_id, "stripe_status": "active"}},
    )
    logger.info(f"[MOCK] Stripe Connect account created for user {user['id']}: {acct_id}")
    return {
        "ok": True,
        "dev_mock": True,
        "stripe_account_id": acct_id,
        "stripe_status": "active",
        "onboarding_url": f"/mock-stripe/onboard?acct={acct_id}",
    }

@api_router.get("/stripe/connect/status")
async def stripe_connect_status(user: dict = Depends(get_current_user)):
    fresh = await db.users.find_one({"id": user["id"]}, {"_id": 0})
    return {
        "stripe_account_id": fresh.get("stripe_account_id"),
        "stripe_status": fresh.get("stripe_status", "none"),
    }


# ---------- Admin: Seller Application Queue ----------
@api_router.get("/admin/seller-applications", response_model=List[SellerApplication])
async def admin_seller_apps(_admin: dict = Depends(require_admin), status_filter: Optional[str] = None):
    q: dict = {}
    if status_filter:
        q["status"] = status_filter
    docs = await db.seller_applications.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    return [SellerApplication(**d) for d in docs]

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
                     "You can now sell on Mercari. Connect your payout method.", "/verify")
    else:
        await notify(doc["user_id"], "system", "Seller application rejected",
                     notes or "See admin notes.", "/profile")
    return {"ok": True, "status": new_status}


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
                         "You can now sell on Mercari. Connect your payout method.", "/verify")
        else:
            await notify(doc["user_id"], "system", "Seller application rejected",
                         notes or "See admin notes.", "/profile")
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
        "You are an expert Mercari listing assistant. Analyze the product photo and return "
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
        "You translate free-form shopping 'vibes' into concrete Mercari filters. "
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
                body = "Hi " + user.get("username", "there") + ",\n\n" + "\n".join(lines) + "\n\nShop now on Mercari Global!"
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
            subject = "Weekly Mercari digest: " + " · ".join(subject_bits)

            body_lines = ["Hi there,", ""]
            if drops:
                body_lines.append("🔥 Price drops this week:")
                for d in drops:
                    body_lines.append(f"  - {d['title']}: ${d['previous_price']:.2f} → ${d['price']:.2f}")
                body_lines.append("")
            if top_listings:
                body_lines.append("✨ Trending on Mercari:")
                for t in top_listings:
                    body_lines.append(f"  - {t['title']} — ${t['price']:.2f}")
                body_lines.append("")
            body_lines.append("Shop everything at Mercari Global.")
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


class ShippingLabelResponse(BaseModel):
    tracking_number: str
    carrier: str
    label_url: str
    estimated_delivery: str
    cost: float
    dev_mock: bool = True


@api_router.post("/orders/{order_id}/shipping-label", response_model=ShippingLabelResponse)
async def create_shipping_label(order_id: str, user: dict = Depends(get_current_user)):
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(404, "Order not found")
    if order["seller_id"] != user["id"] and user.get("role") != "admin":
        raise HTTPException(403, "Only the seller can purchase a label")
    if order.get("tracking_number"):
        return ShippingLabelResponse(
            tracking_number=order["tracking_number"],
            carrier=order.get("carrier", "USPS"),
            label_url=f"/api/orders/{order_id}/label.svg",
            estimated_delivery=order.get("estimated_delivery", "2-5 business days"),
            cost=float(order.get("shipping_fee", 0)),
            dev_mock=order.get("shipping_provider", "mock") == "mock",
        )
    provider = get_shipping_provider()
    label = provider.create_label(order)
    initial_event = event_details("label_created", label.carrier)
    await db.orders.update_one(
        {"id": order_id},
        {"$set": {
            "tracking_number": label.tracking_number,
            "carrier": label.carrier,
            "label_url": f"/api/orders/{order_id}/label.svg",
            "shipping_status": "label_created",
            "shipping_provider": label.provider,
            "estimated_delivery": label.estimated_delivery,
            "shipping_events": [initial_event],
            "label_created_at": _now_utc(),
        }},
    )
    await notify(order["buyer_id"], "order", "Shipping label created",
                 f"Tracking: {label.tracking_number} via {label.carrier}", f"/order/{order_id}")
    logger.info(f"[shipping:{label.provider}] Label created for order {order_id}: {label.carrier} {label.tracking_number}")
    return ShippingLabelResponse(
        tracking_number=label.tracking_number,
        carrier=label.carrier,
        label_url=f"/api/orders/{order_id}/label.svg",
        estimated_delivery=label.estimated_delivery,
        cost=label.cost,
        dev_mock=label.dev_mock,
    )


@api_router.get("/orders/{order_id}/label.svg")
async def render_shipping_label(order_id: str, request: Request):
    """Render a printable shipping label as SVG with a QR-style block and barcode."""
    # Auth via header OR ?auth= query param (so <img>/<iframe> can render it)
    token = None
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1]
    token = token or request.query_params.get("auth")
    if not token:
        raise HTTPException(401, "Missing auth token")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        uid = payload.get("sub") or payload.get("user_id")
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid token")
    user = await db.users.find_one({"id": uid}, {"_id": 0})
    if not user:
        raise HTTPException(401, "Invalid user")

    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order or not order.get("tracking_number"):
        raise HTTPException(404, "Label not generated for this order")
    if order["seller_id"] != user["id"] and user.get("role") != "admin":
        raise HTTPException(403, "Only the seller/admin can view this label")

    return Response(content=_render_label_svg(order, order_id), media_type="image/svg+xml")


def _render_label_svg(order: dict, order_id: str) -> str:
    """Render a printable 4x6-style shipping label as inline SVG."""
    tracking = order.get("tracking_number", "")
    carrier = order.get("carrier", "USPS")
    est = order.get("estimated_delivery", "")
    addr = order.get("address", {}) or {}
    seller_name = order.get("seller_name", "")
    buyer_name = addr.get("full_name") or order.get("buyer_name", "")
    street = addr.get("street", "")
    csz = " ".join(str(v) for v in [addr.get("city", ""), addr.get("state", ""), addr.get("zip", "")] if v).strip()
    country = addr.get("country", "")

    # Deterministic QR-like grid from tracking number
    import hashlib
    h = hashlib.sha256(tracking.encode()).digest()
    grid_bits = []
    for byte in h:
        for i in range(8):
            grid_bits.append((byte >> i) & 1)
    # 16x16 grid
    qr_cells = []
    cell_size = 10
    qr_origin_x, qr_origin_y = 470, 210
    for row in range(16):
        for col in range(16):
            if grid_bits[row * 16 + col]:
                x = qr_origin_x + col * cell_size
                y = qr_origin_y + row * cell_size
                qr_cells.append(f'<rect x="{x}" y="{y}" width="{cell_size}" height="{cell_size}" fill="black" />')

    # Corner alignment markers (mimic QR finder patterns)
    def finder(cx, cy):
        return (
            f'<rect x="{cx}" y="{cy}" width="70" height="70" fill="black" />'
            f'<rect x="{cx+10}" y="{cy+10}" width="50" height="50" fill="white" />'
            f'<rect x="{cx+20}" y="{cy+20}" width="30" height="30" fill="black" />'
        )
    corners = finder(qr_origin_x - 10, qr_origin_y - 10) + finder(qr_origin_x + 100, qr_origin_y - 10) + finder(qr_origin_x - 10, qr_origin_y + 100)

    # Barcode-like stripes derived from the same hash
    bars = []
    x = 40
    for byte in h[:24]:
        widths = [2, 3, 4, 5]
        w = widths[byte % 4]
        gap = 1 + (byte >> 4) % 3
        bars.append(f'<rect x="{x}" y="480" width="{w}" height="90" fill="black" />')
        x += w + gap

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 700" width="640" height="700" style="font-family: 'Helvetica Neue', Arial, sans-serif;">
  <rect width="640" height="700" fill="white" stroke="#111" stroke-width="3"/>
  <!-- Header band -->
  <rect x="0" y="0" width="640" height="60" fill="#FF211F"/>
  <text x="20" y="40" fill="white" font-size="26" font-weight="800">MERCARI GLOBAL — SHIPPING LABEL</text>
  <text x="580" y="40" fill="white" font-size="14" text-anchor="end">MOCK / DEV</text>

  <!-- Carrier & tracking -->
  <text x="20" y="105" fill="#666" font-size="11" letter-spacing="2">CARRIER</text>
  <text x="20" y="135" fill="#111" font-size="28" font-weight="700">{carrier}</text>
  <text x="20" y="175" fill="#666" font-size="11" letter-spacing="2">TRACKING</text>
  <text x="20" y="200" fill="#111" font-size="18" font-family="ui-monospace, Menlo, monospace" font-weight="600">{tracking}</text>

  <!-- Ship-to block -->
  <line x1="20" y1="220" x2="440" y2="220" stroke="#111" stroke-width="1"/>
  <text x="20" y="245" fill="#666" font-size="11" letter-spacing="2">SHIP TO</text>
  <text x="20" y="275" fill="#111" font-size="22" font-weight="700">{buyer_name}</text>
  <text x="20" y="305" fill="#111" font-size="16">{street}</text>
  <text x="20" y="330" fill="#111" font-size="16">{csz}</text>
  <text x="20" y="355" fill="#111" font-size="16">{country}</text>

  <!-- From block -->
  <text x="20" y="395" fill="#666" font-size="11" letter-spacing="2">FROM</text>
  <text x="20" y="415" fill="#111" font-size="14">{seller_name}</text>
  <text x="20" y="435" fill="#666" font-size="12">Est. delivery: {est}</text>

  <!-- Barcode -->
  {''.join(bars)}
  <text x="40" y="595" fill="#111" font-size="12" font-family="ui-monospace, Menlo, monospace">{tracking}</text>

  <!-- QR block -->
  {corners}
  {''.join(qr_cells)}
  <text x="470" y="395" fill="#666" font-size="11" letter-spacing="2">SCAN AT DROP-OFF</text>

  <!-- Footer -->
  <rect x="0" y="670" width="640" height="30" fill="#FFF0E6"/>
  <text x="20" y="690" fill="#FF211F" font-size="12" font-weight="600">MERCARI GLOBAL — Powered by pluggable shipping adapter</text>
  <text x="620" y="690" fill="#FF211F" font-size="11" text-anchor="end" font-family="ui-monospace, Menlo, monospace">#{order_id[:8]}</text>
</svg>'''
    return svg


@api_router.get("/orders/{order_id}/tracking")
async def get_tracking(order_id: str, user: dict = Depends(get_current_user)):
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(404, "Order not found")
    if user["id"] not in (order.get("buyer_id"), order.get("seller_id")) and user.get("role") != "admin":
        raise HTTPException(403, "Not allowed")
    if not order.get("tracking_number"):
        return {"has_label": False}
    events = order.get("shipping_events") or []
    if not events:
        # Backfill for legacy orders — synthesize a single label_created event.
        created = order.get("label_created_at") or order.get("created_at") or _now_utc()
        if isinstance(created, str):
            try: created = datetime.fromisoformat(created.replace("Z", "+00:00"))
            except Exception: created = _now_utc()
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        events = [{
            "status": "label_created",
            "at": created.isoformat(),
            "location": "Origin facility",
            "description": "Shipping label created",
        }]
        await db.orders.update_one({"id": order_id}, {"$set": {"shipping_events": events, "label_created_at": created}})
    return {
        "has_label": True,
        "tracking_number": order["tracking_number"],
        "carrier": order.get("carrier"),
        "label_url": order.get("label_url"),
        "estimated_delivery": order.get("estimated_delivery"),
        "current_status": order.get("shipping_status", "label_created"),
        "provider": order.get("shipping_provider", "mock"),
        "events": events,
        "dev_mock": order.get("shipping_provider", "mock") == "mock",
    }


class AdvanceShippingRequest(BaseModel):
    to_status: Optional[str] = None  # optional target; if omitted advance by one stage


@api_router.post("/orders/{order_id}/shipping-advance")
async def advance_shipping(order_id: str, payload: AdvanceShippingRequest, user: dict = Depends(get_current_user)):
    """Seller/admin manually advances shipping status by one stage (or to a target status)."""
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(404, "Order not found")
    if order["seller_id"] != user["id"] and user.get("role") != "admin":
        raise HTTPException(403, "Only the seller or admin can advance shipping")
    if not order.get("tracking_number"):
        raise HTTPException(400, "No shipping label on this order")
    stages = ["label_created", "picked_up", "in_transit", "out_for_delivery", "delivered"]
    current = order.get("shipping_status", "label_created")
    if current == "delivered":
        raise HTTPException(400, "Order already delivered")
    if payload.to_status:
        if payload.to_status not in stages:
            raise HTTPException(400, "Invalid target status")
        if stages.index(payload.to_status) <= stages.index(current):
            raise HTTPException(400, "Target status must be beyond current")
        next_status = payload.to_status
    else:
        next_status = stages[stages.index(current) + 1]
    ev = event_details(next_status, order.get("carrier", "Carrier"))
    await db.orders.update_one(
        {"id": order_id},
        {"$set": {"shipping_status": next_status}, "$push": {"shipping_events": ev}},
    )
    await notify(order["buyer_id"], "order",
                 f"Shipping update: {next_status.replace('_',' ').title()}",
                 ev["description"], f"/order/{order_id}")
    return {"ok": True, "current_status": next_status, "event": ev}


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
                await db.orders.update_one(
                    {"id": o["id"]},
                    {"$set": {"shipping_status": nxt}, "$push": {"shipping_events": ev}},
                )
                await notify(o["buyer_id"], "order",
                             f"Shipping update: {nxt.replace('_',' ').title()}",
                             ev["description"], f"/order/{o['id']}")
                logger.info(f"[shipping:auto] order {o['id']} advanced to {nxt}")
        except Exception as e:
            logger.warning(f"shipping_progress_loop error: {e}")
        await asyncio.sleep(30)


# =========================
# Phase 12: Disputes & Returns
# =========================
async def _get_order_or_404(order_id: str) -> dict:
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(404, "Order not found")
    return order


@api_router.post("/disputes", response_model=Dispute)
async def create_dispute(payload: DisputeCreate, user: dict = Depends(get_current_user)):
    """Buyer opens a dispute on one of their orders. Delivered/paid/shipped orders eligible."""
    order = await _get_order_or_404(payload.order_id)
    if order["buyer_id"] != user["id"]:
        raise HTTPException(403, "Only the buyer can open a dispute for this order")
    if order.get("status") not in ("paid", "shipped", "delivered"):
        raise HTTPException(400, "This order is not eligible for a dispute")
    existing = await db.disputes.find_one(
        {"order_id": payload.order_id, "status": {"$in": ["open", "reviewing"]}}, {"_id": 0}
    )
    if existing:
        raise HTTPException(400, "An open dispute already exists for this order")
    if not (payload.description or "").strip():
        raise HTTPException(400, "Please describe what went wrong")

    dispute = Dispute(
        order_id=order["id"],
        buyer_id=user["id"],
        buyer_name=user["username"],
        seller_id=order["seller_id"],
        listing_id=order["listing_id"],
        listing_title=order["listing_title"],
        listing_image=order.get("listing_image"),
        amount=float(order.get("amount", 0)),
        reason=payload.reason,
        description=payload.description.strip(),
        photos=[p for p in (payload.photos or []) if isinstance(p, str)][:8],
    )
    doc = dispute.model_dump()
    await db.disputes.insert_one(doc)

    # Auto-refund rule: if the dispute amount is under the admin-configured threshold,
    # resolve immediately with a wallet refund so support only reviews high-value cases.
    settings = await get_settings()
    threshold = float(settings.get("dispute_auto_refund_threshold") or 0.0)
    excluded = set(settings.get("dispute_auto_refund_excluded_reasons") or [])
    if (
        threshold > 0
        and dispute.amount > 0
        and dispute.amount <= threshold
        and dispute.reason not in excluded
    ):
        now = datetime.now(timezone.utc)
        resolution_msg = f"Auto-refunded — orders at or under ${threshold:.2f} are refunded instantly."
        # Credit buyer via ledger's refund path, debit seller via adjustment.
        await ledger.refund_credit(
            db,
            user_id=dispute.buyer_id,
            amount=dispute.amount,
            order_id=order["id"],
            description=f"Auto-refund for dispute #{dispute.id[:8]}",
        )
        seller_debit = float(order["seller_earnings"]) if order.get("seller_earnings") is not None else dispute.amount
        await ledger.apply_entry(
            db,
            user_id=dispute.seller_id,
            delta=-seller_debit,
            tx_type="refund",
            description=f"Auto-refund chargeback for dispute #{dispute.id[:8]}",
            related_id=order["id"],
        )
        await db.orders.update_one({"id": order["id"]}, {"$set": {"status": "cancelled"}})
        await db.disputes.update_one(
            {"id": dispute.id},
            {"$set": {
                "status": "refunded",
                "resolution": resolution_msg,
                "admin_notes": f"Auto-refunded (threshold=${threshold:.2f})",
                "resolved_at": now,
            }},
        )
        await notify(
            dispute.buyer_id, "dispute", "Refund issued automatically",
            resolution_msg, "/wallet",
        )
        await notify(
            dispute.seller_id, "dispute", "Dispute auto-refunded",
            f"An order under ${threshold:.2f} was automatically refunded to the buyer.",
            "/profile?tab=disputes",
        )
        fresh = await db.disputes.find_one({"id": dispute.id}, {"_id": 0})
        return Dispute(**fresh)

    await notify(
        order["seller_id"], "dispute",
        f"Buyer opened a dispute on '{order['listing_title']}'",
        payload.description[:120],
        f"/profile?tab=disputes",
    )
    return dispute


@api_router.get("/disputes/mine", response_model=List[Dispute])
async def my_disputes(user: dict = Depends(get_current_user)):
    """Return disputes where the current user is either buyer or seller."""
    docs = await db.disputes.find(
        {"$or": [{"buyer_id": user["id"]}, {"seller_id": user["id"]}]}, {"_id": 0}
    ).sort("created_at", -1).to_list(200)
    return [Dispute(**d) for d in docs]


@api_router.get("/disputes/{dispute_id}", response_model=Dispute)
async def get_dispute(dispute_id: str, user: dict = Depends(get_current_user)):
    d = await db.disputes.find_one({"id": dispute_id}, {"_id": 0})
    if not d:
        raise HTTPException(404, "Dispute not found")
    if user.get("role") != "admin" and user["id"] not in (d["buyer_id"], d["seller_id"]):
        raise HTTPException(403, "Not allowed")
    return Dispute(**d)


@api_router.get("/admin/disputes", response_model=List[Dispute])
async def admin_list_disputes(
    status_filter: Optional[str] = Query(None, alias="status"),
    _admin: dict = Depends(require_admin),
):
    q: dict = {}
    if status_filter and status_filter in DISPUTE_STATUSES:
        q["status"] = status_filter
    docs = await db.disputes.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    return [Dispute(**d) for d in docs]


@api_router.post("/admin/disputes/{dispute_id}/resolve", response_model=Dispute)
async def admin_resolve_dispute(
    dispute_id: str, payload: DisputeResolveIn, _admin: dict = Depends(require_admin),
):
    d = await db.disputes.find_one({"id": dispute_id}, {"_id": 0})
    if not d:
        raise HTTPException(404, "Dispute not found")
    if d["status"] in ("refunded", "rejected"):
        raise HTTPException(400, f"Dispute already {d['status']}")

    now = datetime.now(timezone.utc)
    updates: dict = {
        "admin_notes": (payload.admin_notes or d.get("admin_notes", "")).strip(),
    }
    if payload.resolution is not None:
        updates["resolution"] = payload.resolution.strip()

    if payload.action == "review":
        updates["status"] = "reviewing"
    elif payload.action == "reject":
        updates["status"] = "rejected"
        updates["resolved_at"] = now
        await notify(
            d["buyer_id"], "dispute",
            "Your dispute was reviewed",
            (updates.get("resolution") or "Our team sided with the seller after review.")[:200],
            f"/profile?tab=disputes",
        )
    elif payload.action == "refund":
        updates["status"] = "refunded"
        updates["resolved_at"] = now
        # Refund: credit the buyer wallet, debit the seller earnings for that order
        amount = float(d.get("amount", 0))
        if amount > 0:
            await ledger.refund_credit(
                db,
                user_id=d["buyer_id"],
                amount=amount,
                order_id=d["order_id"],
                description=f"Refund for dispute #{dispute_id[:8]}",
            )
            # Debit seller earnings for that order (uses seller_earnings if we have it)
            order = await db.orders.find_one({"id": d["order_id"]}, {"_id": 0})
            seller_debit = float(order["seller_earnings"]) if (order and order.get("seller_earnings") is not None) else amount
            await ledger.apply_entry(
                db,
                user_id=d["seller_id"],
                delta=-seller_debit,
                tx_type="refund",
                description=f"Chargeback for dispute #{dispute_id[:8]}",
                related_id=dispute_id,
            )
        # Mark order as cancelled
        await db.orders.update_one({"id": d["order_id"]}, {"$set": {"status": "cancelled"}})
        await notify(
            d["buyer_id"], "dispute",
            "Refund issued",
            (updates.get("resolution") or f"We refunded ${amount:.2f} to your wallet.")[:200],
            f"/wallet",
        )
        await notify(
            d["seller_id"], "dispute",
            "Dispute resolved with refund",
            "The buyer was refunded and the sale was cancelled.",
            f"/profile?tab=disputes",
        )

    await db.disputes.update_one({"id": dispute_id}, {"$set": updates})
    fresh = await db.disputes.find_one({"id": dispute_id}, {"_id": 0})
    return Dispute(**fresh)


# ---- Dispute chat thread ----------------------------------------------------
async def _dispute_role_for(user: dict, d: dict) -> str:
    if user.get("role") == "admin":
        return "admin"
    if user["id"] == d.get("buyer_id"):
        return "buyer"
    if user["id"] == d.get("seller_id"):
        return "seller"
    raise HTTPException(403, "Not allowed")


@api_router.get("/disputes/{dispute_id}/messages", response_model=List[DisputeMessage])
async def list_dispute_messages(dispute_id: str, user: dict = Depends(get_current_user)):
    d = await db.disputes.find_one({"id": dispute_id}, {"_id": 0})
    if not d:
        raise HTTPException(404, "Dispute not found")
    await _dispute_role_for(user, d)
    docs = await db.dispute_messages.find(
        {"dispute_id": dispute_id}, {"_id": 0}
    ).sort("created_at", 1).to_list(500)
    return [DisputeMessage(**m) for m in docs]


@api_router.post("/disputes/{dispute_id}/messages", response_model=DisputeMessage)
async def post_dispute_message(
    dispute_id: str, payload: DisputeMessageCreate, user: dict = Depends(get_current_user),
):
    d = await db.disputes.find_one({"id": dispute_id}, {"_id": 0})
    if not d:
        raise HTTPException(404, "Dispute not found")
    role = await _dispute_role_for(user, d)
    if d.get("status") in ("refunded", "rejected"):
        raise HTTPException(400, "This dispute is closed")
    body = (payload.body or "").strip()
    photos = [p for p in (payload.photos or []) if isinstance(p, str)][:8]
    if not body and not photos:
        raise HTTPException(400, "Message body or at least one photo is required")

    msg = DisputeMessage(
        dispute_id=dispute_id,
        sender_id=user["id"],
        sender_name=user["username"],
        sender_role=role,
        body=body,
        photos=photos,
    )
    await db.dispute_messages.insert_one(msg.model_dump())

    # Notify the other party (or both parties if admin)
    recipients = []
    if role == "buyer":
        recipients = [d["seller_id"]]
    elif role == "seller":
        recipients = [d["buyer_id"]]
    elif role == "admin":
        recipients = [d["buyer_id"], d["seller_id"]]
    for rid in recipients:
        try:
            await notify(
                rid, "dispute",
                f"New message on dispute for '{d['listing_title']}'",
                body[:120] if body else "New photo attached",
                "/disputes",
            )
        except Exception as e:
            logger.warning(f"dispute message notify failed: {e}")
    return msg


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
        "email": "admin@mercari.local",
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
        "admin_credentials": {"email": "admin@mercari.local", "password": "admin123"},
    }


@api_router.get("/")
async def root():
    return {"message": "Mercari Clone API", "status": "ok"}


app.include_router(api_router)
app.include_router(search_router, prefix="/api")
app.include_router(discovery_router, prefix="/api")
app.include_router(users_router, prefix="/api")
app.include_router(newsletter_router, prefix="/api")
app.include_router(google_auth_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(stores_search_router, prefix="/api")
app.include_router(shopping_router, prefix="/api")
app.include_router(listings_router, prefix="/api")
app.include_router(personalized_router, prefix="/api")
app.include_router(checkout_router, prefix="/api")
app.include_router(coupons_router, prefix="/api")
app.include_router(stripe_payments_router, prefix="/api")
app.include_router(scraper_router, prefix="/api")
app.include_router(store_boosts_router, prefix="/api")

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

                # Auto-recover a stuck sync_running lock (e.g. after a crash)
                if state.get("sync_running"):
                    started = state.get("started_at")
                    if started and started.tzinfo is None:
                        started = started.replace(tzinfo=timezone.utc)
                    if not started or (datetime.now(timezone.utc) - started).total_seconds() > 60 * 60 * 6:
                        logger.warning("Clearing stuck Apify sync_running lock (>6h old)")
                        await db.sync_state.update_one(
                            {"id": "apify"},
                            {"$set": {"sync_running": False, "message": "Auto-cleared stuck lock"}},
                        )
                        state["sync_running"] = False

                last = state.get("last_sync_at")
                now = datetime.now(timezone.utc)
                if last:
                    # Handle both naive and aware
                    if last.tzinfo is None:
                        last = last.replace(tzinfo=timezone.utc)
                    elapsed = (now - last).total_seconds()
                    wait = max(0, INTERVAL_SECONDS - elapsed)
                else:
                    # Never synced — run right away
                    wait = 0

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
                    await import_from_apify(db, target_count=5000, replace_existing=True)
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


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
