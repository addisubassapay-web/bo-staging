#!/usr/bin/env python3
"""Delete stale Apify webhooks that point at the old (rotated) credentials.

Any webhook whose `requestUrl` contains one of the tokens/secrets below is
considered stale and will be deleted. The new webhook (with the fresh
credentials in the path OR pointing at the canonical /api/webhooks/apify-import)
is kept.

Usage:
    # Dry-run — prints what would be deleted, changes nothing:
    python3 /app/backend/scripts/prune_stale_apify_webhooks.py

    # Actually delete:
    python3 /app/backend/scripts/prune_stale_apify_webhooks.py --apply

Reads APIFY_TOKEN from /app/backend/.env.
"""
from __future__ import annotations
import os
import re
import sys
import argparse

import requests
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")

APIFY_API = "https://api.apify.com/v2"

# Regex patterns that identify malformed webhook URLs. Any webhook whose URL
# path contains a raw Apify token, webhook secret, or the wrong `/apify-import`
# path (should be `/api/webhooks/apify-import`) is considered stale and needs
# to be rebuilt with the secret in the X-Webhook-Secret header instead.
MALFORMED_PATH_PATTERNS = [
    re.compile(r"/apify_api_[A-Za-z0-9]{20,}"),   # Apify token in path (any token — old or new)
    re.compile(r"/mg-webhook-[A-Fa-f0-9]{16,}"),  # webhook secret in path (any secret)
    re.compile(r"/apify-import(?:$|[/?])"),       # wrong route — should be /api/webhooks/apify-import
]

# Rotated credentials we explicitly want to scrub, in case Apify ever
# accepts a webhook we somehow missed above.
LEGACY_MARKERS = [
    "apify_api_HIbL7vW2cRnimJ7VezGHO9RfXz7p0W315LD3",   # OLD primary token
    "mg-webhook-4f9c2b8e13a04d76b8b7c9e5f2a1d8e6",       # OLD webhook secret
]

# The one canonical URL we want to KEEP. Any webhook whose URL exactly
# matches this and passes the secret via headers is a keeper.
CANONICAL_URL = "https://apify-catalog.emergent.host/api/webhooks/apify-import"


def is_stale(webhook: dict) -> bool:
    url = (webhook.get("requestUrl") or "")
    lower = url.lower()
    # 1) Exact-match canonical URL → always keep
    if url.rstrip("/") == CANONICAL_URL.rstrip("/"):
        return False
    # 2) Any legacy (rotated) credential in the URL → stale
    if any(marker.lower() in lower for marker in LEGACY_MARKERS):
        return True
    # 3) Any malformed path pattern (secret-in-path, wrong route) → stale
    if any(pat.search(url) for pat in MALFORMED_PATH_PATTERNS):
        return True
    # 4) Otherwise keep it — could be an unrelated webhook the user set up
    return False


def fetch_all(token: str) -> list[dict]:
    """Paginate through /v2/webhooks and return every entry."""
    out: list[dict] = []
    offset = 0
    while True:
        r = requests.get(
            f"{APIFY_API}/webhooks",
            params={"token": token, "limit": 100, "offset": offset},
            timeout=15,
        )
        r.raise_for_status()
        page = r.json().get("data", {})
        items = page.get("items", [])
        out.extend(items)
        if len(items) < 100:
            break
        offset += 100
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true",
                        help="Actually issue DELETEs (default: dry-run only)")
    args = parser.parse_args()

    token = os.environ.get("APIFY_TOKEN")
    if not token:
        print("ERROR: APIFY_TOKEN not set in /app/backend/.env", file=sys.stderr)
        return 2

    print(f"Fetching webhooks with APIFY_TOKEN {token[:14]}…{token[-4:]}")
    webhooks = fetch_all(token)
    print(f"→ {len(webhooks)} webhook(s) found on the Apify account\n")

    stale, keep = [], []
    for w in webhooks:
        (stale if is_stale(w) else keep).append(w)

    print(f"Stale (rotated creds, secret-in-path, or wrong route): {len(stale)}")
    for w in stale:
        print(f"  • id={w.get('id')}  url={w.get('requestUrl')}")
    print(f"\nKeeping (canonical URL only): {len(keep)}")
    for w in keep:
        print(f"  • id={w.get('id')}  url={w.get('requestUrl')}")
    print()

    if not stale:
        print("Nothing to do — no stale webhooks.")
        return 0

    if not args.apply:
        print("(dry-run) re-run with --apply to actually delete the stale entries.")
        return 0

    print(f"Deleting {len(stale)} stale webhook(s)…")
    deleted = 0
    for w in stale:
        wid = w.get("id")
        r = requests.delete(f"{APIFY_API}/webhooks/{wid}", params={"token": token}, timeout=15)
        if r.status_code in (200, 204):
            print(f"  ✓ deleted {wid}")
            deleted += 1
        else:
            print(f"  ✗ failed {wid} → HTTP {r.status_code} {r.text[:120]}")
    print(f"\nDone — {deleted}/{len(stale)} deleted.")
    return 0 if deleted == len(stale) else 1


if __name__ == "__main__":
    raise SystemExit(main())
