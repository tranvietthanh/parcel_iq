"""Generic state adapter — placeholder for states without a dedicated adapter.

Returns nulls so the LLM parser will report low confidence on zoning fields.
Active for: NSW, QLD, SA, WA, TAS, ACT, NT.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from app.adapters.base import BaseAdapter

logger = logging.getLogger(__name__)


class GenericStateAdapter(BaseAdapter):
    """Placeholder for states not yet fully implemented."""

    def scrape(self, job: dict) -> dict:
        logger.warning(
            "No state planning adapter for %s.  "
            "Returning null planning data for %s",
            job.get("state", "UNKNOWN"),
            job.get("address_string", ""),
        )
        return {
            "zoning_code": None,
            "zoning_label": None,
            "zoning_status": None,
            "zoning_scheme": None,
            "zone_num": None,
            "gazetted_date": None,
            "lga_name": None,
            "lga_code": None,
            "overlays": [],
            "overlay_codes": [],
            "overlay_groups": {},
            "flood_risk": None,
            "bushfire_risk": None,
            "heritage_overlay": None,
            "has_design_overlay": None,
            "has_vegetation_overlay": None,
            "has_environment_overlay": None,
            "public_acquisition": None,
            "airport_corridor": None,
            "development_contributions": None,
            "development_plan_required": None,
            "incorporated_plan_applies": None,
            "contamination_audit_required": None,
            "constraint_score": None,
            "requires_planning_permit": None,
            "constraint_summary": None,
            "data_sources": [
                {
                    "name": "Generic state planning adapter (no implementation)",
                    "url": None,
                    "fetched_at": datetime.now(UTC).isoformat(),
                }
            ],
        }
