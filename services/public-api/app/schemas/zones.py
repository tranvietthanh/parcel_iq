"""Pydantic schemas for zone endpoints."""

from __future__ import annotations

from uuid import UUID
from pydantic import BaseModel, Field


class CensusStats(BaseModel):
    population: int | None = None
    male_count: int | None = None
    female_count: int | None = None
    median_age: int | None = None
    median_weekly_household_income: int | None = None
    median_total_family_income: int | None = None
    median_total_personal_income: int | None = None
    median_weekly_rent: int | None = None
    median_monthly_mortgage: int | None = None
    average_household_size: float | None = None
    average_persons_per_bedroom: float | None = None
    renting_pct: float | None = None
    born_overseas_pct: float | None = None
    born_in_australia_pct: float | None = None
    indigenous_pct: float | None = None
    language_english_only_pct: float | None = None
    age_distribution: list[dict[str, str | int | float]] = Field(default_factory=list)
    top_birth_countries: list[dict[str, str | int | float]] = Field(default_factory=list)
    income_distribution: list[dict[str, str | int | float]] = Field(default_factory=list)
    labour_force_distribution: list[dict[str, str | int | float]] = Field(default_factory=list)


class NearbySchool(BaseModel):
    name: str
    school_type: str | None = None
    sector: str | None = None
    enrolments: int | None = None
    distance_km: float | None = None
    catchment_slug: str | None = None
    catchment_state: str | None = None


class PropertyStats(BaseModel):
    total_count: int
    with_reports: int
    median_estimated_value: int | None = None
    median_land_size_sqm: float | None = None


class ZoneInfo(BaseModel):
    id: UUID
    name: str
    state: str
    zone_type: str
    slug: str


class ZoneSummary(BaseModel):
    zone: ZoneInfo
    property_stats: PropertyStats
    nearby_schools: list[NearbySchool] = Field(default_factory=list)
    census_stats: CensusStats | None = None
