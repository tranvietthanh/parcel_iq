"""Pydantic v2 model for the structured LLM output.

Enforces the JSON schema expected from the LLM API (OpenAI).
Used by the LLM Parser Worker (writes) and Public API (reads + serves).

Schema source: docs/06-llm-parser-worker.md §7
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class RiskEntry(BaseModel):
    risk: Literal["NONE", "LOW", "MEDIUM", "HIGH"] | None = None
    detail: str | None = None
    confidence_score: float = Field(ge=0.0, le=1.0)


class CrimeDensityEntry(BaseModel):
    rating: Literal["BELOW_AVERAGE", "AVERAGE", "ABOVE_AVERAGE"] | None = None
    detail: str | None = None
    confidence_score: float = Field(ge=0.0, le=1.0)


class OverlayEntry(BaseModel):
    """Enriched overlay data with severity scoring and categorization."""
    code: str
    severity: int | None = Field(None, ge=1, le=10)
    family: str | None = None
    summary: str | None = None


class ZoningAndPlanning(BaseModel):
    zoning_code: str | None = None
    zoning_label: str | None = None
    lga_name: str | None = None
    epi_name: str | None = None
    epi_type: str | None = None
    overlays: list[OverlayEntry] = Field(default_factory=list)
    heritage_area: bool | None = None
    subdivision_potential: str | None = None
    conflict_note: str | None = None
    confidence_score: float = Field(ge=0.0, le=1.0)


class RiskFactors(BaseModel):
    flood: RiskEntry
    bushfire: RiskEntry
    crime_density: CrimeDensityEntry


class Connectivity(BaseModel):
    nbn_tech_type: Literal[
        "FTTP", "HFC", "FTTN", "FTTB", "FTTC", "WIRELESS", "SATELLITE"
    ] | None = None
    nbn_service_status: str | None = None
    nbn_tech_change_status: str | None = None
    nbn_target_eligibility_quarter: str | None = None
    confidence_score: float = Field(ge=0.0, le=1.0)


class InfrastructureItem(BaseModel):
    type: Literal["TRANSPORT", "HEALTH", "EDUCATION", "COMMERCIAL", "OTHER"]
    description: str
    distance_km: float | None = None
    expected_completion_year: int | None = None
    source_url: str | None = None
    confidence_score: float = Field(ge=0.0, le=1.0)


class ScenarioAssumptions(BaseModel):
    interest_rate_percent: float
    weekly_rent_aud: int
    vacancy_rate_percent: float
    maintenance_percent: float
    council_rates_annual_aud: int
    insurance_annual_aud: int


class RoiScenario(BaseModel):
    label: Literal["Conservative", "Base", "Optimistic"]
    assumptions: ScenarioAssumptions
    gross_yield_percent: float
    net_yield_percent: float
    annual_cash_flow_aud: int


class RoiScenarios(BaseModel):
    disclaimer: str
    scenarios: list[RoiScenario]

    @model_validator(mode="after")
    def disclaimer_must_be_present(self):
        if not self.disclaimer or len(self.disclaimer) < 10:
            raise ValueError("ROI disclaimer is required and cannot be empty.")
        return self


class DemographicSnapshot(BaseModel):
    suburb: str | None = None
    lga_name: str | None = None
    reference_year: int | None = None
    total_population: int | None = None
    population_density_per_sqkm: float | None = None
    population_growth_pct_yoy: float | None = None
    population_cagr_5yr_pct: float | None = None
    median_age: float | None = None
    primary_household_type: str | None = None
    total_fertility_rate: float | None = None
    children_enrolled_preschool: int | None = None
    net_internal_migration: int | None = None
    net_overseas_migration: int | None = None
    overseas_migration_arrivals: int | None = None
    dominant_migration_driver: Literal["OVERSEAS", "INTERNAL", "BALANCED"] | None = None
    total_businesses: int | None = None
    business_count_growth_pct_yoy: float | None = None
    net_business_entries: int | None = None
    established_house_median_price_aud: int | None = None
    house_price_growth_pct_yoy: float | None = None
    house_price_cagr_5yr_pct: float | None = None
    attached_dwelling_median_price_aud: int | None = None
    established_house_transfers_count: int | None = None
    attached_dwelling_transfers_count: int | None = None
    total_dwelling_approvals: int | None = None
    dwelling_approvals_growth_pct_yoy: float | None = None
    private_house_approvals: int | None = None
    total_building_approvals_value_aud_millions: float | None = None
    solar_panel_installations: int | None = None
    median_household_weekly_income_aud: int | None = None
    owner_occupier_percent: float | None = None
    dva_age_pension_recipients: int | None = None
    dva_service_pension_recipients: int | None = None
    source: str | None = None
    confidence_score: float = Field(ge=0.0, le=1.0)


class DemographicTrendAnalysis(BaseModel):
    population_momentum: Literal["ACCELERATING", "STABLE", "DECELERATING"] | None = None
    population_momentum_note: str | None = None
    migration_trend: Literal["STRENGTHENING", "STABLE", "WEAKENING"] | None = None
    migration_trend_note: str | None = None
    housing_supply_pressure: Literal["UNDERSUPPLY", "BALANCED", "OVERSUPPLY"] | None = None
    housing_supply_pressure_note: str | None = None
    price_growth_trend: Literal["ACCELERATING", "STABLE", "DECELERATING", "NEGATIVE"] | None = None
    price_growth_trend_note: str | None = None
    business_health_trend: Literal["IMPROVING", "STABLE", "DETERIORATING"] | None = None
    business_health_trend_note: str | None = None
    rental_demand_outlook: Literal["STRONG", "MODERATE", "WEAK"] | None = None
    rental_demand_outlook_note: str | None = None
    overall_investment_signal: Literal["POSITIVE", "NEUTRAL", "CAUTIONARY"] | None = None
    overall_investment_signal_note: str | None = None
    confidence_score: float = Field(ge=0.0, le=1.0)


class Narrative(BaseModel):
    executive_summary: str | None = None
    zoning_summary: str | None = None
    demographic_story: str | None = None
    market_momentum: str | None = None
    rental_case: str | None = None
    risk_summary: str | None = None
    investor_context: str | None = None


class SchoolEntry(BaseModel):
    """School information from nearby schools enrichment."""
    name: str
    distance_km: float
    in_catchment: bool
    enrolments: int | None = None
    sector: str | None = None


class Education(BaseModel):
    """Education section with nearby schools analysis."""
    nearby_schools_summary: str | None = None
    primary_schools: list[SchoolEntry] = Field(default_factory=list)
    secondary_schools: list[SchoolEntry] = Field(default_factory=list)
    confidence_score: float = Field(ge=0.0, le=1.0)


class LlmOutput(BaseModel):
    """Pydantic v2 model enforcing the exact structure expected from Gemini.

    model_config strict=True rejects any extra keys the LLM might add.
    """

    model_config = {"strict": True, "extra": "forbid"}

    zoning_and_planning: ZoningAndPlanning
    risk_factors: RiskFactors
    connectivity: Connectivity
    infrastructure: list[InfrastructureItem]
    roi_scenarios: RoiScenarios
    demographic_snapshot: DemographicSnapshot
    demographic_trend_analysis: DemographicTrendAnalysis | None = None
    education: Education | None = None
    narrative: Narrative | None = None
