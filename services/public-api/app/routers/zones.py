"""Router for zone-related endpoints."""

from __future__ import annotations

import json
import logging
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.rate_limit import limiter
from app.dependencies import get_db
from app.schemas.zones import (
    CensusStats,
    NearbySchool,
    PropertyStats,
    ZoneInfo,
    ZoneSummary,
)
from app.services.abs_census import get_or_fetch_suburb_census_stats

logger = logging.getLogger(__name__)

router = APIRouter(tags=["zones"])


@router.get("/{zone_id}/summary")
@limiter.limit("200/hour")
async def zone_summary(
    request: Request,
    zone_id: UUID,
    db: asyncpg.Connection = Depends(get_db),
) -> ZoneSummary:
    """Retrieve aggregated stats, nearby schools, and Census demographics for a zone."""
    # 1. Fetch zone information
    zone_row = await db.fetchrow(
        """
        SELECT id, zone_type, name, state, slug, metadata
        FROM spatial_zones
        WHERE id = $1
        """,
        zone_id,
    )
    if not zone_row:
        raise HTTPException(status_code=404, detail="Zone not found.")

    zone_type = zone_row["zone_type"]
    metadata_val = zone_row["metadata"] or {}
    if isinstance(metadata_val, str):
        try:
            metadata_val = json.loads(metadata_val)
        except Exception:
            metadata_val = {}

    zone_info = ZoneInfo(
        id=zone_row["id"],
        name=zone_row["name"],
        state=zone_row["state"],
        zone_type=zone_type,
        slug=zone_row["slug"],
    )

    # 2. Fetch property stats
    total_count = 0
    with_reports = 0
    median_val = None
    median_land = None

    if zone_type == "SUBURB":
        stats_row = await db.fetchrow(
            """
            SELECT COUNT(*) AS total_count,
                   COUNT(*) FILTER (WHERE pr.status = 'READY') AS with_reports,
                   PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY p.estimated_value)
                       FILTER (WHERE p.estimated_value IS NOT NULL) AS median_estimated_value,
                   PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY p.land_size_sqm)
                       FILTER (WHERE p.land_size_sqm IS NOT NULL) AS median_land_size_sqm
            FROM properties p
            LEFT JOIN property_reports pr ON pr.property_id = p.id
            WHERE p.suburb_id = $1
            """,
            zone_id,
        )
        if stats_row:
            total_count = stats_row["total_count"] or 0
            with_reports = stats_row["with_reports"] or 0
            median_val = stats_row["median_estimated_value"]
            median_land = stats_row["median_land_size_sqm"]

    elif zone_type == "SCHOOL_CATCHMENT":
        # Check if junction table is populated
        junction_count = await db.fetchval(
            "SELECT COUNT(*) FROM property_school_catchments WHERE zone_id = $1",
            zone_id,
        )
        if junction_count and junction_count > 0:
            stats_row = await db.fetchrow(
                """
                SELECT COUNT(*) AS total_count,
                       COUNT(*) FILTER (WHERE pr.status = 'READY') AS with_reports,
                       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY p.estimated_value)
                           FILTER (WHERE p.estimated_value IS NOT NULL) AS median_estimated_value,
                       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY p.land_size_sqm)
                           FILTER (WHERE p.land_size_sqm IS NOT NULL) AS median_land_size_sqm
                FROM properties p
                JOIN property_school_catchments psc ON psc.property_id = p.id
                LEFT JOIN property_reports pr ON pr.property_id = p.id
                WHERE psc.zone_id = $1
                """,
                zone_id,
            )
        else:
            # Fallback to spatial contains query
            stats_row = await db.fetchrow(
                """
                SELECT COUNT(*) AS total_count,
                       COUNT(*) FILTER (WHERE pr.status = 'READY') AS with_reports,
                       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY p.estimated_value)
                           FILTER (WHERE p.estimated_value IS NOT NULL) AS median_estimated_value,
                       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY p.land_size_sqm)
                           FILTER (WHERE p.land_size_sqm IS NOT NULL) AS median_land_size_sqm
                FROM properties p
                LEFT JOIN property_reports pr ON pr.property_id = p.id
                WHERE ST_Contains((SELECT geom FROM spatial_zones WHERE id = $1), p.geom)
                """,
                zone_id,
            )
        if stats_row:
            total_count = stats_row["total_count"] or 0
            with_reports = stats_row["with_reports"] or 0
            median_val = stats_row["median_estimated_value"]
            median_land = stats_row["median_land_size_sqm"]

    property_stats = PropertyStats(
        total_count=total_count,
        with_reports=with_reports,
        median_estimated_value=int(median_val) if median_val is not None else None,
        median_land_size_sqm=float(median_land) if median_land is not None else None,
    )

    # 3. Nearby schools (SUBURB only)
    nearby_schools = []
    if zone_type == "SUBURB":
        school_rows = await db.fetch(
            """
             SELECT s.name, s.school_type, s.sector, s.enrolments,
                                     COALESCE(catchment.slug, catchment_fallback.slug) AS catchment_slug,
                                     COALESCE(catchment.state, catchment_fallback.state) AS catchment_state,
                   ST_Distance(s.geom::geography, ST_Centroid(sz.geom)::geography) AS distance_meters
                        FROM spatial_zones sz
                        JOIN schools s ON ST_DWithin(s.geom::geography, sz.geom::geography, 5000)
                        LEFT JOIN spatial_zones catchment ON catchment.id = s.catchment_zone_id
                        LEFT JOIN LATERAL (
                                SELECT cf.slug, cf.state
                                FROM spatial_zones cf
                                WHERE cf.zone_type = 'SCHOOL_CATCHMENT'
                                    AND cf.state = sz.state
                                    AND ST_Contains(cf.geom, s.geom)
                                ORDER BY ST_Area(cf.geom::geography)
                                LIMIT 1
                        ) catchment_fallback ON catchment.id IS NULL
            WHERE sz.id = $1
            ORDER BY distance_meters
            LIMIT 10
            """,
            zone_id,
        )
        for row in school_rows:
            dist_m = row["distance_meters"]
            nearby_schools.append(
                NearbySchool(
                    name=row["name"],
                    school_type=row["school_type"],
                    sector=row["sector"],
                    enrolments=row["enrolments"],
                    distance_km=round(dist_m / 1000.0, 2) if dist_m is not None else None,
                    catchment_slug=row["catchment_slug"],
                    catchment_state=row["catchment_state"],
                )
            )

    # 4. Census stats (SUBURB only)
    census_stats = None
    if zone_type == "SUBURB":
        sal_code = metadata_val.get("SAL_CODE21")
        if sal_code:
            try:
                census_data = await get_or_fetch_suburb_census_stats(str(sal_code), db)
                if census_data:
                    census_stats = CensusStats(**census_data)
            except Exception as e:
                logger.error(f"Failed to fetch Census stats for SAL_CODE21 {sal_code}: {e}")

    return ZoneSummary(
        zone=zone_info,
        property_stats=property_stats,
        nearby_schools=nearby_schools,
        census_stats=census_stats,
    )
