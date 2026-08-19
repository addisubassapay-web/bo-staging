#!/usr/bin/env python3
"""Create one active listing for focused checkout UI verification."""
import json
import time

from stripe_removal_verification import API, ADMIN, auth, get_or_create_category, login, request

token, _ = login(ADMIN)
cat = get_or_create_category(token)
payload = {
    "title": f"Stripe removal UI checkout item {int(time.time())}",
    "description": "Temporary item for checkout UI verification.",
    "price": 5.0,
    "category_id": cat["id"],
    "condition": "good",
    "brand": "QA",
    "images": ["https://images.unsplash.com/photo-1516321318423-f06f85e504b3?w=600"],
    "shipping_paid_by": "seller",
    "shipping_method": "Standard",
}
r = request("POST", "/listings", headers=auth(token), json=payload)
r.raise_for_status()
listing = r.json()
print(json.dumps({"api": API, "listing_id": listing["id"], "title": listing["title"]}))