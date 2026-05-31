"""Tests for national adapters — ABS Census and NBN Co."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.adapters.national.abs_census import AbsCensusAdapter
from app.adapters.national.nbnco import NbnCoAdapter


class TestAbsCensusAdapter:
    """Tests for the ABS Census adapter."""

    @patch("app.adapters.national.abs_census.get_regional_data_from_db")
    @patch("app.adapters.national.abs_census.get_db_connection")
    @patch.object(AbsCensusAdapter, "_parse_demographics")
    @patch.object(AbsCensusAdapter, "_fetch_lga_data")
    @patch.object(AbsCensusAdapter, "_resolve_lga")
    def test_returns_demographics_on_success(
        self,
        mock_resolve_lga: MagicMock,
        mock_fetch_lga_data: MagicMock,
        mock_parse: MagicMock,
        mock_get_db: MagicMock,
        mock_get_cached: MagicMock,
        sample_job: dict,
    ):
        # Mock DB connection and cache lookup (returns None — not cached)
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        mock_get_cached.return_value = None  # Not in cache, will fetch from API

        mock_resolve_lga.return_value = "24600"
        mock_fetch_lga_data.return_value = {"data": {"dataSets": [{"observations": {}}]}}
        mock_parse.return_value = {
            "lga_code": "24600",
            "lga_name": "Wyndham",
            "latest_year": "2024",
            "time_series": {"2024": {"total_population": 300000}},
            "latest": {"total_population": 300000},
        }

        adapter = AbsCensusAdapter()
        result = adapter.scrape(sample_job)

        assert result["demographics"] is not None
        assert result["demographics"]["lga_code"] == "24600"
        assert result["demographics"]["source"] == "ABS Data by Region (newly cached)"
        assert len(result["data_sources"]) == 1
        assert "Data by Region" in result["data_sources"][0]["name"]

    @patch.object(AbsCensusAdapter, "_resolve_lga")
    def test_returns_null_demographics_when_sa2_not_found(
        self, mock_resolve_lga: MagicMock, sample_job: dict
    ):
        mock_resolve_lga.return_value = None

        adapter = AbsCensusAdapter()
        result = adapter.scrape(sample_job)

        assert result["demographics"] is None


class TestNbnCoAdapter:
    """Tests for the NBN Co adapter (v2 API)."""

    @patch.object(NbnCoAdapter, "fetch_json")
    def test_returns_nbn_details_on_success_via_suggest(
        self, mock_fetch: MagicMock, sample_job: dict
    ):
        # Mock the two-step flow: suggest → details
        mock_fetch.side_effect = [
            {  # Step 1: suggest API returns locId
                "suggestions": [
                    {
                        "id": "LOC000123456789",
                        "formattedAddress": "123 Test St, Melbourne VIC 3000",
                    }
                ]
            },
            {  # Step 2: details API returns tech type
                "addressDetail": {
                    "techType": "FTTP",
                    "serviceType": "Fixed line",
                    "serviceStatus": "available",
                    "formattedAddress": "123 Test St, Melbourne VIC 3000",
                }
            },
        ]

        adapter = NbnCoAdapter()
        # Ensure coords are absent so the adapter uses the suggest flow
        sample_job.pop("latitude", None)
        sample_job.pop("longitude", None)
        result = adapter.scrape(sample_job)

        assert result["nbn"] is not None
        assert result["nbn"]["tech_type"] == "FTTP"
        assert result["nbn"]["service_type"] == "Fixed line"
        assert result["nbn"]["service_status"] == "available"
        assert result["nbn"]["loc_id"] == "LOC000123456789"
        assert len(result["data_sources"]) == 1
        assert "unofficial" in result["data_sources"][0]["name"].lower()

    @patch.object(NbnCoAdapter, "fetch_json")
    def test_skips_suggest_when_nbn_loc_id_provided(
        self, mock_fetch: MagicMock, sample_job: dict
    ):
        # Provide nbn_loc_id directly — should skip suggest and only call details
        sample_job["nbn_loc_id"] = "LOC000999888777"

        mock_fetch.return_value = {
            "addressDetail": {
                "techType": "HFC",
                "serviceType": "Fixed line",
                "serviceStatus": "available",
            }
        }

        adapter = NbnCoAdapter()
        result = adapter.scrape(sample_job)

        # Should only call details once (not suggest)
        assert mock_fetch.call_count == 1
        assert result["nbn"]["tech_type"] == "HFC"
        assert result["nbn"]["loc_id"] == "LOC000999888777"

    @patch.object(NbnCoAdapter, "fetch_json")
    def test_returns_null_when_suggest_fails(
        self, mock_fetch: MagicMock, sample_job: dict
    ):
        mock_fetch.side_effect = Exception("api error")

        adapter = NbnCoAdapter()
        result = adapter.scrape(sample_job)

        assert result["nbn"] is None

    @patch.object(NbnCoAdapter, "fetch_json")
    def test_returns_null_when_no_suggestions(
        self, mock_fetch: MagicMock, sample_job: dict
    ):
        # Suggest returns empty suggestions list
        mock_fetch.return_value = {"suggestions": []}

        adapter = NbnCoAdapter()
        result = adapter.scrape(sample_job)

        assert result["nbn"] is None

    def test_returns_null_without_address_or_gnaf_pid(self):
        adapter = NbnCoAdapter()
        result = adapter.scrape({"gnaf_pid": None, "address_string": None})
        assert result["nbn"] is None
