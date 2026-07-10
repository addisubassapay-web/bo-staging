"""LLM-powered batch translation for Japanese product listings -> English.

Uses emergentintegrations with EMERGENT_LLM_KEY. Model: gpt-4.1-nano
(cheapest + fastest for translation tasks). Batches 25 items per call.
"""
import os
import json
import asyncio
import logging
import re
import uuid
from typing import List, Dict, Optional

from emergentintegrations.llm.chat import LlmChat, UserMessage

logger = logging.getLogger(__name__)

BATCH_SIZE = 25
MODEL_PROVIDER = "openai"
MODEL_NAME = "gpt-4.1-nano"

SYSTEM_PROMPT = (
    "You are a professional Japanese-to-English translator specialized in e-commerce product listings. "
    "For each item you receive, produce a natural, marketable English title (max 90 chars) and a "
    "concise English description (max 220 chars). Preserve brand names in original Latin script "
    "where present. Return ONLY a JSON array with objects: "
    '[{"i": <index>, "title": "...", "description": "..."}]. '
    "Do not add any commentary."
)


def _extract_json(text: str) -> Optional[list]:
    """Best-effort JSON array extraction from LLM output."""
    text = text.strip()
    # Strip code fences
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```\s*$", "", text)
    # Find first [ ... ] block
    m = re.search(r"\[[\s\S]*\]", text)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


async def translate_batch(items: List[Dict]) -> List[Dict]:
    """Translate a batch of up to BATCH_SIZE items.

    Each input item: { id, title_ja, description_ja, brand, category_name, condition }
    Returns list aligned with `items`, each with { id, title, description }.
    """
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        raise RuntimeError("EMERGENT_LLM_KEY missing from environment")

    payload = []
    for i, it in enumerate(items):
        payload.append({
            "i": i,
            "title_ja": (it.get("title_ja") or "")[:200],
            "description_ja": (it.get("description_ja") or "")[:600],
            "brand": (it.get("brand") or "")[:60],
            "category": it.get("category_name") or "",
            "condition": it.get("condition") or "",
        })

    user_msg = (
        "Translate these Japanese Mercari listings to natural English. "
        "Output JSON array only.\n\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )

    chat = LlmChat(
        api_key=api_key,
        session_id=f"translate-{uuid.uuid4().hex[:8]}",
        system_message=SYSTEM_PROMPT,
    ).with_model(MODEL_PROVIDER, MODEL_NAME)

    try:
        response = await chat.send_message(UserMessage(text=user_msg))
    except Exception as e:
        logger.error(f"LLM translation error: {e}")
        return []

    parsed = _extract_json(response) if isinstance(response, str) else None
    if not parsed:
        logger.error(f"Failed to parse LLM output: {str(response)[:200]}")
        return []

    # Align results back to original items by index
    result: List[Dict] = []
    by_index: Dict[int, Dict] = {}
    for r in parsed:
        if isinstance(r, dict) and "i" in r:
            try:
                by_index[int(r["i"])] = r
            except (TypeError, ValueError):
                pass

    for i, it in enumerate(items):
        r = by_index.get(i, {})
        title = (r.get("title") or "").strip()[:120]
        description = (r.get("description") or "").strip()[:400]
        if not title:
            # fallback template
            title = f"{it.get('brand') or it.get('category_name') or 'Mercari Japan Import'} — item"
        if not description:
            description = f"Preloved item from Japan. Condition: {it.get('condition', 'good')}."
        result.append({
            "id": it["id"],
            "title": title,
            "description": description,
        })

    return result


async def translate_all_listings(db, progress_key: str = "translation") -> Dict:
    """Iterate over all untranslated listings and translate in batches. Runs to completion.

    Progress is stored in sync_state doc under `translation_progress`.
    """
    total = await db.listings.count_documents({"translated": {"$ne": True}})
    if total == 0:
        return {"ok": True, "message": "Nothing to translate", "done": 0}

    done = 0
    batch: List[Dict] = []
    batch_ids: List[str] = []
    cursor = db.listings.find(
        {"translated": {"$ne": True}},
        {"_id": 0, "id": 1, "title": 1, "description": 1, "brand": 1, "category_name": 1, "condition": 1},
    )

    async def flush(current_batch: List[Dict]) -> int:
        if not current_batch:
            return 0
        translated = await translate_batch(current_batch)
        if not translated:
            return 0
        # Bulk update
        for t in translated:
            await db.listings.update_one(
                {"id": t["id"]},
                {"$set": {
                    "title": t["title"],
                    "description": t["description"],
                    "translated": True,
                    "original_title_ja": next((b["title_ja"] for b in current_batch if b["id"] == t["id"]), None),
                }},
            )
        return len(translated)

    async for doc in cursor:
        batch.append({
            "id": doc["id"],
            "title_ja": doc.get("title"),
            "description_ja": doc.get("description"),
            "brand": doc.get("brand"),
            "category_name": doc.get("category_name"),
            "condition": doc.get("condition"),
        })
        batch_ids.append(doc["id"])
        if len(batch) >= BATCH_SIZE:
            n = await flush(batch)
            done += n
            batch = []
            batch_ids = []
            # Progress update
            await db.sync_state.update_one(
                {"id": "kaggle"},
                {"$set": {
                    "translation_progress": {
                        "done": done,
                        "total": total,
                        "pct": round(done / total * 100, 1),
                    }
                }},
                upsert=True,
            )
            # Small yield so other requests are served
            await asyncio.sleep(0.05)

    # Final flush
    if batch:
        n = await flush(batch)
        done += n

    await db.sync_state.update_one(
        {"id": "kaggle"},
        {"$set": {
            "translation_progress": {
                "done": done,
                "total": total,
                "pct": 100.0,
                "completed": True,
            }
        }},
        upsert=True,
    )

    return {"ok": True, "translated": done, "total": total}
