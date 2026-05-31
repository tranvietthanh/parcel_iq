"""Confidence scoring for LLM-parsed property reports.

Computes per-field and overall confidence scores, and determines
whether a report requires admin review before being shown to users.

Schema source: docs/06-llm-parser-worker.md §8, docs/04-database.md §5
"""

from __future__ import annotations

from dataclasses import dataclass

from parceliq_types.llm_output import LlmOutput


@dataclass
class ConfidenceResult:
    """Result of confidence scoring for a single property report."""

    overall: str  # "HIGH", "MEDIUM", "LOW"
    scores: dict  # Per-field scores + overall_avg


def compute_confidence(output: LlmOutput) -> ConfidenceResult:
    """Compute confidence scores from LLM output.

    Rules:
    - overall: HIGH (≥0.85), MEDIUM (≥0.65), LOW (<0.65)
    """
    scores = {
        "zoning_and_planning": output.zoning_and_planning.confidence_score,
        "flood": output.risk_factors.flood.confidence_score,
        "bushfire": output.risk_factors.bushfire.confidence_score,
        "crime_density": output.risk_factors.crime_density.confidence_score,
        "connectivity": output.connectivity.confidence_score,
        "demographics": output.demographic_snapshot.confidence_score,
        "infrastructure": (
            sum(i.confidence_score for i in output.infrastructure) / len(output.infrastructure)
            if output.infrastructure
            else 0.0
        ),
    }

    values = list(scores.values())
    avg = sum(values) / len(values) if values else 0.0

    overall = "HIGH" if avg >= 0.85 else "MEDIUM" if avg >= 0.65 else "LOW"

    return ConfidenceResult(
        overall=overall,
        scores={
            **scores,
            "overall_avg": round(avg, 3),
        },
    )
