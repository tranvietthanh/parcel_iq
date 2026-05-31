"""Router for sitemap URL generation.

Returns all slugs and last-modified timestamps needed by the Next.js
``app/sitemap.ts`` to produce a dynamic ``sitemap.xml``.  No authentication
required — only slugs are exposed, no sensitive data.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import List

import asyncpg
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from app.core.rate_limit import limiter
from app.dependencies import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["sitemap"])


# ── Response models ───────────────────────────────────────────────────────────


class SitemapZone(BaseModel):
    slug: str
    zone_type: str
    state: str
    updated_at: datetime


class SitemapProperty(BaseModel):
    slug: str
    updated_at: datetime


class SitemapUrlsResponse(BaseModel):
    zones: List[SitemapZone]
    properties: List[SitemapProperty]


# ── Endpoint ──────────────────────────────────────────────────────────────────


@router.get("/urls", response_model=SitemapUrlsResponse)
@limiter.limit("60/hour")
async def get_sitemap_urls(
    request: Request,
    db: asyncpg.Connection = Depends(get_db),
) -> SitemapUrlsResponse:
    """Return all slugs for sitemap generation.

    Two queries:
    1. Suburb + school catchment zones from ``spatial_zones``.
    2. Properties that have at least one ``READY`` report, de-duplicated
       via ``GROUP BY`` to handle multiple report rows per property.
    """
    # 1. Zones (suburbs + school catchments)
    zone_rows = await db.fetch(
        """
        SELECT slug,
               zone_type,
               LOWER(state) AS state,
               COALESCE(updated_at, created_at, NOW()) AS updated_at
        FROM spatial_zones
        WHERE zone_type IN ('SUBURB', 'SCHOOL_CATCHMENT')
          AND slug IS NOT NULL
          AND slug != ''
        ORDER BY zone_type, state, slug
        """
    )

    # 2. Properties with completed reports (deduplicated)
    property_rows = await db.fetch(
        """
        SELECT p.slug,
               COALESCE(
                   GREATEST(p.updated_at, pr.latest_updated_at),
                   p.created_at,
                   NOW()
               ) AS updated_at
        FROM properties p
        INNER JOIN (
            SELECT property_id,
                   MAX(updated_at) AS latest_updated_at
            FROM property_reports
            WHERE status = 'READY'
            GROUP BY property_id
        ) pr ON pr.property_id = p.id
        WHERE p.slug IS NOT NULL
          AND p.slug != ''
        ORDER BY p.slug
        """
    )

    zones = [
        SitemapZone(
            slug=row["slug"],
            zone_type=row["zone_type"],
            state=row["state"],
            updated_at=row["updated_at"],
        )
        for row in zone_rows
    ]

    properties = [
        SitemapProperty(
            slug=row["slug"],
            updated_at=row["updated_at"],
        )
        for row in property_rows
    ]

    return SitemapUrlsResponse(zones=zones, properties=properties)
