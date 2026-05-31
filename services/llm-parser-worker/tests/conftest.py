"""Shared test fixtures for the LLM parser worker test suite."""

from __future__ import annotations

import json

import pytest

from app.prompts.user_prompt import _ROI_DISCLAIMER


# ── Valid LlmOutput JSON ────────────────────────────────────────────────────

VALID_LLM_OUTPUT = {
    "zoning_and_planning": {
        "zoning_code": "GRZ1",
        "zoning_label": "General Residential Zone - Schedule 1",
        "lga_name": "Boroondara",
        "epi_name": None,
        "epi_type": None,
        "overlays": [
            {
                "code": "SBO2",
                "severity": 6,
                "family": "flooding",
                "summary": "Special Building Overlay - Schedule 2"
            },
            {
                "code": "HO123",
                "severity": 7,
                "family": "heritage",
                "summary": "Heritage Overlay - Schedule 123"
            }
        ],
        "heritage_area": True,
        "subdivision_potential": "Two-lot subdivision likely feasible given lot size (800sqm) and GRZ1 zoning.",
        "conflict_note": None,
        "confidence_score": 0.92,
    },
    "risk_factors": {
        "flood": {
            "risk": "LOW",
            "detail": "Property is in a Special Building Overlay area with minor overland flow risk.",
            "confidence_score": 0.85,
        },
        "bushfire": {
            "risk": "NONE",
            "detail": "Not within a designated bushfire-prone area.",
            "confidence_score": 0.95,
        },
        "crime_density": {
            "rating": "BELOW_AVERAGE",
            "detail": "ABS data indicates crime rates below the LGA average.",
            "confidence_score": 0.78,
        },
    },
    "connectivity": {
        "nbn_tech_type": "FTTP",
        "nbn_service_status": "available",
        "nbn_tech_change_status": None,
        "nbn_target_eligibility_quarter": None,
        "confidence_score": 0.95,
    },
    "infrastructure": [
        {
            "type": "TRANSPORT",
            "description": "Glenferrie Road tram stop (Route 16) — 200m walk",
            "distance_km": 0.2,
            "expected_completion_year": None,
            "source_url": None,
            "confidence_score": 0.9,
        },
        {
            "type": "EDUCATION",
            "description": "Hawthorn Primary School — within catchment",
            "distance_km": 0.8,
            "expected_completion_year": None,
            "source_url": None,
            "confidence_score": 0.88,
        },
    ],
    "roi_scenarios": {
        "disclaimer": _ROI_DISCLAIMER,
        "scenarios": [
            {
                "label": "Conservative",
                "assumptions": {
                    "interest_rate_percent": 7.0,
                    "weekly_rent_aud": 550,
                    "vacancy_rate_percent": 4.0,
                    "maintenance_percent": 1.5,
                    "council_rates_annual_aud": 2200,
                    "insurance_annual_aud": 1800,
                },
                "gross_yield_percent": 3.2,
                "net_yield_percent": 1.8,
                "annual_cash_flow_aud": -4500,
            },
            {
                "label": "Base",
                "assumptions": {
                    "interest_rate_percent": 6.0,
                    "weekly_rent_aud": 600,
                    "vacancy_rate_percent": 3.0,
                    "maintenance_percent": 1.0,
                    "council_rates_annual_aud": 2200,
                    "insurance_annual_aud": 1800,
                },
                "gross_yield_percent": 3.5,
                "net_yield_percent": 2.3,
                "annual_cash_flow_aud": -1200,
            },
            {
                "label": "Optimistic",
                "assumptions": {
                    "interest_rate_percent": 5.0,
                    "weekly_rent_aud": 650,
                    "vacancy_rate_percent": 2.0,
                    "maintenance_percent": 0.8,
                    "council_rates_annual_aud": 2200,
                    "insurance_annual_aud": 1800,
                },
                "gross_yield_percent": 3.8,
                "net_yield_percent": 2.9,
                "annual_cash_flow_aud": 2400,
            },
        ],
    },
    "demographic_snapshot": {
        "suburb": "Hawthorn",
        "median_household_weekly_income_aud": 1827,
        "owner_occupier_percent": 52.3,
        "median_age": 34,
        "primary_household_type": "Couples without children",
        "source": "ABS Census 2021",
        "confidence_score": 0.91,
    },
}


def valid_llm_json() -> str:
    """Return the valid LLM output as a JSON string."""
    return json.dumps(VALID_LLM_OUTPUT)


# ── Low confidence variant ──────────────────────────────────────────────────

LOW_CONFIDENCE_OUTPUT = {
    **VALID_LLM_OUTPUT,
    "zoning_and_planning": {
        **VALID_LLM_OUTPUT["zoning_and_planning"],
        "confidence_score": 0.45,  # Below 0.6 threshold
    },
}


def low_confidence_llm_json() -> str:
    """Return LLM output with a low-confidence field."""
    return json.dumps(LOW_CONFIDENCE_OUTPUT)


# ── Raw scraped data fixture ────────────────────────────────────────────────

SAMPLE_RAW_DATA = {
    "zoning_code": "GRZ1",
    "zoning_label": "General Residential Zone - Schedule 1",
    "lga_name": "Boroondara",
    "epi_name": None,
    "epi_type": None,
    "heritage_area": True,
    "overlay_codes": ["SBO2", "HO123"],
    "overlays": [
        {
            "code": "SBO2",
            "description": "Special Building Overlay - Schedule 2",
            "family": "flood",
            "severity": 4,
        },
        {
            "code": "HO123",
            "description": "Heritage Overlay - Schedule 123",
            "family": "heritage",
            "severity": 7,
        },
    ],
    "flood_risk": "LOW",
    "bushfire_risk": "NONE",
    "nbn": {
        "tech_type": "FTTP",
        "service_status": "available",
        "tech_change_status": None,
        "target_eligibility_quarter": None,
    },
    "demographics": {
        "suburb": "Hawthorn",
        "median_household_weekly_income": 1827,
        "owner_occupier_percent": 52.3,
        "median_age": 34,
    },
    "council_planning_applications_text": "DA-2024-0456: Two-lot subdivision at 12 Example St. Status: Approved.",
    "council_meeting_minutes_text": "Item 8.3: Council noted the heritage review for the Glenferrie precinct.",
}


SAMPLE_ADDRESS = "12 Example Street, Hawthorn VIC 3122"


@pytest.fixture
def valid_output_json() -> str:
    """Valid LlmOutput JSON string."""
    return valid_llm_json()


@pytest.fixture
def low_confidence_json() -> str:
    """LlmOutput JSON with low confidence fields."""
    return low_confidence_llm_json()


@pytest.fixture
def sample_raw_data() -> dict:
    """Sample raw scraped data dict."""
    return SAMPLE_RAW_DATA.copy()
