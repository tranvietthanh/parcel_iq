"""Tests for the adapter runner — parallel execution and result merging."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.adapters.runner import merge_adapter_results, run_adapters_parallel


class TestMergeAdapterResults:
    """Tests for the merge_adapter_results function."""

    def test_merges_partial_dicts(self):
        partials = [
            {
                "zoning_code": "GRZ1",
                "zoning_label": "General Residential Zone 1",
                "overlays": [{"code": "HO123", "family": "heritage"}],
                "overlay_codes": ["HO123"],
                "data_sources": [{"name": "VicPlan"}],
            },
            {
                "nbn_type": "FTTP",
                "data_sources": [{"name": "NBN Co"}],
            },
            {
                "demographics": {"lga_code": "24600"},
                "data_sources": [{"name": "ABS"}],
            },
        ]

        merged = merge_adapter_results(partials)

        assert merged["zoning_code"] == "GRZ1"
        assert merged["nbn_type"] == "FTTP"
        assert merged["demographics"]["lga_code"] == "24600"
        assert len(merged["data_sources"]) == 3
        assert len(merged["overlays"]) == 1
        assert merged["overlay_codes"] == ["HO123"]

    def test_accumulates_overlays(self):
        partials = [
            {
                "overlays": [
                    {"code": "HO1", "family": "heritage"},
                    {"code": "HO2", "family": "heritage"},
                ]
            },
            {
                "overlays": [
                    {"code": "HO2", "family": "heritage"},
                    {"code": "HO3", "family": "heritage"},
                ]
            },
        ]

        merged = merge_adapter_results(partials)

        # De-duplicated by overlay code
        assert [overlay["code"] for overlay in merged["overlays"]] == ["HO1", "HO2", "HO3"]
        assert merged["overlay_codes"] == ["HO1", "HO2", "HO3"]

    def test_ignores_legacy_string_overlays(self):
        partials = [
            {"overlays": ["HO1", "HO2"]},
            {"overlays": [{"code": "HO3", "family": "heritage"}]},
        ]

        merged = merge_adapter_results(partials)
        assert [overlay["code"] for overlay in merged["overlays"]] == ["HO3"]
        assert merged["overlay_codes"] == ["HO3"]

    def test_accumulates_overlay_codes_from_partials(self):
        partials = [
            {"overlay_codes": ["HO1", "HO2"]},
            {"overlays": [{"code": "HO3", "family": "heritage"}]},
            {"overlay_codes": ["HO2", "SBO"]},
        ]

        merged = merge_adapter_results(partials)
        assert merged["overlay_codes"] == ["HO1", "HO2", "SBO", "HO3"]

    def test_later_non_none_overwrites(self):
        partials = [
            {"zoning_code": "old"},
            {"zoning_code": "new"},
        ]

        merged = merge_adapter_results(partials)
        assert merged["zoning_code"] == "new"

    def test_none_does_not_overwrite(self):
        partials = [
            {"zoning_code": "GRZ1"},
            {"zoning_code": None},
        ]

        merged = merge_adapter_results(partials)
        assert merged["zoning_code"] == "GRZ1"

    def test_empty_partials(self):
        merged = merge_adapter_results([])

        assert merged["zoning_code"] is None
        assert merged["data_sources"] == []

    def test_skips_internal_fields(self):
        partials = [
            {"_adapter_error": "timeout", "zoning_code": "R1Z"},
        ]

        merged = merge_adapter_results(partials)
        assert "_adapter_error" not in merged
        assert merged["zoning_code"] == "R1Z"


class TestRunAdaptersParallel:
    """Tests for the parallel adapter runner."""

    @patch("app.adapters.runner.NATIONAL_ADAPTERS", [])
    @patch("app.adapters.runner.STATE_ADAPTER_MAP", {})
    def test_runs_with_no_adapters(self):
        """With all adapters stubbed out, should still return results."""
        results = run_adapters_parallel(
            job={"state": "VIC"},
            council_config=None,
            state="VIC",
        )
        # Should have at least the GenericStateAdapter result
        assert isinstance(results, list)
        assert len(results) >= 1

    @patch("app.adapters.runner.NATIONAL_ADAPTERS", [])
    def test_includes_council_adapter_when_configured(self):
        """When council config is provided, the council adapter should run."""
        mock_adapter = MagicMock()
        mock_adapter_instance = MagicMock()
        mock_adapter_instance.scrape.return_value = {
            "council_planning_applications_text": "Test",
        }
        mock_adapter.return_value = mock_adapter_instance

        with patch(
            "app.adapters.runner.COUNCIL_ADAPTER_MAP",
            {"TechOne_Council": mock_adapter},
        ):
            results = run_adapters_parallel(
                job={"state": "VIC"},
                council_config={
                    "adapter_name": "TechOne_Council",
                    "base_url": "https://council.example.com",
                    "config": {},
                },
                state="VIC",
            )

        # Should include state + council results
        assert any(
            r.get("council_planning_applications_text") == "Test" for r in results
        )

    @patch("app.adapters.runner.NATIONAL_ADAPTERS", [])
    def test_skips_unknown_council_adapter(self):
        """Unknown adapter_name should be skipped gracefully."""
        results = run_adapters_parallel(
            job={"state": "VIC"},
            council_config={
                "adapter_name": "Unknown_Adapter",
                "base_url": "https://council.example.com",
                "config": {},
            },
            state="VIC",
        )
        # Should still get state adapter results
        assert isinstance(results, list)
