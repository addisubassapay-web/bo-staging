"""Messaging router — Messages + Chat routes extracted from server.py.

Combines the legacy `/messages/*` API and the newer `/chat/*` UI-facing
API since they share the same `db.messages` collection.
"""
from __future__ import annotations
from typing import List

from fastapi import APIRouter, Depends, HTTPException

from models.messages import Message, MessageCreate
from .deps import get_db, get_current_user, notify

router = APIRouter()


# ---- legacy /messages API ---------------------------------------------------

@router.get("/messages/{listing_id}/{other_user_id}", response_model=List[Message])
async def get_messages(listing_id: str, other_user_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    docs = await db.messages.find({
        "listing_id": listing_id,
        "$or": [
            {"sender_id": user["id"], "receiver_id": other_user_id},
            {"sender_id": other_user_id, "receiver_id": user["id"]},
        ],
    }, {"_id": 0}).sort("created_at", 1).to_list(500)
    return [Message(**d) for d in docs]


@router.post("/messages", response_model=Message)
async def send_message(payload: MessageCreate, user: dict = Depends(get_current_user)):
    db = get_db()
    msg = Message(
        listing_id=payload.listing_id,
        sender_id=user["id"],
        sender_name=user["username"],
        receiver_id=payload.receiver_id,
        content=payload.content,
    )
    await db.messages.insert_one(msg.model_dump())
    return msg


# ---- /chat API --------------------------------------------------------------

@router.get("/chat/threads")
async def get_threads(user: dict = Depends(get_current_user)):
    """Return distinct conversation threads for the user."""
    db = get_db()
    pipeline = [
        {"$match": {"$or": [{"sender_id": user["id"]}, {"receiver_id": user["id"]}]}},
        {"$sort": {"created_at": -1}},
        {"$group": {
            "_id": {
                "listing_id": "$listing_id",
                "other": {"$cond": [{"$eq": ["$sender_id", user["id"]]}, "$receiver_id", "$sender_id"]},
            },
            "last_content": {"$first": "$content"},
            "last_at": {"$first": "$created_at"},
            "sender_id": {"$first": "$sender_id"},
        }},
        {"$sort": {"last_at": -1}},
    ]
    threads = await db.messages.aggregate(pipeline).to_list(200)
    result = []
    for t in threads:
        other_id = t["_id"]["other"]
        listing_id = t["_id"]["listing_id"]
        other = await db.users.find_one({"id": other_id}, {"_id": 0, "id": 1, "username": 1})
        listing = await db.listings.find_one(
            {"id": listing_id},
            {"_id": 0, "id": 1, "title": 1, "images": 1, "price": 1},
        )
        result.append({
            "listing_id": listing_id,
            "other_user_id": other_id,
            "other_username": other.get("username") if other else "Unknown",
            "listing_title": listing.get("title") if listing else "Listing removed",
            "listing_image": (listing.get("images") or [None])[0] if listing else None,
            "last_message": t.get("last_content", "")[:120],
            "last_at": t.get("last_at"),
            "unread": False,
        })
    return result


@router.get("/chat/{listing_id}/{other_user_id}", response_model=List[Message])
async def chat_messages(listing_id: str, other_user_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    docs = await db.messages.find({
        "listing_id": listing_id,
        "$or": [
            {"sender_id": user["id"], "receiver_id": other_user_id},
            {"sender_id": other_user_id, "receiver_id": user["id"]},
        ],
    }, {"_id": 0}).sort("created_at", 1).to_list(500)
    return [Message(**d) for d in docs]


@router.post("/chat", response_model=Message)
async def send_chat_message(payload: MessageCreate, user: dict = Depends(get_current_user)):
    if not payload.content.strip():
        raise HTTPException(400, "Empty message")
    db = get_db()
    msg = Message(
        listing_id=payload.listing_id,
        sender_id=user["id"],
        sender_name=user["username"],
        receiver_id=payload.receiver_id,
        content=payload.content.strip(),
    )
    await db.messages.insert_one(msg.model_dump())
    await notify(
        payload.receiver_id, "message",
        f"New message from {user['username']}",
        payload.content[:120],
        f"/chat/{payload.listing_id}/{user['id']}",
    )
    return msg
