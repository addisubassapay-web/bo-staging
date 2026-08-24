"""Affiliate + Referrals router — extracted from server.py.

Two closely-related concerns collapsed into one module since they both
power the `Refer & Earn` / `Affiliate` tab of the profile UI.
"""
from __future__ import annotations
from typing import List

from fastapi import APIRouter, Depends, HTTPException

from models.affiliate import AffiliateLink, AffiliateLinkCreate
from .deps import get_db, get_current_user

router = APIRouter()


# ---- Affiliate links --------------------------------------------------------

@router.post("/affiliate/links", response_model=AffiliateLink)
async def create_affiliate_link(payload: AffiliateLinkCreate, user: dict = Depends(get_current_user)):
    if not payload.listing_id and not payload.store_id:
        raise HTTPException(400, "Provide listing_id or store_id")
    db = get_db()
    existing = await db.affiliate_links.find_one({
        "affiliate_user_id": user["id"],
        "listing_id": payload.listing_id,
        "store_id": payload.store_id,
    }, {"_id": 0})
    if existing:
        return AffiliateLink(**existing)
    link = AffiliateLink(
        affiliate_user_id=user["id"],
        listing_id=payload.listing_id,
        store_id=payload.store_id,
    )
    await db.affiliate_links.insert_one(link.model_dump())
    return link


@router.get("/affiliate/links", response_model=List[AffiliateLink])
async def my_affiliate_links(user: dict = Depends(get_current_user)):
    db = get_db()
    docs = await db.affiliate_links.find(
        {"affiliate_user_id": user["id"]}, {"_id": 0}
    ).sort("created_at", -1).to_list(500)
    return [AffiliateLink(**d) for d in docs]


@router.get("/affiliate/track/{code}")
async def track_affiliate_click(code: str):
    db = get_db()
    link = await db.affiliate_links.find_one({"code": code, "status": "active"}, {"_id": 0})
    if not link:
        raise HTTPException(404, "Invalid affiliate code")
    await db.affiliate_links.update_one({"code": code}, {"$inc": {"clicks": 1}})
    return {
        "ok": True,
        "listing_id": link.get("listing_id"),
        "store_id": link.get("store_id"),
        "code": code,
    }


@router.get("/affiliate/stats")
async def affiliate_stats(user: dict = Depends(get_current_user)):
    db = get_db()
    links = await db.affiliate_links.find(
        {"affiliate_user_id": user["id"]}, {"_id": 0}
    ).to_list(500)
    total_clicks = sum(l.get("clicks", 0) for l in links)
    total_conversions = sum(l.get("conversions", 0) for l in links)
    total_earnings = sum(l.get("earnings", 0.0) for l in links)
    return {
        "links": len(links),
        "clicks": total_clicks,
        "conversions": total_conversions,
        "earnings": round(total_earnings, 2),
        "conversion_rate": round((total_conversions / total_clicks * 100) if total_clicks else 0, 2),
    }


# ---- Referrals --------------------------------------------------------------

@router.get("/referrals/me")
async def my_referrals(user: dict = Depends(get_current_user)):
    db = get_db()
    l1 = await db.users.find(
        {"referred_by": user["id"]},
        {"_id": 0, "id": 1, "username": 1, "created_at": 1},
    ).to_list(1000)
    l1_ids = [u["id"] for u in l1]
    l2 = await db.users.find(
        {"referred_by": {"$in": l1_ids}},
        {"_id": 0, "id": 1, "username": 1, "referred_by": 1, "created_at": 1},
    ).to_list(1000) if l1_ids else []
    l2_ids = [u["id"] for u in l2]
    l3 = await db.users.find(
        {"referred_by": {"$in": l2_ids}},
        {"_id": 0, "id": 1, "username": 1, "referred_by": 1, "created_at": 1},
    ).to_list(1000) if l2_ids else []
    txs = await db.wallet_txs.find(
        {"user_id": user["id"], "type": "referral"}, {"_id": 0}
    ).to_list(1000)
    total_earnings = sum(t.get("amount", 0) for t in txs)
    return {
        "referral_code": user.get("referral_code"),
        "levels": {"l1": l1, "l2": l2, "l3": l3},
        "counts": {"l1": len(l1), "l2": len(l2), "l3": len(l3)},
        "total_referral_earnings": round(total_earnings, 2),
    }
