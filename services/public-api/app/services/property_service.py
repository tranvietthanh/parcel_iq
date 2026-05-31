"""Property service — shared business logic for property lookups."""

from __future__ import annotations

from uuid import UUID

import asyncpg


async def get_property_by_id(db: asyncpg.Connection, property_id: UUID) -> dict | None:
    """Fetch a single property row. Returns None if not found."""
    row = await db.fetchrow(
        "SELECT * FROM properties WHERE id = $1",
        property_id,
    )
    return dict(row) if row else None
