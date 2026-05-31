"""My Properties endpoints.

GET  /api/properties/my/requested             — paginated requested-property history
POST /api/properties/claim-anonymous-requests — claim anonymous requests after sign-in

Anonymous requester identity:
  - Cookie: anon_requester_id (Secure; SameSite=Strict; HttpOnly; Path=/api)
  - 7-day claim window — requests older than 7 days are not claimable
  - Cookie-bound identity: cross-device claiming is not supported (by design)
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from app.core.rate_limit import limiter
from app.dependencies import get_current_user, get_db
from app.schemas.user import UserRow

router = APIRouter(tags=["my-properties"])

ANON_COOKIE_NAME = "anon_requester_id"
ANON_COOKIE_MAX_AGE = 7 * 24 * 60 * 60  # 7 days in seconds
CLAIM_WINDOW_DAYS = 7


def _issue_anon_id(response: Response) -> str:
    """Generate a new opaque anon_requester_id and set it as a secure cookie."""
    anon_id = secrets.token_urlsafe(32)
    response.set_cookie(
        key=ANON_COOKIE_NAME,
        value=anon_id,
        max_age=ANON_COOKIE_MAX_AGE,
        httponly=True,
        secure=True,
        samesite="strict",
        path="/api",
    )
    return anon_id


# ── Anonymous request issuing (used by request-scrape endpoint) ───────────────

async def get_or_create_anon_id(
    request: Request,
    response: Response,
) -> str | None:
    """Return the existing anon_requester_id cookie value, or issue a new one.

    Used by the request-scrape endpoint to attach an anonymous identity to each
    report request so it can be claimed after sign-in.
    """
    existing = request.cookies.get(ANON_COOKIE_NAME)
    if existing:
        return existing
    return _issue_anon_id(response)


# ── Claim endpoint ────────────────────────────────────────────────────────────

@router.post("/claim-anonymous-requests")
@limiter.limit("10/minute")
async def claim_anonymous_requests(
    request: Request,
    current_user: UserRow = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
    anon_requester_id: str | None = Cookie(default=None, alias=ANON_COOKIE_NAME),
) -> dict[str, Any]:
    """Claim previously anonymous report requests for the authenticated user.

    Links property_reports rows with a matching anon_requester_id (and not yet
    linked to a user) to the current user's ID. Only requests within the 7-day
    claim window are eligible.

    Cross-device claiming is not supported — this is cookie-bound only.
    """
    if not anon_requester_id:
        return {"claimed_count": 0, "message": "No anonymous session found."}

    cutoff = datetime.now(timezone.utc) - timedelta(days=CLAIM_WINDOW_DAYS)

    result = await db.execute(
        """
        UPDATE property_reports
        SET requested_by_user_id = $1
        WHERE anon_requester_id = $2
          AND requested_by_user_id IS NULL
          AND created_at >= $3
        """,
        current_user.id,
        anon_requester_id,
        cutoff,
    )

    # asyncpg returns "UPDATE N" — parse the count
    claimed_count = int(result.split()[-1]) if result else 0

    return {
        "claimed_count": claimed_count,
        "message": (
            f"Claimed {claimed_count} request(s)." if claimed_count > 0
            else "No claimable requests found within the 7-day window."
        ),
    }


# ── Requested history endpoint ────────────────────────────────────────────────

@router.get("/my/requested")
@limiter.limit("60/minute")
async def my_requested_properties(
    request: Request,
    current_user: UserRow = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """Return paginated requested-property history for the authenticated user.

    Includes both directly-requested and claimed-anonymous requests.
    Each row includes a has_downloaded_before flag derived from credit_ledger.
    """
    if page < 1:
        page = 1
    if page_size < 1 or page_size > 100:
        page_size = 20
    offset = (page - 1) * page_size

    rows = await db.fetch(
        """
        SELECT
            p.id            AS property_id,
            p.address_string AS address,
            p.state,
            p.slug,
            pr.id           AS report_id,
            pr.status       AS report_status,
            pr.created_at   AS requested_at,
            pr.updated_at   AS ready_at,
            EXISTS (
                SELECT 1 FROM credit_ledger cl
                WHERE cl.user_id = $1
                  AND cl.related_property_id = p.id
                  AND cl.entry_type = 'DOWNLOAD_DEBIT'
            )               AS has_downloaded_before
        FROM property_reports pr
        JOIN properties p ON p.id = pr.property_id
        WHERE pr.requested_by_user_id = $1
        ORDER BY pr.created_at DESC
        LIMIT $2 OFFSET $3
        """,
        current_user.id,
        page_size,
        offset,
    )

    total_count = await db.fetchval(
        """
        SELECT COUNT(*)
        FROM property_reports
        WHERE requested_by_user_id = $1
        """,
        current_user.id,
    )

    return {
        "items": [
            {
                "property_id": str(r["property_id"]),
                "address": r["address"],
                "state": r["state"],
                "slug": r["slug"],
                "report_id": str(r["report_id"]),
                "report_status": r["report_status"],
                "requested_at": r["requested_at"].isoformat() if r["requested_at"] else None,
                "ready_at": r["ready_at"].isoformat() if r["report_status"] == "READY" and r["ready_at"] else None,
                "has_downloaded_before": bool(r["has_downloaded_before"]),
            }
            for r in rows
        ],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_count": total_count or 0,
            "total_pages": max(1, ((total_count or 0) + page_size - 1) // page_size),
        },
    }
