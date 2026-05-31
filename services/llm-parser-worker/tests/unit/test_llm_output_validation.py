"""Unit tests for LlmOutput Pydantic v2 validation.

Tests that valid JSON parses correctly, and invalid/malformed JSON
is rejected by the strict Pydantic model.
"""

from __future__ import annotations

import copy
import json

import pytest

from parceliq_types.llm_output import LlmOutput

from tests.conftest import VALID_LLM_OUTPUT


class TestLlmOutputValidation:
    """Test Pydantic v2 validation of LLM JSON output."""

    def test_valid_output_parses_successfully(self, valid_output_json: str) -> None:
        """Full valid output should parse without errors."""
        result = LlmOutput.model_validate_json(valid_output_json)
        assert result.zoning_and_planning.zoning_code == "GRZ1"
        assert result.risk_factors.flood.risk == "LOW"
        assert len(result.infrastructure) == 2
        assert len(result.roi_scenarios.scenarios) == 3

    def test_rejects_extra_keys(self) -> None:
        """extra='forbid' should reject unexpected keys."""
        data = copy.deepcopy(VALID_LLM_OUTPUT)
        data["unexpected_field"] = "should fail"
        with pytest.raises(Exception, match="unexpected_field"):
            LlmOutput.model_validate_json(json.dumps(data))

    def test_rejects_missing_required_field(self) -> None:
        """Missing a required top-level field should fail."""
        data = copy.deepcopy(VALID_LLM_OUTPUT)
        del data["zoning_and_planning"]
        with pytest.raises(Exception):
            LlmOutput.model_validate_json(json.dumps(data))

    def test_rejects_invalid_risk_level(self) -> None:
        """Risk must be one of the allowed Literal values."""
        data = copy.deepcopy(VALID_LLM_OUTPUT)
        data["risk_factors"]["flood"]["risk"] = "EXTREME"
        with pytest.raises(Exception):
            LlmOutput.model_validate_json(json.dumps(data))

    def test_rejects_confidence_out_of_range(self) -> None:
        """Confidence score must be between 0.0 and 1.0."""
        data = copy.deepcopy(VALID_LLM_OUTPUT)
        data["zoning_and_planning"]["confidence_score"] = 1.5
        with pytest.raises(Exception):
            LlmOutput.model_validate_json(json.dumps(data))

    def test_rejects_negative_confidence(self) -> None:
        """Negative confidence should fail."""
        data = copy.deepcopy(VALID_LLM_OUTPUT)
        data["risk_factors"]["bushfire"]["confidence_score"] = -0.1
        with pytest.raises(Exception):
            LlmOutput.model_validate_json(json.dumps(data))

    def test_rejects_missing_roi_disclaimer(self) -> None:
        """ROI scenarios must include a non-empty disclaimer."""
        data = copy.deepcopy(VALID_LLM_OUTPUT)
        data["roi_scenarios"]["disclaimer"] = ""
        with pytest.raises(Exception, match="disclaimer"):
            LlmOutput.model_validate_json(json.dumps(data))

    def test_rejects_short_roi_disclaimer(self) -> None:
        """Disclaimer must be at least 10 chars."""
        data = copy.deepcopy(VALID_LLM_OUTPUT)
        data["roi_scenarios"]["disclaimer"] = "short"
        with pytest.raises(Exception, match="disclaimer"):
            LlmOutput.model_validate_json(json.dumps(data))

    def test_rejects_invalid_scenario_label(self) -> None:
        """Scenario label must be Conservative, Base, or Optimistic."""
        data = copy.deepcopy(VALID_LLM_OUTPUT)
        data["roi_scenarios"]["scenarios"][0]["label"] = "Aggressive"
        with pytest.raises(Exception):
            LlmOutput.model_validate_json(json.dumps(data))

    def test_rejects_invalid_infrastructure_type(self) -> None:
        """Infrastructure type must be one of the Literal values."""
        data = copy.deepcopy(VALID_LLM_OUTPUT)
        data["infrastructure"][0]["type"] = "RECREATIONAL"
        with pytest.raises(Exception):
            LlmOutput.model_validate_json(json.dumps(data))

    def test_rejects_invalid_crime_rating(self) -> None:
        """Crime density rating must be a valid Literal."""
        data = copy.deepcopy(VALID_LLM_OUTPUT)
        data["risk_factors"]["crime_density"]["rating"] = "VERY_HIGH"
        with pytest.raises(Exception):
            LlmOutput.model_validate_json(json.dumps(data))

    def test_null_optionals_accepted(self) -> None:
        """Null values should be accepted for optional fields."""
        data = copy.deepcopy(VALID_LLM_OUTPUT)
        data["zoning_and_planning"]["zoning_code"] = None
        data["zoning_and_planning"]["subdivision_potential"] = None
        data["risk_factors"]["flood"]["risk"] = None
        data["risk_factors"]["flood"]["detail"] = None
        data["demographic_snapshot"]["median_age"] = None
        result = LlmOutput.model_validate_json(json.dumps(data))
        assert result.zoning_and_planning.zoning_code is None
        assert result.risk_factors.flood.risk is None

    def test_empty_infrastructure_list_accepted(self) -> None:
        """Empty infrastructure list should be valid."""
        data = copy.deepcopy(VALID_LLM_OUTPUT)
        data["infrastructure"] = []
        result = LlmOutput.model_validate_json(json.dumps(data))
        assert result.infrastructure == []

    def test_model_dump_roundtrip(self, valid_output_json: str) -> None:
        """Parse → dump → re-parse should produce identical model."""
        first = LlmOutput.model_validate_json(valid_output_json)
        dumped = json.dumps(first.model_dump())
        second = LlmOutput.model_validate_json(dumped)
        assert first == second

    def test_rejects_removed_review_fields(self) -> None:
        """Legacy review queue fields should be rejected."""
        data = copy.deepcopy(VALID_LLM_OUTPUT)
        data["review_required"] = True
        data["review_reasons"] = ["Flood data source ambiguous.", "Heritage status uncertain."]
        with pytest.raises(Exception, match="review_required"):
            LlmOutput.model_validate_json(json.dumps(data))

    def test_connectivity_parses_correctly(self) -> None:
        """Connectivity section with valid NBN data should parse."""
        result = LlmOutput.model_validate_json(json.dumps(VALID_LLM_OUTPUT))
        assert result.connectivity.nbn_tech_type == "FTTP"
        assert result.connectivity.nbn_service_status == "available"
        assert result.connectivity.confidence_score == 0.95

    def test_rejects_invalid_nbn_tech_type(self) -> None:
        """NBN tech type must be one of the allowed Literal values."""
        data = copy.deepcopy(VALID_LLM_OUTPUT)
        data["connectivity"]["nbn_tech_type"] = "FIBRE"
        with pytest.raises(Exception):
            LlmOutput.model_validate_json(json.dumps(data))

    def test_zoning_new_fields_accepted(self) -> None:
        """New zoning fields (lga_name, epi_name, heritage_area, conflict_note) should parse."""
        result = LlmOutput.model_validate_json(json.dumps(VALID_LLM_OUTPUT))
        assert result.zoning_and_planning.lga_name == "Boroondara"
        assert result.zoning_and_planning.heritage_area is True
        assert result.zoning_and_planning.conflict_note is None
