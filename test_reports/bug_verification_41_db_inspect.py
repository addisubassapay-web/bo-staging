#!/usr/bin/env python3
"""Inspect listing source markers for the focused Zyte/Apify verification."""
import json
import os
from collections import Counter

from dotenv import dotenv_values
from pymongo import MongoClient

env = dotenv_values("/app/backend/.env")
client = MongoClient(env.get("MONGO_URL") or os.environ.get("MONGO_URL"), serverSelectionTimeoutMS=10000)
db = client[env.get("DB_NAME") or os.environ.get("DB_NAME")]

fields = {
    "active_total": db.listings.count_documents({"status": "active"}),
    "active_apify_asin_exists": db.listings.count_documents({"status": "active", "apify_asin": {"$exists": True, "$ne": None}}),
    "active_apify_url_exists": db.listings.count_documents({"status": "active", "apify_url": {"$exists": True, "$nin": [None, ""]}}),
    "active_source_url_exists": db.listings.count_documents({"status": "active", "source_url": {"$exists": True, "$nin": [None, ""]}}),
    "active_imported_from_id_exists": db.listings.count_documents({"status": "active", "imported_from_id": {"$exists": True, "$nin": [None, ""]}}),
}

samples = []
for doc in db.listings.find({"status": "active"}, {"_id": 0, "id": 1, "title": 1, "seller_name": 1, "source_url": 1, "apify_asin": 1, "apify_url": 1, "imported_from_id": 1, "created_at": 1}).sort("created_at", -1).limit(12):
    samples.append(doc)

legacy_samples = list(db.listings.find(
    {"status": "active", "source_url": {"$exists": True, "$nin": [None, ""]}},
    {"_id": 0, "id": 1, "title": 1, "seller_name": 1, "source_url": 1, "apify_asin": 1, "apify_url": 1, "created_at": 1},
).limit(10))

seller_counts = Counter()
for row in db.listings.aggregate([
    {"$match": {"status": "active"}},
    {"$group": {"_id": "$seller_name", "n": {"$sum": 1}}},
    {"$sort": {"n": -1}},
    {"$limit": 10},
]):
    seller_counts[row["_id"]] = row["n"]

out = {"counts": fields, "seller_counts": dict(seller_counts), "newest_samples": samples, "legacy_source_url_samples": legacy_samples}
print(json.dumps(out, default=str, indent=2))
open("/app/test_reports/bug_verification_41_db_inspect_results.json", "w", encoding="utf-8").write(json.dumps(out, default=str, indent=2))