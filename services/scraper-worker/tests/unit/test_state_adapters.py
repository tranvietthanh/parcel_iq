"""Tests for state-level adapters."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.adapters.state.generic_state import GenericStateAdapter
from app.adapters.state.vic_plan import VicPlanAdapter


class TestVicPlanAdapter:
    """Tests for the VicPlan adapter (ArcGIS FeatureServer)."""

    @patch("app.adapters.state.vic_plan.store_vic_plan_data")
    @patch("app.adapters.state.vic_plan.get_cached_vic_plan_data", return_value=None)
    @patch.object(VicPlanAdapter, "fetch_json")
    def test_returns_zoning_data(
        self, mock_fetch: MagicMock, mock_cache: MagicMock, mock_store: MagicMock, sample_job: dict
    ):
        # Mock ArcGIS FeatureServer responses for zones, overlays, and bushfire
        mock_fetch.side_effect = [
            {  # Zone query (Layer 3)
                "features": [
                    {
                        "attributes": {
                            "ZONE_CODE": "GRZ1",
                            "ZONE_STATUS": "Approved",
                            "LGA": "MELBOURNE",
                        }
                    }
                ]
            },
            {  # Overlay query (Layer 2)
                "features": [
                    {"attributes": {"ZONE_CODE": "HO123", "ZONE_DESCRIPTION": "Heritage Overlay"}},
                    {"attributes": {"ZONE_CODE": "LSIO", "ZONE_DESCRIPTION": "Land Subject to Inundation"}},
                ]
            },
            {  # Bushfire query (Layer 9) - no features (not in bushfire zone)
                "features": []
            },
        ]

        adapter = VicPlanAdapter()
        result = adapter.scrape(sample_job)

        assert result["zoning_code"] == "GRZ1"
        assert result["zoning_status"] == "Approved"
        assert result["lga_name"] == "MELBOURNE"
        assert "HO123" in result["overlay_codes"]
        assert "LSIO" in result["overlay_codes"]
        assert any(o["code"] == "HO123" for o in result["overlays"])
        assert result["flood_risk"] == "MEDIUM"  # LSIO = Medium
        assert result["bushfire_risk"] == "NONE"
        assert result["heritage_overlay"] is True  # HO123 detected

    @patch("app.adapters.state.vic_plan.store_vic_plan_data")
    @patch("app.adapters.state.vic_plan.get_cached_vic_plan_data", return_value=None)
    @patch.object(VicPlanAdapter, "fetch_json")
    def test_classifies_high_flood_risk(
        self, mock_fetch: MagicMock, mock_cache: MagicMock, mock_store: MagicMock, sample_job: dict
    ):
        mock_fetch.side_effect = [
            {"features": [{"attributes": {"ZONE_CODE": "GRZ1"}}]},
            {
                "features": [
                    {"attributes": {"ZONE_CODE": "FO"}},  # Floodway = HIGH
                    {"attributes": {"ZONE_CODE": "LSIO"}},
                ]
            },
            {"features": []},
        ]

        adapter = VicPlanAdapter()
        result = adapter.scrape(sample_job)

        assert result["flood_risk"] == "HIGH"  # FO takes precedence

    @patch("app.adapters.state.vic_plan.store_vic_plan_data")
    @patch("app.adapters.state.vic_plan.get_cached_vic_plan_data", return_value=None)
    @patch.object(VicPlanAdapter, "fetch_json")
    def test_classifies_bushfire_risk_from_dedicated_layer(
        self, mock_fetch: MagicMock, mock_cache: MagicMock, mock_store: MagicMock, sample_job: dict
    ):
        mock_fetch.side_effect = [
            {"features": [{"attributes": {"ZONE_CODE": "RLZ"}}]},
            {"features": []},  # No overlays
            {"features": [{"attributes": {"OBJECTID": 12345}}]},  # In bushfire zone
        ]

        adapter = VicPlanAdapter()
        result = adapter.scrape(sample_job)

        assert result["bushfire_risk"] == "LOW"  # Prone area without BMO/BAO

    @patch("app.adapters.state.vic_plan.store_vic_plan_data")
    @patch("app.adapters.state.vic_plan.get_cached_vic_plan_data", return_value=None)
    @patch.object(VicPlanAdapter, "fetch_json")
    def test_handles_low_flood_risk_from_sbo(
        self, mock_fetch: MagicMock, mock_cache: MagicMock, mock_store: MagicMock, sample_job: dict
    ):
        mock_fetch.side_effect = [
            {"features": [{"attributes": {"ZONE_CODE": "GRZ1"}}]},
            {"features": [{"attributes": {"ZONE_CODE": "SBO"}}]},  # Special Building Overlay
            {"features": []},
        ]

        adapter = VicPlanAdapter()
        result = adapter.scrape(sample_job)

        assert result["flood_risk"] == "LOW"  # SBO = drainage overlay

    @patch("app.adapters.state.vic_plan.store_vic_plan_data")
    @patch("app.adapters.state.vic_plan.get_cached_vic_plan_data", return_value=None)
    @patch.object(VicPlanAdapter, "fetch_json")
    def test_handles_empty_features(
        self, mock_fetch: MagicMock, mock_cache: MagicMock, mock_store: MagicMock, sample_job: dict
    ):
        mock_fetch.side_effect = [
            {"features": []},  # No zone found
            {"features": []},  # No overlays
            {"features": []},  # Not in bushfire zone
        ]

        adapter = VicPlanAdapter()
        result = adapter.scrape(sample_job)

        assert result["zoning_code"] is None
        assert result["lga_name"] is None
        assert result["overlays"] == []
        assert result["overlay_codes"] == []
        assert result["flood_risk"] == "NONE"
        assert result["bushfire_risk"] == "NONE"
        assert result["heritage_overlay"] is False

    @patch("app.adapters.state.vic_plan.store_vic_plan_data")
    @patch("app.adapters.state.vic_plan.get_cached_vic_plan_data", return_value=None)
    @patch.object(VicPlanAdapter, "fetch_json")
    def test_handles_api_error_gracefully(
        self, mock_fetch: MagicMock, mock_cache: MagicMock, mock_store: MagicMock, sample_job: dict
    ):
        mock_fetch.side_effect = Exception("API down")

        adapter = VicPlanAdapter()
        result = adapter.scrape(sample_job)

        assert result["zoning_code"] is None
        assert result["overlays"] == []
        assert result["heritage_overlay"] is None


class TestGenericStateAdapter:
    """Tests for the generic state placeholder."""

    def test_returns_nulls(self, sample_job: dict):
        sample_job["state"] = "SA"
        adapter = GenericStateAdapter()
        result = adapter.scrape(sample_job)

        assert result["zoning_code"] is None
        assert result["zoning_label"] is None
        assert result["overlays"] == []
        assert result["overlay_codes"] == []
        assert result["overlay_groups"] == {}
        assert result["flood_risk"] is None
        assert result["bushfire_risk"] is None
        assert result["constraint_score"] is None
        assert result["requires_planning_permit"] is None
        assert isinstance(result["data_sources"], list)

    def test_nsw_uses_generic_shape(self, sample_job: dict):
        sample_job["state"] = "NSW"
        adapter = GenericStateAdapter()
        result = adapter.scrape(sample_job)

        expected_keys = {
            "zoning_code",
            "zoning_label",
            "zoning_status",
            "zoning_scheme",
            "zone_num",
            "gazetted_date",
            "lga_name",
            "lga_code",
            "overlays",
            "overlay_codes",
            "overlay_groups",
            "flood_risk",
            "bushfire_risk",
            "heritage_overlay",
            "has_design_overlay",
            "has_vegetation_overlay",
            "has_environment_overlay",
            "public_acquisition",
            "airport_corridor",
            "development_contributions",
            "development_plan_required",
            "incorporated_plan_applies",
            "contamination_audit_required",
            "constraint_score",
            "requires_planning_permit",
            "constraint_summary",
            "data_sources",
        }
        assert expected_keys.issubset(result.keys())
