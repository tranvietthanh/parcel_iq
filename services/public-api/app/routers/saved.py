"""Saved properties endpoints.

POST   /api/saved/{property_id} — save a property
DELETE /api/saved/{property_id} — unsave a property
GET    /api/saved               — list saved properties
"""

from __future__ import annotations

from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies import get_current_user, get_db
from app.routers.properties import _build_detail_sections, _normalize_insights
from app.schemas.property import PropertyDetail
from app.schemas.user import UserRow

router = APIRouter(tags=["saved"])

SAVED_LIST_QUERY = """
    SELECT
        p.id,
        p.address_string,
        p.state,
        p.slug,
        pr.status AS report_status,
        pr.llm_parsed_insights,
        pr.raw_scraped_data
    FROM saved_properties sp
    JOIN properties p ON p.id = sp.property_id
    LEFT JOIN LATERAL (
        SELECT status, llm_parsed_insights, raw_scraped_data
        FROM property_reports
        WHERE property_id = p.id
        ORDER BY created_at DESC LIMIT 1
    ) pr ON TRUE
    WHERE sp.user_id = $1
    ORDER BY sp.saved_at DESC

"""


@router.post("/{property_id}", status_code=201)
async def save_property(
    property_id: UUID,
    current_user: UserRow = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    """Save a property to the user's saved list."""
    # Verify property exists
    prop = await db.fetchrow("SELECT 1 FROM properties WHERE id = $1", property_id)
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found.")

    try:
        await db.execute(
            "INSERT INTO saved_properties (user_id, property_id) VALUES ($1, $2)",
            current_user.id,
            property_id,
        )
    except asyncpg.UniqueViolationError:
        raise HTTPException(status_code=409, detail="Property already saved.")

    return {"saved": True}


@router.delete("/{property_id}")
async def unsave_property(
    property_id: UUID,
    current_user: UserRow = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    """Remove a property from the user's saved list."""
    result = await db.execute(
        "DELETE FROM saved_properties WHERE user_id = $1 AND property_id = $2",
        current_user.id,
        property_id,
    )
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="Saved property not found.")
    return {"unsaved": True}


@router.get("")
async def list_saved(
    current_user: UserRow = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[PropertyDetail]:
    """List all saved properties for the current user."""
    rows = await db.fetch(
        f"{SAVED_LIST_QUERY} LIMIT $2 OFFSET $3",
        current_user.id,
        limit,
        offset,
    )

    results: list[PropertyDetail] = []
    for row in rows:
        insights = _normalize_insights(row.get("llm_parsed_insights")) or {}
        raw_scraped = _normalize_insights(row.get("raw_scraped_data")) or {}
        detail_sections = _build_detail_sections(insights, raw_scraped)

        results.append(
            PropertyDetail(
                id=row["id"],
                address=row["address_string"],
                state=row["state"],
                slug=row["slug"],
                report_status=row["report_status"],
                education=detail_sections["education"],
                connectivity=detail_sections["connectivity"],
                risk_factors=detail_sections["risk_factors"],
                zoning_and_planning=detail_sections["zoning_and_planning"],
                demographic_snapshot=detail_sections["demographic_snapshot"],
            )
        )
    return results
