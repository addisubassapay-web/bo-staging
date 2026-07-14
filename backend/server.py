from fastapi import FastAPI, APIRouter, HTTPException, Depends, Query, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional, Literal
import uuid
import asyncio
from datetime import datetime, timezone, timedelta
import jwt
from passlib.context import CryptContext

from apify_sync import import_from_apify, simulate_live_update, get_sync_status


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

JWT_SECRET = os.environ.get('JWT_SECRET', 'change-me')
JWT_ALG = "HS256"
JWT_EXPIRE_HOURS = 24 * 7

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)

app = FastAPI(title="Mercari Clone API")
api_router = APIRouter(prefix="/api")


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
    store_id: Optional[str] = None
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
    store_id: Optional[str] = None
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
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class OrderCreate(BaseModel):
    listing_id: str
    shipping_address: dict = {}
    affiliate_code: Optional[str] = None


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
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class StoreCreate(BaseModel):
    name: str
    slug: str
    tagline: Optional[str] = ""
    bio: Optional[str] = ""
    logo: Optional[str] = None
    banner: Optional[str] = None

class StoreUpdate(BaseModel):
    name: Optional[str] = None
    tagline: Optional[str] = None
    bio: Optional[str] = None
    logo: Optional[str] = None
    banner: Optional[str] = None

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
    type: Literal["sale", "affiliate", "referral", "dropship", "withdrawal", "adjustment", "bonus"]
    amount: float  # positive = credit, negative = debit
    balance_after: float
    description: str = ""
    related_id: Optional[str] = None
    status: Literal["completed", "pending"] = "completed"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

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
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


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

class Notification(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    type: Literal["order", "sale", "message", "review", "payout", "system"] = "system"
    title: str
    body: str = ""
    link: Optional[str] = None
    read: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


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
    if not doc:
        s = Settings()
        await db.settings.insert_one(s.model_dump())
        return s.model_dump()
    return doc

async def credit_wallet(user_id: str, amount: float, tx_type: str, description: str, related_id: Optional[str] = None):
    if amount == 0:
        return
    user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not user:
        return
    new_balance = round(user.get("wallet_balance", 0.0) + amount, 2)
    await db.users.update_one({"id": user_id}, {"$set": {"wallet_balance": new_balance}})
    tx = WalletTransaction(
        user_id=user_id, type=tx_type, amount=amount,
        balance_after=new_balance, description=description, related_id=related_id
    )
    await db.wallet_txs.insert_one(tx.model_dump())

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

async def notify(user_id: str, ntype: str, title: str, body: str = "", link: Optional[str] = None):
    if not user_id:
        return
    n = Notification(user_id=user_id, type=ntype, title=title, body=body, link=link)
    await db.notifications.insert_one(n.model_dump())


# =========================
# Auth Routes
# =========================
@api_router.post("/auth/register", response_model=AuthResponse)
async def register(payload: UserCreate):
    existing = await db.users.find_one({"$or": [{"email": payload.email}, {"username": payload.username}]})
    if existing:
        raise HTTPException(status_code=400, detail="Email or username already exists")
    referred_by = None
    if payload.referral_code:
        ref = await db.users.find_one({"referral_code": payload.referral_code.upper()}, {"_id": 0, "id": 1})
        if ref:
            referred_by = ref["id"]
    user = User(email=payload.email, username=payload.username, referred_by=referred_by)
    doc = user.model_dump()
    doc["password_hash"] = hash_password(payload.password)
    await db.users.insert_one(doc)
    # Signup bonus
    settings = await get_settings()
    if settings.get("signup_bonus", 0) > 0:
        await credit_wallet(user.id, settings["signup_bonus"], "bonus", "Signup bonus")
    if referred_by:
        # notify referrer via wallet transaction with $0? Just a log entry
        pass
    token = create_token(user.id, user.role)
    fresh = await db.users.find_one({"id": user.id}, {"_id": 0, "password_hash": 0})
    return AuthResponse(token=token, user=UserPublic(**fresh))

@api_router.post("/auth/login", response_model=AuthResponse)
async def login(payload: UserLogin):
    user = await db.users.find_one({"email": payload.email})
    if not user or not verify_password(payload.password, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="Account disabled")
    token = create_token(user["id"], user["role"])
    return AuthResponse(token=token, user=UserPublic(**to_public_user(user)))

@api_router.get("/auth/me", response_model=UserPublic)
async def me(user: dict = Depends(get_current_user)):
    return UserPublic(**user)


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
    sort: str = "newest",
    featured: Optional[bool] = None,
    seller_id: Optional[str] = None,
    status_filter: Optional[str] = "active",
    limit: int = 60,
    skip: int = 0,
):
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

    sort_map = {
        "newest": [("created_at", -1)],
        "oldest": [("created_at", 1)],
        "price_asc": [("price", 1)],
        "price_desc": [("price", -1)],
        "popular": [("likes_count", -1), ("views_count", -1)],
    }
    cursor = db.listings.find(query, {"_id": 0}).sort(sort_map.get(sort, sort_map["newest"])).skip(skip).limit(limit)
    docs = await cursor.to_list(limit)
    return [Listing(**d) for d in docs]

@api_router.get("/listings/{listing_id}", response_model=Listing)
async def get_listing(listing_id: str):
    doc = await db.listings.find_one({"id": listing_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Listing not found")
    await db.listings.update_one({"id": listing_id}, {"$inc": {"views_count": 1}})
    doc["views_count"] = doc.get("views_count", 0) + 1
    return Listing(**doc)

@api_router.post("/listings", response_model=Listing)
async def create_listing(payload: ListingCreate, user: dict = Depends(get_current_user)):
    cat = await db.categories.find_one({"id": payload.category_id}, {"_id": 0})
    if not cat:
        raise HTTPException(400, "Invalid category")
    listing = Listing(
        seller_id=user["id"],
        seller_name=user["username"],
        category_name=cat["name"],
        store_id=user.get("store_id"),
        **payload.model_dump(),
    )
    await db.listings.insert_one(listing.model_dump())
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
    if updates:
        await db.listings.update_one({"id": listing_id}, {"$set": updates})
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
# Favorites
# =========================
@api_router.get("/favorites", response_model=List[Listing])
async def get_favorites(user: dict = Depends(get_current_user)):
    favs = await db.favorites.find({"user_id": user["id"]}, {"_id": 0}).to_list(500)
    ids = [f["listing_id"] for f in favs]
    docs = await db.listings.find({"id": {"$in": ids}}, {"_id": 0}).to_list(500)
    return [Listing(**d) for d in docs]

@api_router.post("/favorites/{listing_id}")
async def add_favorite(listing_id: str, user: dict = Depends(get_current_user)):
    existing = await db.favorites.find_one({"user_id": user["id"], "listing_id": listing_id})
    if existing:
        return {"ok": True, "already": True}
    fav = Favorite(user_id=user["id"], listing_id=listing_id)
    await db.favorites.insert_one(fav.model_dump())
    await db.listings.update_one({"id": listing_id}, {"$inc": {"likes_count": 1}})
    return {"ok": True}

@api_router.delete("/favorites/{listing_id}")
async def remove_favorite(listing_id: str, user: dict = Depends(get_current_user)):
    result = await db.favorites.delete_one({"user_id": user["id"], "listing_id": listing_id})
    if result.deleted_count > 0:
        await db.listings.update_one({"id": listing_id}, {"$inc": {"likes_count": -1}})
    return {"ok": True}


# =========================
# Cart
# =========================
@api_router.get("/cart", response_model=List[Listing])
async def get_cart(user: dict = Depends(get_current_user)):
    items = await db.cart_items.find({"user_id": user["id"]}, {"_id": 0}).to_list(500)
    ids = [i["listing_id"] for i in items]
    docs = await db.listings.find({"id": {"$in": ids}, "status": "active"}, {"_id": 0}).to_list(500)
    return [Listing(**d) for d in docs]

@api_router.post("/cart/{listing_id}")
async def add_to_cart(listing_id: str, user: dict = Depends(get_current_user)):
    existing = await db.cart_items.find_one({"user_id": user["id"], "listing_id": listing_id})
    if existing:
        return {"ok": True, "already": True}
    item = CartItem(user_id=user["id"], listing_id=listing_id)
    await db.cart_items.insert_one(item.model_dump())
    return {"ok": True}

@api_router.delete("/cart/{listing_id}")
async def remove_from_cart(listing_id: str, user: dict = Depends(get_current_user)):
    await db.cart_items.delete_one({"user_id": user["id"], "listing_id": listing_id})
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

    settings = await get_settings()
    amount = float(listing["price"])
    shipping_fee = 0.0 if listing.get("shipping_paid_by") == "seller" else 5.99

    # Platform fee
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

    # Dropship: original seller earnings
    dropship_source_seller_id = None
    dropship_source_earnings = 0.0
    if listing.get("imported_from_id") and listing.get("base_price"):
        original = await db.listings.find_one({"id": listing["imported_from_id"]}, {"_id": 0, "seller_id": 1})
        if original and original.get("seller_id"):
            dropship_source_seller_id = original["seller_id"]
            dropship_source_earnings = float(listing["base_price"])

    # Reseller (current seller) earnings = amount - platform_fee - affiliate - dropship_source
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
    )
    await db.orders.insert_one(order.model_dump())
    await db.listings.update_one({"id": listing["id"]}, {"$set": {"status": "sold"}})
    await db.users.update_one({"id": listing["seller_id"]}, {"$inc": {"sales_count": 1}})
    await db.cart_items.delete_many({"listing_id": listing["id"]})

    # Credit wallets
    await credit_wallet(listing["seller_id"], seller_earnings, "sale", f"Sale: {listing['title']}", order.id)
    if affiliate_user_id and affiliate_earnings > 0:
        await credit_wallet(affiliate_user_id, affiliate_earnings, "affiliate", f"Affiliate commission: {listing['title']}", order.id)
        await db.affiliate_links.update_one(
            {"id": affiliate_link["id"]},
            {"$inc": {"conversions": 1, "earnings": affiliate_earnings}},
        )
    if dropship_source_seller_id and dropship_source_earnings > 0:
        await credit_wallet(dropship_source_seller_id, dropship_source_earnings, "dropship", f"Dropship sale: {listing['title']}", order.id)
    for rp in referral_payouts:
        await credit_wallet(rp["user_id"], rp["amount"], "referral", f"Referral L{rp['level']} bonus", order.id)

    # Update store total_sales
    if listing.get("store_id"):
        await db.stores.update_one({"id": listing["store_id"]}, {"$inc": {"total_sales": 1}})

    # Notifications
    await notify(listing["seller_id"], "sale", f"You sold {listing['title']}!", f"Earnings: ${seller_earnings:.2f}", f"/listing/{listing['id']}")
    await notify(user["id"], "order", f"Order placed: {listing['title']}", f"You paid ${amount + shipping_fee:.2f}", f"/profile?tab=orders")
    if affiliate_user_id:
        await notify(affiliate_user_id, "payout", f"Affiliate commission earned", f"+${affiliate_earnings:.2f} from your link", "/affiliate")
    if dropship_source_seller_id:
        await notify(dropship_source_seller_id, "sale", f"Dropship sale: {listing['title']}", f"Earnings: ${dropship_source_earnings:.2f}", None)

    return order


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
        "revenue": total_revenue,
        "platform_fees": total_fees,
    }

@api_router.get("/admin/users", response_model=List[UserPublic])
async def admin_list_users(_admin: dict = Depends(require_admin)):
    docs = await db.users.find({}, {"_id": 0, "password_hash": 0}).sort("created_at", -1).to_list(1000)
    return [UserPublic(**d) for d in docs]

@api_router.put("/admin/users/{user_id}")
async def admin_update_user(user_id: str, updates: dict, _admin: dict = Depends(require_admin)):
    allowed = {"role", "is_active", "bio", "avatar"}
    filtered = {k: v for k, v in updates.items() if k in allowed}
    if not filtered:
        raise HTTPException(400, "No valid updates")
    await db.users.update_one({"id": user_id}, {"$set": filtered})
    doc = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    return UserPublic(**doc) if doc else {"ok": True}

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
    settings = await get_settings()
    is_active = settings.get("store_mode", "auto") == "auto"
    store = Store(owner_id=user["id"], **{**payload.model_dump(), "slug": payload.slug.lower()}, is_active=is_active)
    await db.stores.insert_one(store.model_dump())
    await db.users.update_one({"id": user["id"]}, {"$set": {"store_id": store.id}})
    return store

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
@api_router.get("/wallet")
async def get_wallet(user: dict = Depends(get_current_user)):
    txs = await db.wallet_txs.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(200)
    pending_wd = await db.withdrawals.find({"user_id": user["id"], "status": {"$in": ["pending", "approved"]}}, {"_id": 0}).to_list(100)
    return {
        "balance": user.get("wallet_balance", 0.0),
        "transactions": [WalletTransaction(**t).model_dump() for t in txs],
        "pending_withdrawals": [WithdrawalRequest(**w).model_dump() for w in pending_wd],
    }

@api_router.post("/wallet/withdraw", response_model=WithdrawalRequest)
async def request_withdrawal(payload: WithdrawalRequestCreate, user: dict = Depends(get_current_user)):
    settings = await get_settings()
    min_wd = settings.get("min_withdrawal", 10.0)
    if payload.amount < min_wd:
        raise HTTPException(400, f"Minimum withdrawal is ${min_wd}")
    if payload.amount > user.get("wallet_balance", 0.0):
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
        # debit wallet immediately
        await credit_wallet(user["id"], -payload.amount, "withdrawal", f"Withdrawal #{wd.id[:8]}", wd.id)

    return wd


# =========================
# DROPSHIP / IMPORT
# =========================
class ImportPayload(BaseModel):
    listing_id: str
    markup_pct: float  # percentage on top of base price

@api_router.post("/listings/import", response_model=Listing)
async def import_listing(payload: ImportPayload, user: dict = Depends(get_current_user)):
    settings = await get_settings()
    max_mk = settings.get("dropship_max_markup_pct", 100.0)
    if payload.markup_pct < 0 or payload.markup_pct > max_mk:
        raise HTTPException(400, f"Markup must be between 0 and {max_mk}%")
    original = await db.listings.find_one({"id": payload.listing_id, "status": "active"}, {"_id": 0})
    if not original:
        raise HTTPException(404, "Source listing not available")
    if original["seller_id"] == user["id"]:
        raise HTTPException(400, "Cannot import your own listing")
    if original.get("imported_from_id"):
        raise HTTPException(400, "Cannot import an already imported listing")
    base_price = float(original["price"])
    new_price = round(base_price * (1 + payload.markup_pct / 100.0), 2)
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
        store_id=user.get("store_id"),
        imported_from_id=original["id"],
        base_price=base_price,
    )
    await db.listings.insert_one(imported.model_dump())
    return imported


# =========================
# ADMIN: Settings, Withdrawals, Stores, Affiliate
# =========================
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
        "semi_threshold", "referral_levels_enabled",
    }
    filtered = {k: v for k, v in updates.items() if k in allowed}
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
    docs = await db.stores.find({}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return [Store(**d) for d in docs]

@api_router.put("/admin/stores/{store_id}")
async def admin_update_store(store_id: str, updates: dict, _admin: dict = Depends(require_admin)):
    allowed = {"verified_tier", "is_active", "name", "tagline"}
    filtered = {k: v for k, v in updates.items() if k in allowed}
    if not filtered:
        raise HTTPException(400, "No valid updates")
    await db.stores.update_one({"id": store_id}, {"$set": filtered})
    doc = await db.stores.find_one({"id": store_id}, {"_id": 0})
    return Store(**doc) if doc else {"ok": True}

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

@api_router.get("/admin/sync/status")
async def admin_sync_status(_admin: dict = Depends(require_admin)):
    return await get_sync_status(db)

@api_router.get("/sync/status")
async def public_sync_status():
    return await get_sync_status(db)


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

    # Sample listings
    cats_by_slug = {c["slug"]: c for c in cat_docs}
    samples = [
        ("Vintage Levi's 501 Jeans", "Classic straight-leg denim, gently worn, size 30x32.", 48.0, 90.0, "men", "good", "Levi's", "30x32", "Blue"),
        ("Nike Air Max 90 Sneakers", "Iconic silhouette, barely used, comes with original box.", 85.0, 130.0, "men", "like_new", "Nike", "US 10", "White"),
        ("Zara Wool Blend Coat", "Elegant camel coat, perfect for fall/winter, size S.", 62.0, 149.0, "women", "like_new", "Zara", "S", "Camel"),
        ("Apple AirPods Pro (2nd Gen)", "MagSafe case, active noise cancelation, near new.", 165.0, 249.0, "electronics", "like_new", "Apple", "", "White"),
        ("Sony WH-1000XM4 Headphones", "Industry-leading noise canceling. Excellent condition.", 210.0, 349.0, "electronics", "good", "Sony", "", "Black"),
        ("Ceramic Handmade Vase Set", "Set of 3 minimalist stoneware vases, unused gift.", 34.0, None, "home", "new", "", "", "Cream"),
        ("Coach Leather Handbag", "Authentic Coach shoulder bag, soft pebbled leather.", 120.0, 295.0, "women", "good", "Coach", "", "Tan"),
        ("Fujifilm Instax Mini 11", "Instant camera + strap, includes 20 films.", 55.0, 89.0, "electronics", "good", "Fujifilm", "", "Blue"),
        ("Yoga Mat + Block Bundle", "6mm eco-friendly TPE mat with cork block.", 28.0, 55.0, "sports", "like_new", "", "", "Purple"),
        ("Le Creuset Dutch Oven 5.5qt", "Cerise red enamel cast iron, minor use.", 220.0, 400.0, "home", "good", "Le Creuset", "", "Red"),
        ("Lego Star Wars Millennium Falcon", "Complete set with instructions, kids outgrew it.", 145.0, 199.0, "toys", "good", "Lego", "", "Grey"),
        ("Nintendo Switch OLED", "White Joy-Cons, includes dock and cables.", 260.0, 349.0, "electronics", "good", "Nintendo", "", "White"),
        ("Handmade Macramé Wall Hanging", "Original piece, cotton rope, boho vibe.", 42.0, None, "handmade", "new", "", "24 in", "Natural"),
        ("Vintage 90s Denim Jacket", "Oversized fit, faded wash, unisex.", 38.0, None, "vintage", "good", "", "L", "Blue"),
        ("H&M Kids Rainbow Sweater", "Soft cotton, size 6-7Y, worn twice.", 12.0, 29.0, "kids", "like_new", "H&M", "6-7Y", "Multi"),
        ("Fenty Beauty Foundation", "Shade 240, brand new sealed.", 28.0, 40.0, "beauty", "new", "Fenty Beauty", "", ""),
        ("Complete Harry Potter Book Set", "All 7 hardcovers, gently read.", 78.0, 180.0, "books", "good", "", "", ""),
        ("iPad Air 5th Gen 64GB", "Space Gray, WiFi, includes charger.", 380.0, 599.0, "electronics", "like_new", "Apple", "10.9\"", "Grey"),
        ("Adidas Ultraboost 22 Running Shoes", "Size US 9, run only 3 times.", 90.0, 190.0, "sports", "like_new", "Adidas", "US 9", "Black"),
        ("Bose SoundLink Mini II", "Portable Bluetooth speaker, warm sound.", 95.0, 199.0, "electronics", "good", "Bose", "", "Silver"),
        ("Anthropologie Ceramic Planters", "Set of 2, drainage holes, indoor use.", 32.0, 60.0, "home", "new", "", "", "White"),
        ("Kate Spade Wristlet Wallet", "Saffiano leather, pink, RFID protected.", 44.0, 98.0, "women", "like_new", "Kate Spade", "", "Pink"),
        ("Baby Bjorn Bouncer", "Ergonomic baby bouncer, mesh fabric.", 85.0, 219.0, "kids", "good", "Baby Bjorn", "", "Grey"),
        ("Vintage Vinyl Records Lot (10)", "70s rock classics, VG+ condition.", 60.0, None, "vintage", "good", "", "", ""),
    ]
    now = datetime.now(timezone.utc)
    listings_docs = []
    for i, s in enumerate(samples):
        title, desc, price, orig, cat_slug, cond, brand, size, color = s
        cat = cats_by_slug[cat_slug]
        seller = sellers[i % len(sellers)]
        listing = Listing(
            seller_id=seller["id"],
            seller_name=seller["username"],
            title=title,
            description=desc,
            price=price,
            original_price=orig,
            category_id=cat["id"],
            category_name=cat["name"],
            condition=cond,
            brand=brand,
            size=size,
            color=color,
            images=[
                f"https://picsum.photos/seed/{cat_slug}{i}a/800/800",
                f"https://picsum.photos/seed/{cat_slug}{i}b/800/800",
                f"https://picsum.photos/seed/{cat_slug}{i}c/800/800",
            ],
            shipping_paid_by="seller" if i % 2 == 0 else "buyer",
            shipping_method="Standard",
            likes_count=(i * 3) % 47,
            views_count=(i * 11) % 500 + 20,
            featured=i < 6,
            created_at=now - timedelta(hours=i * 5),
        )
        listings_docs.append(listing.model_dump())
    await db.listings.insert_many(listings_docs)

    return {
        "ok": True,
        "seeded": True,
        "categories": len(cat_docs),
        "users": len(sellers) + 1,
        "listings": len(listings_docs),
        "admin_credentials": {"email": "admin@mercari.local", "password": "admin123"},
    }


@api_router.get("/")
async def root():
    return {"message": "Mercari Clone API", "status": "ok"}


app.include_router(api_router)

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
    # Ensure settings doc exists
    await get_settings()

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
        # Auto-sync Amazon data every 7 days (weekly)
        WEEK_SECONDS = 60 * 60 * 24 * 7
        await asyncio.sleep(WEEK_SECONDS)  # wait 1 week before first auto-sync
        while True:
            try:
                state = await db.sync_state.find_one({"id": "apify"}, {"_id": 0}) or {}
                if not state.get("sync_running"):
                    logger.info("Starting scheduled Apify auto-sync (weekly)")
                    await import_from_apify(db, target_count=5000, replace_existing=True)
            except Exception as e:
                logger.error(f"apify auto-sync failed: {e}")
            await asyncio.sleep(WEEK_SECONDS)

    asyncio.create_task(live_sync_loop())
    asyncio.create_task(apify_auto_sync_loop())


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
