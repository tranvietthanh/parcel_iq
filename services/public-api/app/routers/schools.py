"""Router for school-related endpoints."""

from __future__ import annotations

from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_db
from app.schemas.schools import SchoolData

router = APIRouter(tags=["schools"])


@router.get("/by-catchment/{zone_id}")
async def school_by_catchment(
    zone_id: UUID,
    db: asyncpg.Connection = Depends(get_db),
) -> SchoolData:
    """Retrieve school metadata for a specific catchment zone."""
    row = await db.fetchrow(
        """
        SELECT id, name, address, suburb, postcode, state,
               school_type, gender, sector, enrolments, year_range,
               website, phone
        FROM schools
        WHERE catchment_zone_id = $1
        """,
        zone_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="No school found for this catchment.")
    return SchoolData(**dict(row))
