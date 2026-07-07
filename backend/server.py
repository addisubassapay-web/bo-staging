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
from datetime import datetime, timezone, timedelta
import jwt
from passlib.context import CryptContext

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
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class OrderCreate(BaseModel):
    listing_id: str
    shipping_address: dict = {}

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
# Auth Routes
# =========================
@api_router.post("/auth/register", response_model=AuthResponse)
async def register(payload: UserCreate):
    existing = await db.users.find_one({"$or": [{"email": payload.email}, {"username": payload.username}]})
    if existing:
        raise HTTPException(status_code=400, detail="Email or username already exists")
    user = User(email=payload.email, username=payload.username)
    doc = user.model_dump()
    doc["password_hash"] = hash_password(payload.password)
    await db.users.insert_one(doc)
    token = create_token(user.id, user.role)
    return AuthResponse(token=token, user=UserPublic(**user.model_dump()))

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
    order = Order(
        buyer_id=user["id"],
        buyer_name=user["username"],
        seller_id=listing["seller_id"],
        seller_name=listing["seller_name"],
        listing_id=listing["id"],
        listing_title=listing["title"],
        listing_image=listing["images"][0] if listing.get("images") else None,
        amount=listing["price"],
        shipping_fee=0.0 if listing.get("shipping_paid_by") == "seller" else 5.99,
        shipping_address=payload.shipping_address,
        status="paid",
    )
    await db.orders.insert_one(order.model_dump())
    await db.listings.update_one({"id": listing["id"]}, {"$set": {"status": "sold"}})
    await db.users.update_one({"id": listing["seller_id"]}, {"$inc": {"sales_count": 1}})
    await db.cart_items.delete_many({"listing_id": listing["id"]})
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
    revenue_agg = await db.orders.aggregate([
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
    ]).to_list(1)
    total_revenue = revenue_agg[0]["total"] if revenue_agg else 0
    return {
        "users": users_count,
        "active_listings": active_listings,
        "sold_listings": sold_listings,
        "orders": orders_count,
        "categories": categories_count,
        "revenue": total_revenue,
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
    await db.listings.create_index("seller_id")
    await db.listings.create_index("category_id")
    await db.listings.create_index("status")
    await db.favorites.create_index([("user_id", 1), ("listing_id", 1)], unique=True)
    await db.cart_items.create_index([("user_id", 1), ("listing_id", 1)], unique=True)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
