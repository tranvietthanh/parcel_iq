"""Pydantic schemas for search endpoints."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class SearchParams(BaseModel):
    """Query parameters for ``GET /api/search``."""

    q: str | None = None
    bbox: str | None = None  # "minLng,minLat,maxLng,maxLat"
    limit: int = Field(default=100, le=500, ge=1)

    @model_validator(mode="after")
    def require_q_or_bbox(self) -> "SearchParams":
        if not self.q and not self.bbox:
            raise ValueError("Either 'q' or 'bbox' is required.")
        return self


# ── Text-search response ─────────────────────────────────────────────────────


class SearchSuggestion(BaseModel):
    type: str  # ADDRESS, SCHOOL, LGA, SUBURB
    label: str
    property_id: UUID | None = None
    zone_id: UUID | None = None
    coordinates: list[float] | None = None  # [lng, lat]
    bbox: list[float] | None = None  # [minLng, minLat, maxLng, maxLat]
    slug: str | None = None
    zone_state: str | None = None


class TextSearchResponse(BaseModel):
    suggestions: list[SearchSuggestion]


# ── Bbox (GeoJSON) response ──────────────────────────────────────────────────


class FeatureProperties(BaseModel):
    id: str
    address: str
    report_status: str | None = None
    estimated_value: int | None = None
    slug: str | None = None


class Feature(BaseModel):
    type: str = "Feature"
    geometry: dict  # GeoJSON Point
    properties: FeatureProperties


class FeatureCollection(BaseModel):
    type: str = "FeatureCollection"
    features: list[Feature]


# ── Zone polygon response ────────────────────────────────────────────────────


class ZoneFeature(BaseModel):
    type: str = "Feature"
    geometry: dict  # GeoJSON MultiPolygon
    properties: dict
