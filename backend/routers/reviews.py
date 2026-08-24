"""Reviews router — extracted from server.py.

Buyers post ratings/comments on completed orders; aggregate is written
back onto the seller's user doc. Kept intentionally close to the
original inline implementation to avoid regressions.
"""
from __future__ import annotations
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException

from models.reviews import Review, ReviewCreate
from .deps import get_db, get_current_user, notify

router = APIRouter()


@router.post("/reviews", response_model=Review)
async def create_review(payload: ReviewCreate, user: dict = Depends(get_current_user)):
    if payload.rating < 1 or payload.rating > 5:
        raise HTTPException(400, "Rating must be 1-5")
    db = get_db()
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
        await db.users.update_one(
            {"id": order["seller_id"]},
            {"$set": {"rating": round(agg[0]["avg"], 2)}},
        )
    await notify(
        order["seller_id"], "review",
        f"New {payload.rating}-star review",
        (payload.comment or "")[:120],
        f"/listing/{order['listing_id']}",
    )
    return review


@router.get("/reviews/seller/{seller_id}", response_model=List[Review])
async def get_seller_reviews(seller_id: str):
    db = get_db()
    docs = await db.reviews.find({"seller_id": seller_id}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return [Review(**d) for d in docs]


@router.get("/reviews/listing/{listing_id}", response_model=List[Review])
async def get_listing_reviews(listing_id: str):
    db = get_db()
    docs = await db.reviews.find({"listing_id": listing_id}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return [Review(**d) for d in docs]


@router.get("/reviews/order/{order_id}", response_model=Optional[Review])
async def get_order_review(order_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    doc = await db.reviews.find_one(
        {"order_id": order_id, "reviewer_id": user["id"]}, {"_id": 0}
    )
    return Review(**doc) if doc else None
