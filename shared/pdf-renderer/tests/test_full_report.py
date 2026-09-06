from __future__ import annotations

import io
from typing import Any

import pypdf
import pytest

from pdf_renderer.full_report import generate_report_pdf_bytes
from pdf_renderer.storage import build_report_pdf_object_key


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


@pytest.fixture
def sample_report_data() -> dict[str, Any]:
    return {
        "zoning_and_planning": {
            "zoning_code": "GRZ2",
            "zoning_label": "General Residential Zone - Schedule 2",
            "lga_name": "City of Melbourne",
            "heritage_area": False,
            "subdivision_potential": "Subject to Council Approval",
            "epi_name": "Melbourne Planning Scheme",
            "epi_type": "Standard Instrument LEP",
            "confidence_score": 0.95,
            "conflict_note": "Conflict between GRZ2 height limit and DDO overlay requirements.",
            "overlays": [
                {
                    "code": "DDO1",
                    "family": "Design and Development",
                    "summary": "Building height must not exceed 11 metres.",
                    "severity": 6,
                }
            ],
        },
        "risk_factors": {
            "flood": {
                "risk": "LOW",
                "detail": "1 in 100 year flood planning level applies to rear boundary.",
            },
            "bushfire": {
                "risk": "MEDIUM",
                "detail": "Designated Bushfire Prone Area requiring BAL-12.5 assessment.",
            },
            "crime_density": {
                "rating": "BELOW_AVERAGE",
                "detail": "Property offences 18% lower than statewide LGA average.",
            },
        },
        "connectivity": {
            "nbn_tech_type": "FTTP",
            "nbn_service_status": "Available",
            "nbn_tech_change_status": "Not planned",
            "nbn_target_eligibility_quarter": "Q1 2025",
        },
        "education": {
            "nearby_schools_summary": "Strong educational precinct within 1.5km.",
            "primary_schools": [
                {
                    "name": "Carlton Gardens Primary School",
                    "distance_km": 0.45,
                    "in_catchment": True,
                    "enrolments": 380,
                }
            ],
            "secondary_schools": [
                {
                    "name": "University High School",
                    "distance_km": 1.1,
                    "in_catchment": True,
                    "enrolments": 1450,
                }
            ],
        },
        "infrastructure": [
            {
                "type": "TRANSPORT",
                "description": "Suburban Rail Loop East Station construction",
                "distance_km": 0.75,
                "expected_completion_year": 2035,
                "source_url": "https://bigbuild.vic.gov.au/projects/suburban-rail-loop",
            },
            {
                "type": "HEALTH",
                "description": "Royal Melbourne Hospital Redevelopment",
                "distance_km": 1.4,
                "expected_completion_year": 2028,
            },
        ],
        "narrative": {
            "executive_summary": "High-yield inner-suburb property positioned for long-term growth.",
            "zoning_summary": "Favorable planning controls with dual-occupancy development potential.",
        },
        "demographic_snapshot": {
            "total_population": 42500,
            "established_house_median_price_aud": 1250000,
        },
        "demographic_trend_analysis": {
            "overall_investment_signal": "POSITIVE",
            "overall_investment_signal_note": "Consistently accelerating capital growth with low vacancy.",
            "population_momentum": "ACCELERATING",
        },
        "roi_scenarios": {
            "disclaimer": "Projections are indicative only and do not constitute financial advice.",
            "scenarios": [
                {
                    "label": "Base",
                    "gross_yield_percent": 4.8,
                    "net_yield_percent": 3.9,
                    "annual_cash_flow_aud": 6500,
                    "assumptions": {
                        "weekly_rent_aud": 650,
                        "interest_rate_percent": 6.25,
                    },
                }
            ],
        },
    }


def test_full_report_renders_enriched_sections(sample_report_data: dict[str, Any]) -> None:
    """Full variant renders Infrastructure, risk details, conflict notes, and EPI Type."""
    pdf_bytes = generate_report_pdf_bytes(
        data=sample_report_data,
        address="100 Swanston St, Melbourne VIC 3000",
        variant="full",
    )
    assert len(pdf_bytes) > 0

    text = _extract_pdf_text(pdf_bytes)

    # 1. Infrastructure section and items present
    assert "INFRASTRUCTURE" in text.upper()
    assert "Suburban Rail Loop East Station" in text
    assert "Royal Melbourne Hospital" in text
    assert "2035" in text

    # 2. Risk detail commentary present in full report
    assert "1 in 100 year flood planning level" in text
    assert "Designated Bushfire Prone Area" in text
    assert "Property offences 18% lower" in text

    # 3. Zoning conflict note present in full report
    assert "Conflict between GRZ2 height limit" in text

    # 4. EPI Type present
    assert "EPI Type" in text
    assert "Standard Instrument LEP" in text


def test_lite_report_omits_analyst_commentary(sample_report_data: dict[str, Any]) -> None:
    """Lite variant strictly suppresses analyst commentary (risk details, conflict notes, infrastructure)."""
    pdf_bytes = generate_report_pdf_bytes(
        data=sample_report_data,
        address="100 Swanston St, Melbourne VIC 3000",
        variant="lite",
    )
    assert len(pdf_bytes) > 0

    text = _extract_pdf_text(pdf_bytes)

    # 1. Infrastructure section MUST NOT appear in lite report
    assert "INFRASTRUCTURE" not in text.upper()
    assert "Suburban Rail Loop East" not in text

    # 2. Risk details MUST NOT appear in lite report
    assert "1 in 100 year flood planning level" not in text
    assert "Designated Bushfire Prone Area" not in text
    assert "Property offences 18% lower" not in text

    # But standard risk ratings should still appear
    assert "Flood Risk" in text
    assert "LOW" in text

    # 3. Zoning conflict note MUST NOT appear in lite report
    assert "Conflict between GRZ2 height limit" not in text

    # 4. EPI Type (structured metadata) DOES appear in both variants
    assert "EPI Type" in text
    assert "Standard Instrument LEP" in text


def test_llm_markup_escaping() -> None:
    """LLM-authored text containing unescaped &, <, >, and unclosed tags does not crash generation."""
    malformed_data = {
        "zoning_and_planning": {
            "zoning_code": "GRZ2 & B4",
            "zoning_label": "Mixed Use <Commercial & Residential>",
            "conflict_note": "Unclosed <b>bold tag & <custom_element> inside note",
            "epi_name": "Planning Scheme & Assessment Guide",
            "epi_type": "Regional & Local Policy",
            "overlays": [
                {
                    "code": "DDO & EAO",
                    "family": "Environmental & Design",
                    "summary": "Height < 12m & setbacks > 5m required",
                    "severity": 5,
                }
            ],
        },
        "risk_factors": {
            "flood": {
                "risk": "HIGH",
                "detail": "Overland flow path > 0.5m & unclosed <tag> detail",
            },
            "bushfire": {"risk": "LOW", "detail": "BAL < 12.5 & cleared boundary"},
            "crime_density": {"rating": "AVERAGE", "detail": "Trend & statistics <normal>"},
        },
        "education": {
            "nearby_schools_summary": "Primary & Secondary schools <within 2km>",
            "primary_schools": [
                {
                    "name": "St. Mary's & St. John's <Primary>",
                    "distance_km": 0.8,
                    "in_catchment": True,
                }
            ],
        },
        "infrastructure": [
            {
                "type": "TRANSPORT & LOGISTICS",
                "description": "Rail <Stage 2> & Bus Interchange with > 10 routes",
                "distance_km": 1.2,
                "expected_completion_year": 2030,
            }
        ],
        "narrative": {
            "executive_summary": "Strategic location & strong fundamentals <unclosed tag",
        },
        "demographic_trend_analysis": {
            "overall_investment_signal": "POSITIVE",
            "overall_investment_signal_note": "High demand & low supply: rent > mortgage",
        },
        "roi_scenarios": {
            "disclaimer": "General advice & disclaimer <not financial advice>",
            "scenarios": [],
        },
    }

    # Should not raise XML parsing or ReportLab LayoutError
    full_pdf = generate_report_pdf_bytes(malformed_data, variant="full")
    assert len(full_pdf) > 0
    full_text = _extract_pdf_text(full_pdf)
    assert "Rail <Stage 2> & Bus Interchange" in full_text or "Rail" in full_text

    lite_pdf = generate_report_pdf_bytes(malformed_data, variant="lite")
    assert len(lite_pdf) > 0


def test_empty_infrastructure_renders_placeholder() -> None:
    """Empty infrastructure list renders clean placeholder without crashing."""
    data = {
        "zoning_and_planning": {"zoning_code": "IN1Z"},
        "risk_factors": {},
        "infrastructure": [],
    }
    pdf_bytes = generate_report_pdf_bytes(data, variant="full")
    assert len(pdf_bytes) > 0
    text = _extract_pdf_text(pdf_bytes)
    assert "No nearby infrastructure data available." in text


def test_storage_cache_key_versioning() -> None:
    """Cache keys contain the v2 version tag."""
    assert build_report_pdf_object_key("abc-123", "full") == "reports/abc-123.v2.pdf"
    assert build_report_pdf_object_key("abc-123", "lite") == "reports/abc-123.lite.v2.pdf"
    assert build_report_pdf_object_key("abc-123") == "reports/abc-123.v2.pdf"


def test_null_and_malformed_items_handling() -> None:
    """Null fields and non-dict items in infrastructure and education do not cause AttributeError or crash."""
    null_data = {
        "zoning_and_planning": {
            "zoning_code": None,
            "zoning_label": None,
            "conflict_note": None,
            "overlays": [None, "invalid-string", {"code": None, "family": None, "summary": None, "severity": None}],
        },
        "risk_factors": {
            "flood": {"risk": None, "detail": None},
            "bushfire": None,
        },
        "education": {
            "nearby_schools_summary": None,
            "primary_schools": [None, {"name": None, "distance_km": None, "in_catchment": None, "enrolments": None}],
            "secondary_schools": ["invalid", {"name": "Test High", "distance_km": 1.5, "in_catchment": True}],
        },
        "infrastructure": [
            None,
            "not-a-dict",
            {"type": None, "description": None, "distance_km": None, "expected_completion_year": None},
            {"type": "HOSPITAL", "description": "New Regional Clinic", "distance_km": 2.5, "expected_completion_year": 2028},
        ],
        "demographic_trend_analysis": {
            "overall_investment_signal": None,
            "overall_investment_signal_note": None,
        },
        "roi_scenarios": {
            "disclaimer": None,
            "scenarios": [],
        },
    }

    full_pdf = generate_report_pdf_bytes(null_data, address=None, variant="full")
    assert len(full_pdf) > 0
    lite_pdf = generate_report_pdf_bytes(null_data, address=None, variant="lite")
    assert len(lite_pdf) > 0

