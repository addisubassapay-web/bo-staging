"""
Shared "real user first" helpers for the /api/admin/* list endpoints.

The database is 98% synthetic (e2e tests, master-pass fixtures, apify seeds,
scraper placeholders). Admins waste time scrolling past those rows to find a
handful of genuine users. Every admin listing endpoint that has an owner /
seller / buyer id should call ``real_users_first`` before returning docs so the
real-user rows float to the top while still preserving the intended
``created_at DESC`` ordering within each group.

Rules for "synthetic":
- Email domain is on the internal allow-list (``example.com``, ``e2e.com``,
  ``*.local``, ``apify.local``, ``localhost``); OR
- Email local-part or username starts with a fixture prefix
  (``e2e_``, ``case_``, ``seed_``, ``fixture_``, ``test_``,
  ``mpo1_/mpo2_/mpo3_``, ``upper_``, ``lo_``, ``buyer_``, ``seller_``); OR
- Email is missing / malformed.
"""
from __future__ import annotations

from datetime import datetime
from typing import Iterable, List, Set

_SYNTHETIC_DOMAINS = frozenset({
    "example.com",
    "e2e.com",
    "t.local",
    "case.local",
    "test.local",
    "apify.local",
    "mercari.local",
    "localhost",
})

_FIXTURE_PREFIXES = (
    "mpo1_", "mpo2_", "mpo3_",
    "e2e_", "case_", "seed_", "fixture_", "test_",
    "upper_", "lo_",
    "buyer_", "seller_",
)


def is_synthetic_email(email: str, username: str = "") -> bool:
    email = (email or "").lower().strip()
    if not email or "@" not in email:
        return True
    local, _, domain = email.rpartition("@")
    if domain in _SYNTHETIC_DOMAINS:
        return True
    if domain.endswith(".local"):
        return True
    uname = (username or "").lower()
    for p in _FIXTURE_PREFIXES:
        if local.startswith(p) or uname.startswith(p):
            return True
    return False


def is_synthetic_user_doc(user: dict) -> bool:
    if not user:
        return True
    return is_synthetic_email(user.get("email") or "", user.get("username") or "")


async def real_user_ids(db, user_ids: Iterable[str]) -> Set[str]:
    """Return the subset of ``user_ids`` that correspond to real users.

    Missing / orphaned ids are NOT included - they behave as synthetic so
    abandoned fixture data doesn't float ahead of genuine rows.
    """
    ids = {i for i in (user_ids or []) if i}
    if not ids:
        return set()
    cursor = db.users.find(
        {"id": {"$in": list(ids)}},
        {"_id": 0, "id": 1, "email": 1, "username": 1},
    )
    out: Set[str] = set()
    async for u in cursor:
        if not is_synthetic_user_doc(u):
            out.add(u.get("id"))
    return out


async def synthetic_user_ids(db, user_ids: Iterable[str]) -> Set[str]:
    ids = {i for i in (user_ids or []) if i}
    if not ids:
        return set()
    reals = await real_user_ids(db, ids)
    return ids - reals


def _created_ts(doc: dict, field: str = "created_at") -> float:
    c = doc.get(field)
    if isinstance(c, datetime):
        try:
            return c.timestamp()
        except Exception:
            return 0.0
    if isinstance(c, str):
        # Fall back to lexicographic sort key for ISO strings.
        try:
            return datetime.fromisoformat(c.replace("Z", "+00:00")).timestamp()
        except Exception:
            return 0.0
    return 0.0


async def real_users_first(
    db,
    docs: List[dict],
    id_fields: Iterable[str],
    *,
    created_field: str = "created_at",
) -> List[dict]:
    """
    Sort ``docs`` so entries owned by real users come first, keeping DESC
    ``created_at`` ordering within each group.

    ``id_fields`` is the tuple of doc keys that hold a user id (e.g.
    ``("owner_id",)`` for stores, ``("buyer_id", "seller_id")`` for orders).
    A doc is treated as synthetic only when *every* referenced user id is
    synthetic - so a real buyer with a fixture seller (or vice versa) still
    surfaces at the top for triage.
    """
    if not docs:
        return docs

    id_fields = tuple(id_fields)
    all_ids: Set[str] = set()
    for d in docs:
        for f in id_fields:
            v = d.get(f)
            if v:
                all_ids.add(v)

    real_ids = await real_user_ids(db, all_ids)

    def _is_doc_real(d: dict) -> bool:
        vals = [d.get(f) for f in id_fields if d.get(f)]
        if not vals:
            return False
        # A doc counts as "real" if ANY referenced user id belongs to a real
        # user (e.g. a real buyer purchasing from a fixture seller still
        # surfaces for triage). Every id missing / synthetic -> synthetic doc.
        return any(v in real_ids for v in vals)

    docs.sort(key=lambda d: (not _is_doc_real(d), -_created_ts(d, created_field)))
    return docs


async def filter_real_only(
    db,
    docs: List[dict],
    id_fields: Iterable[str],
) -> List[dict]:
    """Drop synthetic docs entirely. Real = ANY referenced user id is real."""
    if not docs:
        return docs
    id_fields = tuple(id_fields)
    all_ids: Set[str] = set()
    for d in docs:
        for f in id_fields:
            v = d.get(f)
            if v:
                all_ids.add(v)
    real_ids = await real_user_ids(db, all_ids)

    def keep(d: dict) -> bool:
        vals = [d.get(f) for f in id_fields if d.get(f)]
        return any(v in real_ids for v in vals) if vals else False

    return [d for d in docs if keep(d)]
