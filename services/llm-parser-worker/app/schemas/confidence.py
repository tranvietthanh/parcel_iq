"""Confidence scoring — re-exports from shared parceliq-types.

The canonical ConfidenceResult and compute_confidence live in
shared/py-types/parceliq_types/confidence.py.
"""

from parceliq_types.confidence import (  # noqa: F401
    ConfidenceResult,
    compute_confidence,
)

__all__ = [
    "ConfidenceResult",
    "compute_confidence",
]
