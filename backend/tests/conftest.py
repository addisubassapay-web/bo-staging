"""Shared pytest fixtures — makes sure our webhook regression tests never
pollute the permanent product catalog on Atlas.

Every test that creates products under a `B00TEST*`, `B00SYNC*`, `B00ASY*` or
`B00FORCE*` SKU will have those rows scrubbed at session start and end.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv
from pymongo import MongoClient

# Ensure the backend .env is loaded before any Mongo access — tests are
# invoked as `python -m pytest` and pytest doesn't inherit the app's env.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def _purge() -> None:
    client = MongoClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    db.products.delete_many({"sku": {"$regex": "^B00(TEST|SYNC|ASY|FORCE|BIG)"}})
    # Purge ONLY the failing-dataset test job. The other ingest jobs are
    # produced live during tests and each xdist worker owns its own set;
    # a blanket delete here races with concurrent runs on other workers.
    db.apify_ingest_state.delete_many({"dataset_id": "nonexistent-dataset-for-test"})
    client.close()


@pytest.fixture(autouse=True, scope="session")
def _wipe_webhook_test_products():
    _purge()
    yield
    _purge()
