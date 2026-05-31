"""ozpr_types – Shared Pydantic models for OZ Property Report services.

Installed as a local path dependency in each service's pyproject.toml:
    [tool.uv.sources]
    parceliq-types = { path = "../../shared/py-types", editable = true }
"""

from parceliq_types.llm_output import LlmOutput
from parceliq_types.scraped_data import ScrapedPropertyData
from parceliq_types.confidence import ConfidenceResult, compute_confidence

__all__ = [
    "LlmOutput",
    "ScrapedPropertyData",
    "ConfidenceResult",
    "compute_confidence",
]
