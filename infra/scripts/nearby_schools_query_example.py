"""
Example query to find nearby schools for a property report.

This would be used in:
- services/scraper-worker/app/tasks.py (add to scraped data)
- services/public-api/app/routers/properties.py (add to report response)
"""

import asyncpg

async def get_nearby_schools(
    db_pool: asyncpg.Pool,
    property_id: str,
    radius_km: float = 3.0,
) -> list[dict]:
    """
    Find all schools within radius_km of a property.
    
    Returns enriched school data including:
    - Basic info (name, address, type, sector)
    - Distance from property
    - Whether property is in catchment
    """
    
    query = """
        WITH property_point AS (
            SELECT geom FROM properties WHERE id = $1
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
                ST_Distance(
                    s.geom::geography,
                    (SELECT geom FROM property_point)::geography
                ) / 1000.0,
                2
            ) AS distance_km,
            -- Check if property is within this school's catchment zone
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
            -- Catchment note for UI
            CASE
                WHEN s.catchment_zone_id IS NULL THEN 'Zone data not found — verify at findmyschool.vic.gov.au'
                WHEN EXISTS (
                    SELECT 1 FROM spatial_zones sz
                    WHERE sz.id = s.catchment_zone_id
                      AND ST_Contains(sz.geom, (SELECT geom FROM property_point))
                ) THEN 'Property is within catchment zone'
                ELSE 'Property is outside catchment zone'
            END AS catchment_note,
            EXTRACT(YEAR FROM sz.created_at) AS zone_year
        FROM schools s
        LEFT JOIN spatial_zones sz ON s.catchment_zone_id = sz.id
        WHERE 
            -- Within radius (using geography for accurate distance)
            ST_DWithin(
                s.geom::geography,
                (SELECT geom FROM property_point)::geography,
                $2 * 1000  -- Convert km to meters
            )
        ORDER BY distance_km ASC
        LIMIT 50;  -- Reasonable cap (3km radius = ~28 km² area)
    """
    
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(query, property_id, radius_km)
    
    return [dict(row) for row in rows]


# Example usage in scraper worker task
async def enrich_with_schools(property_id: str, db_pool: asyncpg.Pool) -> dict:
    """Add nearby schools to property report data."""
    schools = await get_nearby_schools(db_pool, property_id, radius_km=3.0)
    
    # Group by type for better UX
    primary_schools = [s for s in schools if s["school_type"] == "Primary"]
    secondary_schools = [s for s in schools if s["school_type"] == "Secondary"]
    
    return {
        "nearby_schools": {
            "primary": primary_schools,
            "secondary": secondary_schools,
            "combined": [s for s in schools if s["school_type"] == "Combined"],
            "total_count": len(schools),
            "search_radius_km": 3.0,
        }
    }


# Example output format (matches your requirement):
EXAMPLE_OUTPUT = {
    "nearby_schools": {
        "primary": [
            {
                "name": "Westgrove Primary School",
                "address": "37a Thames Boulevard",
                "suburb": "Werribee",
                "postcode": "3030",
                "distance_km": 0.34,
                "school_type": "Primary",
                "gender": "Mixed",
                "sector": "Government",
                "enrolments": 487,
                "lat": -37.8785,
                "lng": 144.65953,
                "in_catchment": True,
                "catchment_note": "Property is within catchment zone",
                "zone_year": 2026,
            },
            {
                "name": "Werribee North Primary School",
                "address": "120 Old Geelong Road",
                "suburb": "Werribee",
                "postcode": "3030",
                "distance_km": 1.2,
                "school_type": "Primary",
                "gender": "Mixed",
                "sector": "Government",
                "enrolments": 523,
                "lat": -37.8912,
                "lng": 144.6423,
                "in_catchment": False,
                "catchment_note": "Property is outside catchment zone",
                "zone_year": 2026,
            },
        ],
        "secondary": [
            {
                "name": "Werribee Secondary College",
                "address": "Duncans Road",
                "suburb": "Werribee",
                "postcode": "3030",
                "distance_km": 2.1,
                "school_type": "Secondary",
                "gender": "Mixed",
                "sector": "Government",
                "enrolments": 1523,
                "lat": -37.8734,
                "lng": 144.6712,
                "in_catchment": False,
                "catchment_note": "Zone data not found — verify at findmyschool.vic.gov.au",
                "zone_year": None,
            },
        ],
        "total_count": 12,
        "search_radius_km": 3.0,
    }
}
