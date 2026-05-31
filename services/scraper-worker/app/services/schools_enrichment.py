"""Enrich property data with nearby schools information.

Finds all schools within 3km radius and includes catchment status.
Used by scraper task to populate nearby_schools field in ScrapedPropertyData.
"""

from __future__ import annotations

import logging
from typing import Any

import psycopg2

logger = logging.getLogger(__name__)


def enrich_property_with_schools(
    db_conn: psycopg2.extensions.connection,
    property_id: str,
    radius_km: float = 3.0,
) -> dict[str, Any] | None:
    """
    Find all schools within radius_km of a property.
    
    Args:
        db_conn: Synchronous psycopg2 connection
        property_id: UUID of the property
        radius_km: Search radius in kilometers (default 3.0)
    
    Returns:
        Dict with schools_by_type, total_count, search_radius_km
        or None if property not found or has no geometry.
    """
    
    query = """
        WITH property_point AS (
            SELECT geom FROM properties WHERE id = %s
        )
        SELECT 
            s.id,
            s.name,
            s.address,
            s.suburb,
            s.postcode,
            s.school_type,
            s.gender,
            s.sector,
            s.enrolments,
            s.year_range,
            s.website,
            s.phone,
            ST_Y(s.geom) AS lat,
            ST_X(s.geom) AS lng,
            ROUND(
                (ST_Distance(
                    s.geom::geography,
                    (SELECT geom FROM property_point)::geography
                ) / 1000.0)::numeric,
                2
            ) AS distance_km,
            CASE 
                WHEN s.catchment_zone_id IS NOT NULL 
                     AND EXISTS (
                         SELECT 1 FROM spatial_zones sz
                         WHERE sz.id = s.catchment_zone_id
                           AND ST_Contains(
                               sz.geom,
                               (SELECT geom FROM property_point)
                           )
                     )
                THEN true
                ELSE false
            END AS in_catchment,
            CASE
                WHEN s.catchment_zone_id IS NULL THEN 'Zone data not found'
                WHEN EXISTS (
                    SELECT 1 FROM spatial_zones sz
                    WHERE sz.id = s.catchment_zone_id
                      AND ST_Contains(sz.geom, (SELECT geom FROM property_point))
                ) THEN 'Property is within catchment zone'
                ELSE 'Property is outside catchment zone'
            END AS catchment_note,
            EXTRACT(YEAR FROM COALESCE(sz.created_at, NOW())) AS zone_year
        FROM schools s
        LEFT JOIN spatial_zones sz ON s.catchment_zone_id = sz.id
        WHERE 
            ST_DWithin(
                s.geom::geography,
                (SELECT geom FROM property_point)::geography,
                %s
            )
        ORDER BY distance_km ASC
        LIMIT 50;
    """
    
    try:
        with db_conn.cursor() as cur:
            cur.execute(query, (property_id, radius_km * 1000))
            rows = cur.fetchall()
        
        if not rows:
            return None
        
        # Convert rows to dicts and group by school type
        schools_by_type = {}
        for row_idx, row in enumerate(rows):
            try:
                school_dict = {
                    "id": str(row["id"]),
                    "name": row["name"],
                    "address": row["address"],
                    "suburb": row["suburb"],
                    "postcode": row["postcode"],
                    "school_type": row["school_type"],
                    "gender": row["gender"],
                    "sector": row["sector"],
                    "enrolments": row["enrolments"],
                    "year_range": row["year_range"],
                    "website": row["website"],
                    "phone": row["phone"],
                    "lat": float(row["lat"]) if row["lat"] else None,
                    "lng": float(row["lng"]) if row["lng"] else None,
                    "distance_km": float(row["distance_km"]) if row["distance_km"] else 0.0,
                    "in_catchment": row["in_catchment"],
                    "catchment_note": row["catchment_note"],
                    "zone_year": int(row["zone_year"]) if row["zone_year"] else None,
                }
                
                school_type = row["school_type"] or "Other"
                if school_type not in schools_by_type:
                    schools_by_type[school_type] = []
                
                schools_by_type[school_type].append(school_dict)
            except (KeyError, ValueError, TypeError) as e:
                logger.warning(f"Skipping row {row_idx} for property {property_id}: {e}")
                continue
        
        return {
            "schools_by_type": schools_by_type,
            "total_count": sum(len(v) for v in schools_by_type.values()),
            "search_radius_km": radius_km,
        }
    
    except Exception as e:
        logger.error(f"Error enriching schools for property {property_id}: {type(e).__name__}: {e}", exc_info=True)
        return None
