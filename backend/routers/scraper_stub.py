"""Deprecation stub — Zyte scraper endpoints have been retired.

The platform now sources all imported inventory exclusively from Apify.
Every legacy `/api/scraper/*` route responds with HTTP 410 Gone and a
pointer to the Apify-only workflow so external callers migrate cleanly.
"""
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/scraper", tags=["scraper-deprecated"])

_MSG = (
    "Zyte scraper endpoints have been removed. Mercari-Global now imports "
    "products only via the Apify Amazon crawler — see /api/admin/sync/apify."
)


# Exact match for /api/scraper (no trailing slash) — Starlette otherwise 307s.
@router.api_route("", methods=["GET", "POST", "PUT", "DELETE", "PATCH"], include_in_schema=False)
async def gone_root():
    raise HTTPException(status_code=410, detail=_MSG)


@router.api_route("/", methods=["GET", "POST", "PUT", "DELETE", "PATCH"], include_in_schema=False)
async def gone_root_slash():
    raise HTTPException(status_code=410, detail=_MSG)


@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"], include_in_schema=False)
async def gone(path: str):
    raise HTTPException(status_code=410, detail=_MSG)
