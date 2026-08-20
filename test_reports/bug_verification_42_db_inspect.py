#!/usr/bin/env python3
"""Read-only DB corroboration for Apify-only listing verification."""
import asyncio
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

ROOT = Path('/app/backend')
load_dotenv(ROOT / '.env')
OUT = Path('/app/test_reports/bug_verification_42_db_inspect_results.json')

async def main():
    client = AsyncIOMotorClient(os.environ['MONGO_URL'])
    db = client[os.environ.get('DB_NAME', 'test_database')]
    legacy_regex = {'$regex': r'toscrape\.com|scrape\.me|quotes\.toscrape', '$options': 'i'}
    soumission_count = await db.listings.count_documents({'title': {'$regex': 'Soumission', '$options': 'i'}})
    legacy_source_active_count = await db.listings.count_documents({'status': 'active', 'source_url': legacy_regex})
    legacy_source_any_count = await db.listings.count_documents({'source_url': legacy_regex})
    active_count = await db.listings.count_documents({'status': 'active'})
    state = await db.sync_state.find_one({'id': 'apify'}, {'_id': 0}) or {}
    sample = await db.listings.find({'source_url': legacy_regex}, {'_id': 0, 'id': 1, 'title': 1, 'status': 1, 'source_url': 1}).limit(5).to_list(5)
    out = {
        'checked_at': datetime.now(timezone.utc).isoformat(),
        'db_name': os.environ.get('DB_NAME'),
        'soumission_title_raw_count': soumission_count,
        'legacy_source_active_raw_count': legacy_source_active_count,
        'legacy_source_any_raw_count': legacy_source_any_count,
        'active_listing_raw_count': active_count,
        'sync_state': state,
        'legacy_sample': sample,
    }
    OUT.write_text(json.dumps(out, indent=2, default=str))
    print(json.dumps(out, indent=2, default=str)[:4000])
    client.close()

asyncio.run(main())
