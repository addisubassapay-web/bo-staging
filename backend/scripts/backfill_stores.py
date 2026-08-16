"""Auto-provision a storefront for every real user who doesn't already have one.
Idempotent. Uses `ensure_store_for_user()` semantics inline (script is standalone).
"""
import asyncio
import os
import re
import uuid
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")


async def provision_store(db, user: dict) -> str:
    if user.get("store_id"):
        existing = await db.stores.find_one({"id": user["store_id"]}, {"_id": 0, "id": 1})
        if existing:
            return "already_had_store"

    base_slug = re.sub(r"[^a-z0-9-]+", "-", (user.get("username") or "seller").lower()).strip("-") or "seller"
    slug = base_slug
    suffix = 1
    while await db.stores.find_one({"slug": slug}, {"_id": 0, "id": 1}):
        suffix += 1
        slug = f"{base_slug}-{suffix}"

    display = (user.get("first_name") or user.get("username") or "Seller").strip()
    store = {
        "id": str(uuid.uuid4()),
        "owner_id": user["id"],
        "name": f"{display}'s Store",
        "slug": slug,
        "tagline": "Curated with care",
        "bio": "",
        "logo": user.get("avatar"),
        "banner": None,
        "verified_tier": "none",
        "followers_count": 0,
        "total_sales": 0,
        "is_active": True,
        "featured_rank": 9999,
        "created_at": datetime.now(timezone.utc),
    }
    await db.stores.insert_one(store)
    await db.users.update_one({"id": user["id"]}, {"$set": {"store_id": store["id"]}})
    return "created"


async def main() -> None:
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    users = await db.users.find({"role": "user"}, {"_id": 0}).to_list(500)
    created = existing = 0
    for u in users:
        result = await provision_store(db, u)
        if result == "created":
            created += 1
            print(f"  + created store for {u.get('username')}")
        else:
            existing += 1

    total_stores = await db.stores.count_documents({})
    print(f"\nUsers: {len(users)}  |  new stores: {created}  |  already had: {existing}")
    print(f"Total stores now: {total_stores}")


if __name__ == "__main__":
    asyncio.run(main())
