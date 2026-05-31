"""Unit tests for confidence scoring logic.

Tests the score computation rules and thresholds for HIGH/MEDIUM/LOW.
"""

from __future__ import annotations

import json

from parceliq_types.confidence import ConfidenceResult, compute_confidence
from parceliq_types.llm_output import LlmOutput

from tests.conftest import LOW_CONFIDENCE_OUTPUT, VALID_LLM_OUTPUT


class TestComputeConfidence:
    """Test confidence score calculation."""

    def _make_output(self, data: dict) -> LlmOutput:
        return LlmOutput.model_validate_json(json.dumps(data))

    def test_high_confidence_no_review(self) -> None:
        """All scores ≥ 0.85 → overall=HIGH."""
        output = self._make_output(VALID_LLM_OUTPUT)
        result = compute_confidence(output)

        assert isinstance(result, ConfidenceResult)
        assert result.overall == "HIGH"
        assert result.scores["overall_avg"] >= 0.85
    def test_medium_confidence_range(self) -> None:
        """Overall avg between 0.65 and 0.85 → MEDIUM."""
        import copy

        data = copy.deepcopy(VALID_LLM_OUTPUT)
        # Bring down some scores to land in medium range (7 fields now)
        data["zoning_and_planning"]["confidence_score"] = 0.7
        data["risk_factors"]["flood"]["confidence_score"] = 0.65
        data["risk_factors"]["bushfire"]["confidence_score"] = 0.65
        data["risk_factors"]["crime_density"]["confidence_score"] = 0.65
        data["connectivity"]["confidence_score"] = 0.7
        data["demographic_snapshot"]["confidence_score"] = 0.7
        data["infrastructure"][0]["confidence_score"] = 0.7
        data["infrastructure"][1]["confidence_score"] = 0.7
        output = self._make_output(data)
        result = compute_confidence(output)

        assert result.overall == "MEDIUM"

    def test_low_confidence_overall(self) -> None:
        """Overall avg < 0.65 → LOW."""
        import copy

        data = copy.deepcopy(VALID_LLM_OUTPUT)
        data["zoning_and_planning"]["confidence_score"] = 0.5
        data["risk_factors"]["flood"]["confidence_score"] = 0.5
        data["risk_factors"]["bushfire"]["confidence_score"] = 0.5
        data["risk_factors"]["crime_density"]["confidence_score"] = 0.5
        data["connectivity"]["confidence_score"] = 0.5
        data["demographic_snapshot"]["confidence_score"] = 0.5
        data["infrastructure"][0]["confidence_score"] = 0.5
        data["infrastructure"][1]["confidence_score"] = 0.5
        output = self._make_output(data)
        result = compute_confidence(output)

        assert result.overall == "LOW"

    def test_scores_dict_has_required_keys(self) -> None:
        """Scores dict must contain per-field scores + metadata."""
        output = self._make_output(VALID_LLM_OUTPUT)
        result = compute_confidence(output)

        required_keys = {
            "zoning_and_planning",
            "flood",
            "bushfire",
            "crime_density",
            "connectivity",
            "demographics",
            "infrastructure",
            "overall_avg",
        }
        assert required_keys.issubset(set(result.scores.keys()))

    def test_empty_infrastructure_scores_zero(self) -> None:
        """If no infrastructure items, infrastructure score = 0.0."""
        import copy

        data = copy.deepcopy(VALID_LLM_OUTPUT)
        data["infrastructure"] = []
        output = self._make_output(data)
        result = compute_confidence(output)

        assert result.scores["infrastructure"] == 0.0
