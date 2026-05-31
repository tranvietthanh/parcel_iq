#!/usr/bin/env python3
"""Test the updated user prompt with enriched data."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "app"))

from app.prompts.user_prompt import build_user_prompt

# Sample raw data with VicPlan enrichments
raw_data = {
    "zoning_code": "GRZ1",
    "zoning_label": "GENERAL RESIDENTIAL ZONE - SCHEDULE 1",
    "lga_name": "WYNDHAM",
    "flood_risk": "NONE",
    "bushfire_risk": "NONE",
    "requires_planning_permit": False,
    "development_plan_required": False,
    "incorporated_plan_applies": False,
    "public_acquisition": False,
    "development_contributions": False,
    "contamination_audit_required": False,
    "airport_corridor": False,
    "heritage_overlay": False,
    "has_design_overlay": False,
    "constraint_score": 0.0,
    "constraint_summary": [
        "This site is zoned GRZ1 (General Residential Zone - Schedule 1)."
    ],
    "overlays": [],  # No overlays for this property
    "overlay_codes": [],
    "nbn": {
        "tech_type": "HFC",
        "service_status": "available",
    },
    "demographics": {
        "lga_code": "27260",
        "lga_name": "Wyndham",
        "latest_year": "2024",
        "latest": {
            "total_population": 337009,
            "population_density_per_sqkm": 621.7,
            "population_growth_pct_yoy": 4.0,
            "established_house_median_price_aud": 660000,
            "house_price_growth_pct_yoy": 0.15,
        },
        "time_series": {
            "2023": {
                "total_population": 324209,
                "population_growth_pct_yoy": 4.74,
                "established_house_median_price_aud": 651000,
            },
            "2024": {
                "total_population": 337009,
                "population_growth_pct_yoy": 4.0,
                "established_house_median_price_aud": 660000,
                "house_price_growth_pct_yoy": 0.15,
            },
        },
        "source": "ABS Data by Region"
    },
}

# Sample with overlays
raw_data_with_overlays = {
    **raw_data,
    "heritage_overlay": True,
    "has_design_overlay": True,
    "constraint_score": 6.5,
    "overlays": [
        {
            "code": "HO544",
            "description": "Heritage Overlay - Schedule 544",
            "severity": 7,
            "family": "heritage",
            "summary": "Heritage Overlay — demolition, alterations, and subdivision require a permit.",
            "detail": "The Heritage Overlay (HO) protects places of cultural heritage significance...",
        },
        {
            "code": "DDO12",
            "description": "Design and Development Overlay - Schedule 12",
            "severity": 5,
            "family": "development",
            "summary": "Design & Development Overlay — height, setback, and design controls apply.",
            "detail": "The Design and Development Overlay (DDO) sets specific design requirements...",
        }
    ],
    "overlay_codes": ["HO544", "DDO12"],
    "constraint_summary": [
        "This site is zoned GRZ1 (General Residential Zone - Schedule 1).",
        "Heritage Overlay (HO544) applies — demolition and external alterations require a permit.",
        "Design controls (DDO12) limit building height and setbacks.",
    ]
}

print("=" * 80)
print("PROMPT PREVIEW (Property with NO overlays)")
print("=" * 80)
prompt1 = build_user_prompt("7 St Lawrence Cl, Werribee VIC 3030", raw_data)
# Show just the State Planning API section
lines = prompt1.split("\n")
start_idx = next(i for i, line in enumerate(lines) if "State Planning API" in line)
end_idx = next(i for i, line in enumerate(lines[start_idx:], start_idx) if line.startswith("### NBN"))
print("\n".join(lines[start_idx:end_idx]))

print("\n\n")
print("=" * 80)
print("PROMPT PREVIEW (Property WITH overlays)")
print("=" * 80)
prompt2 = build_user_prompt("123 Heritage St, Melbourne VIC 3000", raw_data_with_overlays)
lines = prompt2.split("\n")
start_idx = next(i for i, line in enumerate(lines) if "State Planning API" in line)
end_idx = next(i for i, line in enumerate(lines[start_idx:], start_idx) if line.startswith("### NBN"))
print("\n".join(lines[start_idx:end_idx]))
