"""Search endpoints — bbox map search + text autocomplete.

GET /api/search      — bbox (GeoJSON FC) or text (suggestions)
GET /api/search/zones — zone polygon GeoJSON by zone_id
"""

from __future__ import annotations

import json
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.core.rate_limit import limiter
from app.dependencies import get_db
from app.middleware.turnstile import verify_turnstile
from app.schemas.search import (
    Feature,
    FeatureCollection,
    FeatureProperties,
    SearchSuggestion,
    TextSearchResponse,
    ZoneFeature,
)

router = APIRouter(tags=["search"])

# ── SQL ───────────────────────────────────────────────────────────────────────

BBOX_QUERY = """
    SELECT p.id::text, p.address_string,
           ST_AsGeoJSON(p.geom)::json AS geometry,
           p.estimated_value, pr.status AS report_status,
           p.slug
    FROM properties p
    LEFT JOIN property_reports pr ON pr.property_id = p.id
    WHERE p.geom && ST_MakeEnvelope($1, $2, $3, $4, 4326)
    LIMIT $5
"""

ZONE_BBOX_QUERY = """
    SELECT p.id::text, p.address_string,
           ST_AsGeoJSON(p.geom)::json AS geometry,
           p.estimated_value, pr.status AS report_status,
           p.slug
    FROM properties p
    LEFT JOIN property_reports pr ON pr.property_id = p.id
    WHERE p.geom && ST_MakeEnvelope($1, $2, $3, $4, 4326)
      AND ST_Within(p.geom, (SELECT geom FROM spatial_zones WHERE id = $6))
    LIMIT $5
"""

TEXT_SEARCH_QUERY = """
    (
        SELECT 'ADDRESS' AS type, p.address_string AS label,
               p.id::text AS property_id, NULL::text AS zone_id,
               ST_X(p.geom) AS lng, ST_Y(p.geom) AS lat,
               NULL::json AS bbox,
               p.slug AS slug,
               NULL::text AS zone_state
        FROM properties p
        WHERE (
            p.address_tokens @@ plainto_tsquery('simple', $1)
            OR p.address_string ILIKE '%' || $1 || '%'
        )
        LIMIT $2
    )
    UNION ALL
    (
        SELECT sz.zone_type AS type, sz.name || ' — ' || sz.state AS label,
               NULL::text AS property_id, sz.id::text AS zone_id,
               NULL::numeric AS lng, NULL::numeric AS lat,
               ST_AsGeoJSON(ST_Envelope(sz.geom))::json AS bbox,
               sz.slug AS slug,
               sz.state AS zone_state
        FROM spatial_zones sz
        WHERE sz.name ILIKE '%' || $1 || '%'
        LIMIT $2
    )
"""

ZONE_POLYGON_QUERY = """
    SELECT zone_type, name, state,
           ST_AsGeoJSON(geom)::json AS geometry,
           ST_AsGeoJSON(ST_Envelope(geom))::json AS bbox,
           metadata
    FROM spatial_zones
    WHERE id = $1
"""


# ── Routes ────────────────────────────────────────────────────────────────────


@router.get("")
@limiter.limit("200/hour")
async def search(
    request: Request,
    q: str | None = Query(default=None),
    bbox: str | None = Query(default=None),
    zone_id: UUID | None = Query(default=None),
    limit: int = Query(default=100, le=500, ge=1),
    _turnstile: None = Depends(verify_turnstile),
    db: asyncpg.Connection = Depends(get_db),
) -> FeatureCollection | TextSearchResponse:
    """Search properties by bounding box or text query."""
    if not q and not bbox:
        raise HTTPException(status_code=400, detail="Either 'q' or 'bbox' is required.")

    if bbox:
        return await _bbox_search(db, bbox, limit, zone_id=zone_id)
    return await _text_search(db, q, limit)  # type: ignore[arg-type]


@router.get("/zones")
async def search_zones(
    zone_id: UUID = Query(...),
    db: asyncpg.Connection = Depends(get_db),
) -> ZoneFeature:
    """Return GeoJSON polygon for a spatial zone."""
    row = await db.fetchrow(ZONE_POLYGON_QUERY, zone_id)
    if not row:
        raise HTTPException(status_code=404, detail="Zone not found.")

    geometry_val = row["geometry"] if isinstance(row["geometry"], dict) else json.loads(row["geometry"])
    
    bbox_val = None
    bbox_val = _extract_bbox(row["bbox"])

    metadata_val = row["metadata"] or {}
    if isinstance(metadata_val, str):
        metadata_val = json.loads(metadata_val)

    return ZoneFeature(
        geometry=geometry_val,
        properties={
            "zone_type": row["zone_type"],
            "name": row["name"],
            "state": row["state"],
            "bbox": bbox_val,
            **metadata_val,
        },
    )


@router.get("/zones/slug/{slug}")
async def search_zones_by_slug(
    slug: str,
    db: asyncpg.Connection = Depends(get_db),
) -> ZoneFeature:
    """Return GeoJSON polygon for a spatial zone by its slug."""
    row = await db.fetchrow(
        """
        SELECT id, zone_type, name, state,
               ST_AsGeoJSON(geom)::json AS geometry,
               ST_AsGeoJSON(ST_Envelope(geom))::json AS bbox,
               metadata
        FROM spatial_zones
        WHERE slug = $1
        """,
        slug
    )
    if not row:
        raise HTTPException(status_code=404, detail="Zone not found.")

    geometry_val = row["geometry"] if isinstance(row["geometry"], dict) else json.loads(row["geometry"])

    bbox_val = None
    bbox_val = _extract_bbox(row["bbox"])

    metadata_val = row["metadata"] or {}
    if isinstance(metadata_val, str):
        metadata_val = json.loads(metadata_val)

    return ZoneFeature(
        geometry=geometry_val,
        properties={
            "id": str(row["id"]),
            "zone_type": row["zone_type"],
            "name": row["name"],
            "state": row["state"],
            "bbox": bbox_val,
            **metadata_val,
        },
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_bbox(envelope_geojson) -> list[float] | None:
    if not envelope_geojson:
        return None
    d = envelope_geojson if isinstance(envelope_geojson, dict) else json.loads(envelope_geojson)
    coords = d.get("coordinates", [[]])[0]
    if len(coords) >= 4:
        lngs = [c[0] for c in coords]
        lats = [c[1] for c in coords]
        return [min(lngs), min(lats), max(lngs), max(lats)]
    return None


async def _bbox_search(
    db: asyncpg.Connection, bbox: str, limit: int, *, zone_id: UUID | None = None,
) -> FeatureCollection:
    parts = bbox.split(",")
    if len(parts) != 4:
        raise HTTPException(status_code=400, detail="bbox must be 'minLng,minLat,maxLng,maxLat'.")
    try:
        min_lng, min_lat, max_lng, max_lat = (float(p) for p in parts)
    except ValueError:
        raise HTTPException(status_code=400, detail="bbox values must be numeric.")

    if not (-180 <= min_lng < max_lng <= 180):
        raise HTTPException(
            status_code=400,
            detail="Longitude values must satisfy -180 <= minLng < maxLng <= 180.",
        )
    if not (-90 <= min_lat < max_lat <= 90):
        raise HTTPException(
            status_code=400,
            detail="Latitude values must satisfy -90 <= minLat < maxLat <= 90.",
        )

    if zone_id:
        rows = await db.fetch(ZONE_BBOX_QUERY, min_lng, min_lat, max_lng, max_lat, limit, zone_id)
    else:
        rows = await db.fetch(BBOX_QUERY, min_lng, min_lat, max_lng, max_lat, limit)

    features = [
        Feature(
            geometry=row["geometry"] if isinstance(row["geometry"], dict) else json.loads(row["geometry"]),
            properties=FeatureProperties(
                id=row["id"],
                address=row["address_string"],
                report_status=row["report_status"],
                estimated_value=row["estimated_value"],
                slug=row["slug"],
            ),
        )
        for row in rows
    ]
    return FeatureCollection(features=features)


async def _text_search(db: asyncpg.Connection, q: str, limit: int) -> TextSearchResponse:
    rows = await db.fetch(TEXT_SEARCH_QUERY, q, limit)

    suggestions = []
    for row in rows:
        coords = None
        if row["lng"] is not None and row["lat"] is not None:
            coords = [row["lng"], row["lat"]]

        bbox_val = None
        bbox_val = _extract_bbox(row["bbox"])

        suggestions.append(
            SearchSuggestion(
                type=row["type"],
                label=row["label"],
                property_id=row["property_id"],
                zone_id=row["zone_id"],
                coordinates=coords,
                bbox=bbox_val,
                slug=row["slug"],
                zone_state=row["zone_state"],
            )
        )
    return TextSearchResponse(suggestions=suggestions)
