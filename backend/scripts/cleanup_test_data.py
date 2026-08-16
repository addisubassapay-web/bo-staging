"""One-shot cleanup: remove test users, their listings, and derivative data.
Keeps only:
- Admin
- The 5 curated demo sellers (sophia_style, urban_finds, vintage_maven, tech_haven, cozy_home)
- Any human-registered user (real email domain, not TEST_/@example.com/@test.local)

Usage: python3 /app/backend/scripts/cleanup_test_data.py
"""
import asyncio
import os
import sys
from pathlib import Path

# Allow running as a script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")

DEMO_SELLERS = ["sophia_style", "urban_finds", "vintage_maven", "tech_haven", "cozy_home"]


def is_real_user(u: dict) -> bool:
    if u.get("role") == "admin":
        return True
    if u.get("username") in DEMO_SELLERS:
        return True
    email = (u.get("email") or "").lower()
    if "test_" in email:
        return False
    if email.endswith("@example.com"):
        return False
    if email.endswith("@test.local"):
        return False
    if email.endswith("@demo.local"):
        return True
    # Public email domains → real
    if any(email.endswith(d) for d in [
        "@gmail.com", "@yahoo.com", "@hotmail.com", "@outlook.com",
        "@icloud.com", "@aol.com", "@proton.me", "@protonmail.com",
        "@live.com", "@msn.com", "@ymail.com",
    ]):
        return True
    return False


async def main() -> None:
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    users = await db.users.find({}, {"_id": 0}).to_list(5000)
    real_users = [u for u in users if is_real_user(u)]
    test_users = [u for u in users if not is_real_user(u)]

    real_ids = {u["id"] for u in real_users}
    test_ids = {u["id"] for u in test_users}

    print(f"Users total: {len(users)}  →  keep {len(real_users)}, delete {len(test_users)}")

    listings_delete = await db.listings.count_documents({"seller_id": {"$nin": list(real_ids)}})
    listings_keep = await db.listings.count_documents({"seller_id": {"$in": list(real_ids)}})
    print(f"Listings: keep {listings_keep}, delete {listings_delete}")

    # 1) Strip test-titled listings first (runs even if no test users remain)
    bad_title_re = {
        "$regex": r"^(TEST_|test_|Follow Notif Test|FOLLOW NOTIF TEST|TEST_pay|TEST_SOPHIA)",
    }
    bad_title_ids = [
        d["id"] for d in await db.listings.find(
            {"title": bad_title_re}, {"id": 1}
        ).to_list(1000)
    ]
    if bad_title_ids:
        await db.listings.delete_many({"id": {"$in": bad_title_ids}})
        await db.favorites.delete_many({"listing_id": {"$in": bad_title_ids}})
        await db.cart_items.delete_many({"listing_id": {"$in": bad_title_ids}})
        await db.views.delete_many({"listing_id": {"$in": bad_title_ids}})
        await db.orders.delete_many({"listing_id": {"$in": bad_title_ids}})
        print(f"Deleted {len(bad_title_ids)} test-titled listings owned by kept sellers")

    if not test_ids:
        remaining_users = await db.users.count_documents({})
        remaining_listings = await db.listings.count_documents({})
        print(f"\nNo test users to remove. FINAL — users: {remaining_users}, listings: {remaining_listings}")
        return

    # 2) Wipe test-owned listings
    list_ids_to_delete = [
        d["id"] for d in await db.listings.find(
            {"seller_id": {"$in": list(test_ids)}}, {"id": 1}
        ).to_list(10_000)
    ]

    if list_ids_to_delete:
        await db.listings.delete_many({"id": {"$in": list_ids_to_delete}})
        # Also nuke derivative refs
        await db.favorites.delete_many({"listing_id": {"$in": list_ids_to_delete}})
        await db.cart_items.delete_many({"listing_id": {"$in": list_ids_to_delete}})
        await db.views.delete_many({"listing_id": {"$in": list_ids_to_delete}})
        await db.orders.delete_many({"listing_id": {"$in": list_ids_to_delete}})
        print(f"Deleted {len(list_ids_to_delete)} test listings + derivative refs")

    # Remove the now-orphaned duplicate bad-title block at the end (moved to top)

    # Delete test users and their user-scoped data
    for coll in [
        "users",
        "stores",
        "wallets",
        "wallet_txns",
        "referrals",
        "notifications",
        "reviews",
        "disputes",
        "affiliate_clicks",
        "seller_applications",
        "cart_items",
        "favorites",
        "views",
        "orders",  # orders keyed by user_id
        "user_settings",
    ]:
        try:
            r = await db[coll].delete_many({
                "$or": [
                    {"user_id": {"$in": list(test_ids)}},
                    {"owner_id": {"$in": list(test_ids)}},
                    {"seller_id": {"$in": list(test_ids)}},
                    {"buyer_id": {"$in": list(test_ids)}},
                    {"id": {"$in": list(test_ids)}} if coll == "users" else {"user_id": None},
                ]
            })
            if r.deleted_count:
                print(f"  {coll}: -{r.deleted_count}")
        except Exception as e:
            print(f"  {coll}: skipped ({e})")

    # Final counts
    remaining_users = await db.users.count_documents({})
    remaining_listings = await db.listings.count_documents({})
    print(f"\nFINAL — users: {remaining_users}, listings: {remaining_listings}")


if __name__ == "__main__":
    asyncio.run(main())
