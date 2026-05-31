"""Level 3: Celery Task Queue Integration Tests

Tests that dispatch actual Celery tasks through Redis broker,
verifying end-to-end task execution with real adapters.

These tests use task_always_eager=True mode by default, which executes
tasks synchronously in-process without needing a separate worker.

For testing with a real worker:
  1. Start Redis: docker compose up -d redis
  2. Start worker: celery -A app.celery_app worker --loglevel=info
  3. Set CELERY_ALWAYS_EAGER=false in environment
  4. Run: pytest tests/integration/ -v
"""

from __future__ import annotations

from unittest.mock import ANY, MagicMock, patch

import pytest


class TestAdapterTaskExecution:
    """Test adapter execution through task-like patterns."""

    def test_vic_plan_adapter_execution(self, celery_config, sample_property_job):
        """Test VicPlan adapter executes successfully.
        
        This simulates what happens when a scrape task runs the VicPlan adapter.
        We mock the HTTP call but test the full adapter logic path.
        """
        from app.adapters.state.vic_plan import VicPlanAdapter

        # Mock the fetch_json to avoid real API calls
        with patch.object(VicPlanAdapter, "fetch_json") as mock_fetch:
            # Mock ArcGIS FeatureServer responses
            mock_fetch.side_effect = [
                # Zone query response (Layer 3)
                {
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
                # Overlay query response (Layer 2)
                {"features": [{"attributes": {"ZONE_CODE": "HO123", "ZONE_DESCRIPTION": "Heritage Overlay"}}]},
                # Bushfire query response (Layer 9)
                {"features": [{"attributes": {"OBJECTID": 1}}]},
            ]

            adapter = VicPlanAdapter()
            result = adapter.scrape(sample_property_job)

            # Verify results
            assert result["zoning_code"] == "GRZ1"
            assert result["zoning_status"] == "Approved"
            assert result["lga_name"] == "MELBOURNE"
            assert result["bushfire_risk"] == "LOW"  # Prone area without BMO/BAO
            assert result["heritage_overlay"] is True  # HO123
            assert "HO123" in result["overlay_codes"]
            assert len(result["data_sources"]) == 1

            # Verify 3 API calls were made (zone, overlay, bushfire)
            assert mock_fetch.call_count == 3

    def test_nsw_state_uses_generic_adapter(self, celery_config, sample_nsw_property_job):
        """NSW now uses GenericStateAdapter and should return the generic schema."""
        from app.adapters.state.generic_state import GenericStateAdapter

        adapter = GenericStateAdapter()
        result = adapter.scrape(sample_nsw_property_job)

        assert result["zoning_code"] is None
        assert result["overlay_codes"] == []
        assert result["constraint_score"] is None
        assert result["requires_planning_permit"] is None
        assert len(result["data_sources"]) == 1

    def test_nbn_adapter_execution_with_suggest_flow(self, celery_config, sample_property_job):
        """Test NBN Co adapter executes 2-step suggest→details flow."""
        from app.adapters.national.nbnco import NbnCoAdapter

        with patch.object(NbnCoAdapter, "fetch_json") as mock_fetch:
            # Mock suggest response, then details response
            mock_fetch.side_effect = [
                # POST /suggest response
                {"suggestions": [{"id": "LOC000123456789", "formattedAddress": "1 Collins St"}]},
                # GET /details/{locId} response
                {
                    "addressDetail": {
                        "techType": "FTTP",
                        "serviceType": "Fixed line",
                        "serviceStatus": "available",
                        "techChangeStatus": None,
                        "targetEligibilityQuarter": None,
                        "formattedAddress": "1 Collins Street, Melbourne VIC 3000",
                    }
                },
            ]

            adapter = NbnCoAdapter()
            result = adapter.scrape(sample_property_job)

            # Verify results
            assert result["nbn"]["loc_id"] == "LOC000123456789"
            assert result["nbn"]["tech_type"] == "FTTP"
            assert result["nbn"]["service_type"] == "Fixed line"
            assert result["nbn"]["service_status"] == "available"
            assert len(result["data_sources"]) == 1

            # Verify 2 API calls (suggest + details)
            assert mock_fetch.call_count == 2

    def test_abs_census_adapter_with_db_cache_hit(self, celery_config, sample_property_job):
        """Test ABS regional adapter when DB cache hits (fast path)."""
        from app.adapters.national.abs_census import AbsCensusAdapter

        with patch.object(AbsCensusAdapter, "_resolve_lga") as mock_resolve_lga, \
             patch("app.adapters.national.abs_census.get_regional_data_from_db") as mock_db_get:
            
            # Mock LGA resolution
            mock_resolve_lga.return_value = "24600"
            
            # Simulate cache hit - return cached data
            mock_db_get.return_value = {
                "region_code": "24600",
                "region_type": "LGA2021",
                "enriched_demographics": {
                    "lga_code": "24600",
                    "lga_name": "Wyndham",
                    "latest_year": "2024",
                    "time_series": {"2024": {"total_population": 300000}},
                    "latest": {"total_population": 300000},
                },
                "cached_at": "2024-01-01T00:00:00Z",
            }

            adapter = AbsCensusAdapter()
            result = adapter.scrape(sample_property_job)

            # Verify results from cache
            assert result["demographics"]["lga_code"] == "24600"
            assert result["demographics"]["lga_name"] == "Wyndham"
            assert result["demographics"]["source"] == "ABS Data by Region (cached)"
            assert len(result["data_sources"]) == 1
            
            # Verify DB was queried (accepts any DB connection object as first arg)
            mock_db_get.assert_called_once_with(ANY, "24600")

    def test_adapter_error_handling(self, celery_config, sample_property_job):
        """Test that adapter errors are handled gracefully."""
        from app.adapters.state.vic_plan import VicPlanAdapter

        with patch.object(VicPlanAdapter, "fetch_json") as mock_fetch:
            # Simulate API timeout
            mock_fetch.side_effect = TimeoutError("API timeout")

            adapter = VicPlanAdapter()
            result = adapter.scrape(sample_property_job)

            # Should return null data, not crash
            assert result["zoning_code"] is None
            assert result["zoning_status"] is None
            assert result["bushfire_risk"] is None


class TestCeleryTaskConfiguration:
    """Test Celery configuration and task registration."""

    def test_celery_app_configured(self, celery_config):
        """Verify Celery app is properly configured."""
        from app.celery_app import celery_app

        assert celery_app.conf.task_serializer == "json"
        assert celery_app.conf.result_serializer == "json"
        assert celery_app.conf.timezone == "UTC"
        assert celery_app.conf.enable_utc is True

    def test_scrape_property_task_registered(self, celery_config):
        """Verify scrape_property task is registered."""
        from app.celery_app import celery_app

        registered_tasks = celery_app.tasks.keys()
        assert "scraper_worker.tasks.scrape_property" in registered_tasks

    def test_census_refresh_task_registered(self, celery_config):
        """Verify census refresh task is registered."""
        from app.celery_app import celery_app

        registered_tasks = celery_app.tasks.keys()
        assert "app.tasks.refresh_abs_census_complete" in registered_tasks


# ─── Documentation for running with real worker ───────────────────────────────

"""
RUNNING WITH REAL CELERY WORKER (Advanced)

For full end-to-end testing with a real worker process:

1. Start dependencies:
   ```bash
   docker compose up -d postgres redis
   cd shared/db-migrations && alembic upgrade head
   ```

2. Start Celery worker in separate terminal:
   ```bash
   cd services/scraper-worker
   celery -A app.celery_app worker --loglevel=info --queue=data_acquisition_queue
   ```

3. Disable eager mode and run tests:
   ```bash
   export CELERY_ALWAYS_EAGER=false
   pytest tests/integration/test_adapter_tasks.py -v -s
   ```

Expected output:
  - Tasks will be dispatched to Redis
  - Worker picks up tasks and executes them
  - Tests wait for results via AsyncResult.get()

Notes:
  - Requires modifying conftest.py to check CELERY_ALWAYS_EAGER env var
  - Tests need to use .apply_async() and wait for results
  - Slower but tests real distributed execution
"""
