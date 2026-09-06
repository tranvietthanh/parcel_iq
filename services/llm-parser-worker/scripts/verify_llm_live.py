"""Manual live call sanity check.

Runs a single prompt against the configured provider and validates basic JSON
structure.
This is intentionally not part of pytest to avoid quota usage in CI.
"""

from __future__ import annotations

import argparse
import json
import os

from parceliq_types.llm_output import LlmOutput

from app.config import settings
from app.prompts.system_prompt import SYSTEM_PROMPT
from app.prompts.user_prompt import build_user_prompt
from app.services.providers import get_llm_client

SAMPLE_ADDRESS = "12 Example Street, Hawthorn VIC 3122"
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
    "council_planning_applications_text": (
        "DA-2024-0456: Two-lot subdivision at 12 Example St. Status: Approved."
    ),
    "council_meeting_minutes_text": (
        "Item 8.3: Council noted the heritage review for the Glenferrie precinct."
    ),
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Live sanity check for LLM provider")
    parser.add_argument(
        "--provider",
        choices=["openai", "anthropic", "google"],
        default=settings.LLM_PROVIDER,
        help="LLM provider to test (default: configured LLM_PROVIDER)",
    )
    args = parser.parse_args()
    provider = args.provider

    if provider == "openai":
        if not os.getenv("OPENAI_API_KEY") and not settings.OPENAI_API_KEY:
            print("OPENAI_API_KEY is not set. Export it before running this script.")
            return 2
    elif provider == "anthropic":
        if not os.getenv("ANTHROPIC_API_KEY") and not settings.ANTHROPIC_API_KEY:
            print("ANTHROPIC_API_KEY is not set. Export it before running this script.")
            return 2
    elif provider == "google":
        if not os.getenv("GOOGLE_API_KEY") and not settings.GOOGLE_API_KEY:
            print("GOOGLE_API_KEY is not set. Export it before running this script.")
            return 2

    client = get_llm_client(provider_name=provider)
    prompt = build_user_prompt(SAMPLE_ADDRESS, SAMPLE_RAW_DATA)
    raw_json = client.generate_json(SYSTEM_PROMPT, prompt)

    # Basic sanity checks
    parsed = json.loads(raw_json)
    required_keys = {
        "zoning_and_planning",
        "risk_factors",
        "connectivity",
        "infrastructure",
        "roi_scenarios",
        "demographic_snapshot",
        "demographic_trend_analysis",
        "education",
        "narrative",
    }
    missing = required_keys.difference(parsed.keys())
    if missing:
        print(f"Missing keys in output: {sorted(missing)}")
        return 1

    # Strict schema validation
    LlmOutput.model_validate_json(raw_json)

    print(raw_json)
    print(f"LLM provider {provider} ({client.model_name}) response validated successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
