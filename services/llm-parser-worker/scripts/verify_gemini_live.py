"""Manual live call sanity check.

Runs a single prompt against the configured provider and validates basic JSON
structure.
This is intentionally not part of pytest to avoid quota usage in CI.
"""

from __future__ import annotations

import json
import os
import sys

from app.prompts.system_prompt import SYSTEM_PROMPT
from app.prompts.user_prompt import build_user_prompt
from app.services.llm_client import llm_client
from parceliq_types.llm_output import LlmOutput


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
    from app.config import settings

    # Worker now uses OpenAI; ensure API key is set
    if not os.getenv("OPENAI_API_KEY") and not settings.OPENAI_API_KEY:
        print("OPENAI_API_KEY is not set. Export it before running this script.")
        return 2

    prompt = build_user_prompt(SAMPLE_ADDRESS, SAMPLE_RAW_DATA)
    raw_json = llm_client.generate_json(SYSTEM_PROMPT, prompt)

    # Basic sanity checks
    parsed = json.loads(raw_json)
    required_keys = {
        "zoning_and_planning",
        "risk_factors",
        "connectivity",
        "infrastructure",
        "roi_scenarios",
        "demographic_snapshot",
        "review_required",
        "review_reasons",
    }
    missing = required_keys.difference(parsed.keys())
    if missing:
        print(f"Missing keys in output: {sorted(missing)}")
        return 1

    # Strict schema validation
    LlmOutput.model_validate_json(raw_json)

    print(raw_json)
    print(f"OpenAI ({settings.OPENAI_MODEL}) response validated successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
