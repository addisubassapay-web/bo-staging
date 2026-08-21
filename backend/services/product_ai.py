"""AI product polish — shortens Amazon-style titles and generates SEO-friendly
descriptions for products in the permanent `products` catalog.

Uses the Emergent LLM Key (OpenAI GPT provider) via `emergentintegrations`.
Idempotent: any product with `ai_polished_at` timestamp is skipped unless
`force=True`. Writes back to Mongo under a dedicated `ai_meta` sub-doc so
the raw Amazon fields are preserved for audit.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from emergentintegrations.llm.chat import LlmChat, UserMessage

logger = logging.getLogger(__name__)

# GPT-5.4 = default OpenAI model per playbook — cheapest good-quality choice.
_MODEL_PROVIDER = "openai"
_MODEL_NAME = "gpt-5.4"

_SYSTEM = (
    "You rewrite Amazon-style product listings so they read like a "
    "high-end marketplace. Reply with STRICT JSON — no markdown fences, "
    "no commentary — using EXACTLY these keys: polished_title, "
    "polished_description, meta_title, meta_description. "
    "Constraints: polished_title <= 70 chars, no brand prefix, natural. "
    "polished_description 100–200 chars, benefit-focused, 1–2 sentences. "
    "meta_title <= 60 chars. meta_description <= 155 chars."
)


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    """LLMs sometimes wrap JSON in ``` fences. Grab the first {…} block."""
    if not text:
        return None
    text = text.strip()
    # Strip markdown fences if present
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.DOTALL).strip()
    try:
        return json.loads(text)
    except Exception:
        # Best-effort — find first { … } span
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            return None
        try:
            return json.loads(m.group(0))
        except Exception:
            return None


async def polish_one(product: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Ask GPT to polish ONE product. Returns the parsed JSON dict on success,
    or None on any failure (never raises — the caller iterates over many)."""
    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        logger.error("EMERGENT_LLM_KEY missing — skipping polish")
        return None
    title = (product.get("title") or "").strip()[:200]
    desc = (product.get("description") or "").strip()[:800]
    category = product.get("category") or "?"
    if not title:
        return None
    prompt = (
        f"Category: {category}\n"
        f"Source title: {title}\n"
        f"Source description: {desc or '(none)'}\n\n"
        "Return the JSON now."
    )
    try:
        chat = LlmChat(
            api_key=key,
            session_id=f"polish-{uuid.uuid4().hex[:12]}",
            system_message=_SYSTEM,
        ).with_model(_MODEL_PROVIDER, _MODEL_NAME)
        # Use send_message (non-streaming) since we consume the entire JSON body
        raw = await chat.send_message(UserMessage(text=prompt))
        text = raw if isinstance(raw, str) else getattr(raw, "content", str(raw))
        data = _extract_json(text)
        if not data or not data.get("polished_title"):
            return None
        # Trim to enforce limits even if the LLM overshoots
        data["polished_title"] = (data.get("polished_title") or "").strip()[:70]
        data["polished_description"] = (data.get("polished_description") or "").strip()[:220]
        data["meta_title"] = (data.get("meta_title") or "").strip()[:60]
        data["meta_description"] = (data.get("meta_description") or "").strip()[:155]
        return data
    except Exception as e:
        logger.warning(f"polish failed for {product.get('id')!s}: {e}")
        return None


async def polish_batch(
    db,
    limit: int = 50,
    force: bool = False,
    only_active: bool = True,
    concurrency: int = 4,
) -> Dict[str, Any]:
    """Polish up to `limit` products in parallel.
    - Skips already-polished rows unless `force=True`.
    - `concurrency=4` keeps us well under any RPM limits.
    """
    query: Dict[str, Any] = {}
    if only_active:
        query["is_active"] = True
    if not force:
        query["ai_polished_at"] = {"$exists": False}
    cursor = db.products.find(query, {"_id": 0, "id": 1, "title": 1, "description": 1, "category": 1})
    products = await cursor.limit(limit).to_list(limit)
    if not products:
        return {"scanned": 0, "polished": 0, "skipped": 0, "failures": 0}

    sem = asyncio.Semaphore(concurrency)
    now = datetime.now(timezone.utc)
    counters = {"polished": 0, "failures": 0, "skipped": 0}

    async def _worker(p: Dict[str, Any]):
        async with sem:
            data = await polish_one(p)
            if data:
                await db.products.update_one(
                    {"id": p["id"]},
                    {"$set": {
                        "ai_meta": data,
                        "polished_title": data.get("polished_title"),
                        "meta_title": data.get("meta_title"),
                        "meta_description": data.get("meta_description"),
                        "ai_polished_at": now,
                    }},
                )
                counters["polished"] += 1
            else:
                # Still stamp `ai_polished_at` so a permanent failure doesn't loop forever.
                await db.products.update_one(
                    {"id": p["id"]},
                    {"$set": {"ai_polished_at": now, "ai_polish_failed": True}},
                )
                counters["failures"] += 1

    await asyncio.gather(*[_worker(p) for p in products])
    return {"scanned": len(products), **counters}
