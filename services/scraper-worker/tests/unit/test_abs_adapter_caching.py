"""Tests for ABS Census adapter with database caching.

Tests verify that the adapter:
1. Checks database for cached data first
2. Falls back to API if not cached
3. Stores new data in database
"""

from __future__ import annotations

from unittest.mock import MagicMock, Mock, patch

import pytest

from app.adapters.national.abs_census import AbsCensusAdapter


class TestAbsCensusAdapterWithCaching:
    """Tests for ABS adapter with DB-backed caching."""

    @patch("app.adapters.national.abs_census.get_db_connection")
    @patch("app.adapters.national.abs_census.get_regional_data_from_db")
    @patch.object(AbsCensusAdapter, "_resolve_lga")
    def test_returns_cached_data_when_available(
        self,
        mock_resolve_lga: MagicMock,
        mock_get_cached: MagicMock,
        mock_get_db: MagicMock,
        sample_job: dict,
    ):
        """Test that cached Census data is returned without API call."""
        # Setup
        mock_resolve_lga.return_value = "24600"
        mock_db = Mock()
        mock_get_db.return_value = mock_db

        # Cached data exists
        cached_data = {
            "region_code": "24600",
            "region_type": "LGA2021",
            "enriched_demographics": {
                "lga_code": "24600",
                "lga_name": "Wyndham",
                "latest_year": "2024",
                "time_series": {"2024": {"total_population": 300000}},
                "latest": {"total_population": 300000},
            },
            "cached_at": "2026-02-27T14:00:00+00:00",
        }
        mock_get_cached.return_value = cached_data

        # Act
        adapter = AbsCensusAdapter()
        result = adapter.scrape(sample_job)

        # Assert
        assert result["demographics"] is not None
        assert result["demographics"]["lga_code"] == "24600"
        assert result["demographics"]["lga_name"] == "Wyndham"
        assert result["demographics"]["source"] == "ABS Data by Region (cached)"

        # Verify database was queried
        mock_get_cached.assert_called_once_with(mock_db, "24600")

        # Verify NO API calls were made (adapter.fetch_json not called)
        # (This is implicit — if fetch_json was called, test would fail)

    @patch("app.adapters.national.abs_census.store_regional_data_to_db")
    @patch("app.adapters.national.abs_census.get_regional_data_from_db")
    @patch("app.adapters.national.abs_census.get_db_connection")
    @patch.object(AbsCensusAdapter, "_fetch_lga_data")
    @patch.object(AbsCensusAdapter, "_parse_demographics")
    @patch.object(AbsCensusAdapter, "_resolve_lga")
    def test_downloads_and_caches_when_not_in_db(
        self,
        mock_resolve_lga: MagicMock,
        mock_parse: MagicMock,
        mock_fetch_lga_data: MagicMock,
        mock_get_db: MagicMock,
        mock_get_cached: MagicMock,
        mock_store: MagicMock,
        sample_job: dict,
    ):
        """Test that uncached data triggers API download and storage."""
        # Setup
        mock_resolve_lga.return_value = "24600"
        mock_db = Mock()
        mock_get_db.return_value = mock_db

        # Not in cache
        mock_get_cached.return_value = None

        mock_fetch_lga_data.return_value = {"data": {"dataSets": [{"observations": {}}]}}
        mock_parse.return_value = {
            "lga_code": "24600",
            "lga_name": "Wyndham",
            "latest_year": "2024",
            "time_series": {"2024": {"total_population": 300000}},
            "latest": {"total_population": 300000},
        }

        mock_store.return_value = True

        # Act
        adapter = AbsCensusAdapter()
        result = adapter.scrape(sample_job)

        # Assert: Got data
        assert result["demographics"] is not None
        assert result["demographics"]["lga_code"] == "24600"
        assert result["demographics"]["source"] == "ABS Data by Region (newly cached)"

        # Verify cache was checked
        mock_get_cached.assert_called_once_with(mock_db, "24600")

        # Verify regional fetch path was called
        mock_fetch_lga_data.assert_called_once_with("24600")
        mock_parse.assert_called_once()

        # Verify data was stored in DB
        mock_store.assert_called_once()
        call_args = mock_store.call_args
        assert call_args[1]["region_code"] == "24600"
        assert call_args[1]["region_type"] == "LGA2021"

        # DB connection should be used
        mock_get_db.assert_called()

    @patch("app.adapters.national.abs_census.store_regional_data_to_db")
    @patch("app.adapters.national.abs_census.get_regional_data_from_db")
    @patch("app.adapters.national.abs_census.get_db_connection")
    @patch.object(AbsCensusAdapter, "_fetch_lga_data")
    @patch.object(AbsCensusAdapter, "_parse_demographics")
    @patch.object(AbsCensusAdapter, "_resolve_lga")
    def test_invalid_cached_data_triggers_refetch(
        self,
        mock_resolve_lga: MagicMock,
        mock_parse: MagicMock,
        mock_fetch_lga_data: MagicMock,
        mock_get_db: MagicMock,
        mock_get_cached: MagicMock,
        mock_store: MagicMock,
        sample_job: dict,
    ):
        """Malformed cache rows should be ignored and refreshed from ABS."""
        mock_resolve_lga.return_value = "24600"
        mock_db = Mock()
        mock_get_db.return_value = mock_db

        mock_get_cached.return_value = {
            "region_code": "24600",
            "region_type": "LGA2021",
            "enriched_demographics": None,
            "cached_at": "fetched_at",
        }

        mock_fetch_lga_data.return_value = {"data": {"dataSets": [{"observations": {}}]}}
        mock_parse.return_value = {
            "lga_code": "24600",
            "lga_name": "Wyndham",
            "latest_year": "2024",
            "time_series": {"2024": {"total_population": 300000}},
            "latest": {"total_population": 300000},
        }
        mock_store.return_value = True

        adapter = AbsCensusAdapter()
        result = adapter.scrape(sample_job)

        assert result["demographics"] is not None
        assert result["demographics"]["source"] == "ABS Data by Region (newly cached)"
        mock_fetch_lga_data.assert_called_once_with("24600")
        mock_parse.assert_called_once()
        mock_store.assert_called_once()

    @patch("app.adapters.national.abs_census.get_regional_data_from_db")
    @patch("app.adapters.national.abs_census.get_db_connection")
    @patch.object(AbsCensusAdapter, "_resolve_lga")
    def test_handles_sa2_not_found(
        self,
        mock_resolve_lga: MagicMock,
        mock_get_db: MagicMock,
        mock_get_cached: MagicMock,
        sample_job: dict,
    ):
        """Test graceful handling when LGA cannot be resolved."""
        # Setup
        mock_resolve_lga.return_value = None

        # Act
        adapter = AbsCensusAdapter()
        result = adapter.scrape(sample_job)

        # Assert
        assert result["demographics"] is None

        # Database should NOT be queried
        mock_get_cached.assert_not_called()


class TestAbsCensusDataCacheIntegration:
    """Integration tests for cache workflow (with mocked DB)."""

    @patch("app.adapters.national.abs_census.get_db_connection")
    @patch("app.adapters.national.abs_census.get_regional_data_from_db")
    @patch.object(AbsCensusAdapter, "_resolve_lga")
    def test_cache_hit_returns_source_as_cached(
        self,
        mock_resolve_lga: MagicMock,
        mock_get_cached: MagicMock,
        mock_get_db: MagicMock,
    ):
        """Test that cache hits return 'source: cached' in response."""
        # Setup
        mock_resolve_lga.return_value = "24600"
        mock_db = Mock()
        mock_get_db.return_value = mock_db
        mock_get_cached.return_value = {
            "region_code": "24600",
            "region_type": "LGA2021",
            "enriched_demographics": {
                "lga_code": "24600",
                "lga_name": "Wyndham",
                "latest_year": "2024",
                "time_series": {"2024": {"total_population": 300000}},
                "latest": {"total_population": 300000},
            },
            "cached_at": "2026-02-27T10:00:00+00:00",
        }

        # Act
        adapter = AbsCensusAdapter()
        result = adapter.scrape(
            {
                "latitude": -37.8136,
                "longitude": 144.9631,
                "address_string": "Test",
                "state": "VIC",
            }
        )

        # Assert: source shows it's from cache
        assert "cached" in result["demographics"]["source"].lower()
        assert result["data_sources"][0]["name"] == "ABS Database Cache"

    @patch("app.adapters.national.abs_census.store_regional_data_to_db")
    @patch("app.adapters.national.abs_census.get_regional_data_from_db")
    @patch("app.adapters.national.abs_census.get_db_connection")
    @patch.object(AbsCensusAdapter, "_fetch_lga_data")
    @patch.object(AbsCensusAdapter, "_parse_demographics")
    @patch.object(AbsCensusAdapter, "_resolve_lga")
    def test_cache_miss_returns_source_as_newly_cached(
        self,
        mock_resolve_lga: MagicMock,
        mock_parse: MagicMock,
        mock_fetch_lga_data: MagicMock,
        mock_get_db: MagicMock,
        mock_get_cached: MagicMock,
        mock_store: MagicMock,
    ):
        """Test that new downloads return 'source: newly cached'."""
        # Setup
        mock_resolve_lga.return_value = "24600"
        mock_db = Mock()
        mock_get_db.return_value = mock_db
        mock_get_cached.return_value = None

        mock_fetch_lga_data.return_value = {"data": {"dataSets": [{"observations": {}}]}}
        mock_parse.return_value = {
            "lga_code": "24600",
            "lga_name": "Wyndham",
            "latest_year": "2024",
            "time_series": {"2024": {"total_population": 300000}},
            "latest": {"total_population": 300000},
        }
        mock_store.return_value = True

        # Act
        adapter = AbsCensusAdapter()
        result = adapter.scrape(
            {
                "latitude": -37.8136,
                "longitude": 144.9631,
                "address_string": "Test",
                "state": "VIC",
            }
        )

        # Assert: source shows it was newly cached
        assert "newly cached" in result["demographics"]["source"].lower()
        assert "ABS DataAPI" in result["data_sources"][0]["name"]
