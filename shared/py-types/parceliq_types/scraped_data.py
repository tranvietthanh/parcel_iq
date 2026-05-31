"""Scraped property data model.

Merged output from all adapters for a single property.
Used by the Scraper Worker (produces) and LLM Parser Worker (consumes).

Schema source: docs/05-scraper-worker.md §5
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal


@dataclass
class ScrapedPropertyData:
    """Merged output from all adapters for a single property."""

    # State-level planning data
    zoning_code: str | None = None
    zoning_label: str | None = None
    overlays: list[str] = field(default_factory=list)
    flood_risk: Literal["NONE", "LOW", "MEDIUM", "HIGH"] | None = None
    bushfire_risk: Literal["NONE", "LOW", "MEDIUM", "HIGH"] | None = None

    # National data
    nbn_type: str | None = None
    demographics: dict | None = None

    # Education data
    nearby_schools: dict | None = None  # Schools within 3km radius with catchment info

    # Council-level data (unstructured text for LLM to parse)
    council_planning_applications_text: str | None = None
    council_meeting_minutes_text: str | None = None

    # Source attribution (for data quality + display)
    data_sources: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to plain dict for JSON serialisation."""
        return asdict(self)
