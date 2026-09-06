"""Tests for ABS Census adapter with database caching.

Tests verify that the adapter:
1. Checks database for cached data first
2. Falls back to API if not cached
3. Stores new data in database
"""

from __future__ import annotations

from unittest.mock import MagicMock, Mock, patch

from app.adapters.national.abs_census import (
    AbsCensusAdapter,
    _add_growth_rates,
    _has_usable_cached_demographics,
)


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


class TestAbsGrowthRatesAndCacheUsability:
    """Tests for _add_growth_rates and _has_usable_cached_demographics."""

    def test_add_growth_rates_consecutive_years(self) -> None:
        """Growth rates are computed for consecutive years and absent for the initial year."""
        time_series = {
            "2021": {
                "total_population": 100000,
                "established_house_median_price_aud": 500000,
                "total_businesses": 1000,
                "total_dwelling_approvals": 200,
            },
            "2022": {
                "total_population": 110000,
                "established_house_median_price_aud": 550000,
                "total_businesses": 1100,
                "total_dwelling_approvals": 250,
            },
        }
        sorted_years = ["2021", "2022"]

        _add_growth_rates(time_series, sorted_years)

        # 2021 should have no growth metrics (no previous year)
        assert "population_growth_pct_yoy" not in time_series["2021"]
        assert "house_price_growth_pct_yoy" not in time_series["2021"]
        assert "business_count_growth_pct_yoy" not in time_series["2021"]
        assert "dwelling_approvals_growth_pct_yoy" not in time_series["2021"]

        # 2022 should have correctly calculated YoY metrics
        # (110000 - 100000) / 100000 * 100 = 10.0%
        assert time_series["2022"]["population_growth_pct_yoy"] == 10.0
        # (550000 - 500000) / 500000 * 100 = 10.0%
        assert time_series["2022"]["house_price_growth_pct_yoy"] == 10.0
        # (1100 - 1000) / 1000 * 100 = 10.0%
        assert time_series["2022"]["business_count_growth_pct_yoy"] == 10.0
        # (250 - 200) / 200 * 100 = 25.0%
        assert time_series["2022"]["dwelling_approvals_growth_pct_yoy"] == 25.0

    def test_add_growth_rates_coverage_gap(self) -> None:
        """Non-consecutive years (e.g. 2016 -> 2021) skip growth calculation."""
        time_series = {
            "2016": {
                "total_population": 100000,
            },
            "2021": {
                "total_population": 120000,
            },
            "2022": {
                "total_population": 126000,
            },
        }
        sorted_years = ["2016", "2021", "2022"]

        _add_growth_rates(time_series, sorted_years)

        # 2016: initial year, no growth
        assert "population_growth_pct_yoy" not in time_series["2016"]
        # 2021: 5-year gap (2016 to 2021), must NOT be labeled YoY
        assert "population_growth_pct_yoy" not in time_series["2021"]
        # 2022: consecutive with 2021, computes YoY: (126000 - 120000) / 120000 * 100 = 5.0%
        assert time_series["2022"]["population_growth_pct_yoy"] == 5.0

    def test_add_growth_rates_zero_and_none_safe(self) -> None:
        """Does not raise ZeroDivisionError if previous year is 0 or value is missing."""
        time_series = {
            "2021": {
                "total_population": 0,
                "total_businesses": None,
            },
            "2022": {
                "total_population": 500,
                "total_businesses": 100,
            },
        }
        _add_growth_rates(time_series, ["2021", "2022"])
        assert "population_growth_pct_yoy" not in time_series["2022"]
        assert "business_count_growth_pct_yoy" not in time_series["2022"]

    def test_has_usable_cached_demographics_valid_with_growth(self) -> None:
        """Cached blob with consecutive years and populated growth keys is usable."""
        enriched = {
            "latest": {"total_population": 110000},
            "time_series": {
                "2021": {"total_population": 100000},
                "2022": {"total_population": 110000, "population_growth_pct_yoy": 10.0},
            },
        }
        assert _has_usable_cached_demographics(enriched) is True

    def test_has_usable_cached_demographics_stale_without_growth(self) -> None:
        """Cached blob with consecutive years but 0 growth keys is treated as stale."""
        enriched = {
            "latest": {"total_population": 110000},
            "time_series": {
                "2021": {"total_population": 100000},
                "2022": {"total_population": 110000},
            },
        }
        assert _has_usable_cached_demographics(enriched) is False

    def test_has_usable_cached_demographics_single_year(self) -> None:
        """Single-year cached blob with no growth rates expected remains usable."""
        enriched = {
            "latest": {"total_population": 100000},
            "time_series": {
                "2021": {"total_population": 100000},
            },
        }
        assert _has_usable_cached_demographics(enriched) is True

    def test_has_usable_cached_demographics_non_consecutive_years_without_growth(self) -> None:
        """Non-consecutive years where growth cannot be computed remains usable."""
        enriched = {
            "latest": {"total_population": 120000},
            "time_series": {
                "2016": {"total_population": 100000},
                "2021": {"total_population": 120000},
            },
        }
        assert _has_usable_cached_demographics(enriched) is True

    def test_has_usable_cached_demographics_malformed(self) -> None:
        """Empty or missing structures return False."""
        assert _has_usable_cached_demographics({}) is False
        assert _has_usable_cached_demographics({"latest": {}}) is False
        assert _has_usable_cached_demographics({"time_series": {}}) is False
        assert _has_usable_cached_demographics(None) is False
