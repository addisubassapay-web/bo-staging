#!/usr/bin/env python3
"""Cleanup only temporary users/cart data created by iteration 27 verification."""
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient


ROOT = Path("/app")
SETUP = ROOT / "test_reports" / "iteration_27_runtime_api.json"
OUT = ROOT / "test_reports" / "iteration_27_runtime_cleanup.json"


def main():
    setup = json.loads(SETUP.read_text())
    ids = [setup["buyer"]["user"]["id"], setup["empty_buyer"]["user"]["id"]]
    emails = [setup["buyer"]["payload"]["email"], setup["empty_buyer"]["payload"]["email"]]
    load_dotenv(ROOT / "backend" / ".env")
    client = MongoClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    deleted = {}
    for coll in [
        "cart_items", "favorites", "views", "orders", "wallets", "wallet_txns",
        "referrals", "notifications", "reviews", "disputes", "affiliate_clicks",
        "seller_applications", "user_settings",
    ]:
        deleted[coll] = db[coll].delete_many({"user_id": {"$in": ids}}).deleted_count
    deleted["users"] = db.users.delete_many({"$or": [{"id": {"$in": ids}}, {"email": {"$in": emails}}]}).deleted_count
    report = {"cleaned_user_ids": ids, "cleaned_emails": emails, "deleted": deleted}
    OUT.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()