"""Pydantic schemas for property endpoints."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class PropertyDetail(BaseModel):
    """Curated property detail payload for client display.

    Only includes section-level data. Never returns the full raw payload.
    """

    id: UUID
    address: str
    state: str
    slug: str | None = None
    report_status: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    education: dict | None = None
    connectivity: dict | None = None
    risk_factors: dict | None = None
    zoning_and_planning: dict | None = None
    demographic_snapshot: dict | None = None
