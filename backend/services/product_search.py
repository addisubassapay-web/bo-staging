"""Product search + suggest.

Two goals: (1) surface tiles as users type on `/products`, and (2)
recover from typos so shoppers don't rage-quit when they misspell a
brand. The endpoint feeds an autocomplete dropdown; it should stay
snappy on 4,500+ products so we hedge our bets with several fast
Mongo passes rather than one clever aggregation.

Response shape (all sections optional):
    {
      "query": "<original>",
      "corrected": "<fuzzy-corrected q or None>",
      "products": [{id, title, price, image, category, in_stock}, ...],
      "categories": [{name, slug, count}],  # matching categories
      "terms": ["...", ...],                # popular related terms
      "took_ms": 12
    }
"""
from __future__ import annotations

import difflib
import re
import time
from typing import Dict, List, Optional


# Common shopping terms we use as the "vocabulary" for fuzzy correction.
# Extended with the category list on load so users typing "electronic"
# still get corrected to "electronics".
_CANONICAL_VOCAB: set = {
    "women", "men", "kids", "electronics", "home", "beauty",
    "sports", "toys", "books", "handmade",
}


def _tokenize(s: str) -> List[str]:
    """Rough word split — kept greedy so acronyms like "USB" survive."""
    return [t for t in re.split(r"[^a-z0-9]+", s.lower()) if t]


async def _harvest_vocab(db, cap: int = 3000) -> set:
    """Cache the top-N most frequent title tokens as our fuzzy-correction
    vocabulary. Runs once per process (module-level `_vocab` cache)."""
    global _vocab_cache
    if _vocab_cache is not None:
        return _vocab_cache

    counts: Dict[str, int] = {}
    async for doc in db.products.find({"is_active": True}, {"_id": 0, "title": 1}):
        for tok in _tokenize(doc.get("title") or ""):
            if len(tok) < 3:
                continue
            counts[tok] = counts.get(tok, 0) + 1
    # Take the top-N; add canonical vocab so category terms always exist.
    top = sorted(counts.items(), key=lambda kv: -kv[1])[:cap]
    _vocab_cache = set(t for t, _ in top) | _CANONICAL_VOCAB
    return _vocab_cache


_vocab_cache: Optional[set] = None


def _correct_token(tok: str, vocab: set) -> Optional[str]:
    """Return the closest vocab word, if one is close enough. difflib's
    get_close_matches is O(len(vocab)) but our vocab is <=3k so this is
    fine at request time."""
    if tok in vocab or len(tok) < 3:
        return None
    matches = difflib.get_close_matches(tok, vocab, n=1, cutoff=0.78)
    return matches[0] if matches else None


def _try_correct_query(q: str, vocab: set) -> Optional[str]:
    """Correct the FULL query string token-by-token. Returns the fixed
    string, or None if no correction was applied."""
    tokens = _tokenize(q)
    if not tokens:
        return None
    fixed: List[str] = []
    any_change = False
    for t in tokens:
        c = _correct_token(t, vocab)
        if c:
            any_change = True
            fixed.append(c)
        else:
            fixed.append(t)
    return " ".join(fixed) if any_change else None


async def _prefix_products(db, q: str, limit: int) -> List[dict]:
    """Fast prefix hit — `Nintendo Sw…` → tiles as user types."""
    escaped = re.escape(q)
    cursor = (
        db.products.find(
            {
                "is_active": True,
                "title": {"$regex": f"^{escaped}", "$options": "i"},
            },
            {"_id": 0, "id": 1, "title": 1, "price": 1, "currency": 1,
             "images": 1, "category": 1, "in_stock": 1},
        )
        .sort([("in_stock", -1)])
        .limit(limit)
    )
    return await cursor.to_list(length=limit)


async def _substring_products(db, q: str, limit: int, exclude_ids: set) -> List[dict]:
    """Second pass — anywhere in title."""
    escaped = re.escape(q)
    cursor = (
        db.products.find(
            {
                "is_active": True,
                "title": {"$regex": escaped, "$options": "i"},
                "id": {"$nin": list(exclude_ids)} if exclude_ids else {"$exists": True},
            },
            {"_id": 0, "id": 1, "title": 1, "price": 1, "currency": 1,
             "images": 1, "category": 1, "in_stock": 1},
        )
        .sort([("in_stock", -1)])
        .limit(limit)
    )
    return await cursor.to_list(length=limit)


async def _matching_categories(db, q: str) -> List[dict]:
    """Category chips that share tokens with the query."""
    from services.product_category import CANONICAL_CATEGORIES
    tokens = set(_tokenize(q))
    matches: List[dict] = []
    for cat in CANONICAL_CATEGORIES:
        if cat.lower() in tokens or any(cat.lower().startswith(t) or t.startswith(cat.lower()) for t in tokens if len(t) > 2):
            n = await db.products.count_documents({"is_active": True, "category": cat})
            if n:
                matches.append({"name": cat, "slug": cat.lower(), "count": n})
    return matches


async def _related_terms(db, q: str, limit: int = 6) -> List[str]:
    """Related search terms — grabs common tokens co-occurring in
    matching product titles. Cheap to compute over a small hit sample."""
    escaped = re.escape(q)
    docs = await (
        db.products.find(
            {
                "is_active": True,
                "title": {"$regex": escaped, "$options": "i"},
            },
            {"_id": 0, "title": 1},
        )
        .limit(60)
        .to_list(60)
    )
    q_tokens = set(_tokenize(q))
    counts: Dict[str, int] = {}
    for d in docs:
        for tok in _tokenize(d.get("title") or ""):
            if tok in q_tokens or len(tok) < 4 or tok.isdigit():
                continue
            counts[tok] = counts.get(tok, 0) + 1
    # Take top-N by frequency
    top = sorted(counts.items(), key=lambda kv: -kv[1])[:limit]
    return [t for t, _ in top]


async def build_suggest(
    db,
    q: str,
    product_limit: int = 8,
) -> dict:
    """One-shot builder used by the endpoint."""
    t0 = time.time()
    q_stripped = (q or "").strip()

    result: Dict[str, object] = {
        "query": q_stripped,
        "corrected": None,
        "products": [],
        "categories": [],
        "terms": [],
    }
    if len(q_stripped) < 2:
        result["took_ms"] = int((time.time() - t0) * 1000)
        return result

    # 1) Direct product hits (prefix + substring)
    prefix_hits = await _prefix_products(db, q_stripped, product_limit)
    remaining = max(0, product_limit - len(prefix_hits))
    exclude = {p["id"] for p in prefix_hits}
    substr_hits = await _substring_products(db, q_stripped, remaining, exclude) if remaining else []
    products = prefix_hits + substr_hits

    # 2) If we found nothing, try a spelling correction and retry
    corrected: Optional[str] = None
    if not products:
        vocab = await _harvest_vocab(db)
        corrected = _try_correct_query(q_stripped, vocab)
        if corrected and corrected != q_stripped.lower():
            products = await _prefix_products(db, corrected, product_limit)
            if len(products) < product_limit:
                exclude = {p["id"] for p in products}
                more = await _substring_products(db, corrected, product_limit - len(products), exclude)
                products.extend(more)
            result["corrected"] = corrected

    # 3) Matching categories (highlights when query matches a bucket name)
    result["categories"] = await _matching_categories(db, corrected or q_stripped)

    # 4) Related terms co-occurring in hits
    result["terms"] = await _related_terms(db, corrected or q_stripped)

    result["products"] = products
    result["took_ms"] = int((time.time() - t0) * 1000)
    return result
