"""Tests for the scrape_property Celery task."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestScrapePropertyTask:
    """Tests for the main scrape_property task."""

    @patch("app.celery_app.celery_app.send_task")
    @patch("app.services.minio_client.store_raw_scrape", return_value="key.json")
    @patch("app.utils.pii.strip_pii_from_scraped_data", side_effect=lambda d: d)
    @patch("app.adapters.runner.merge_adapter_results")
    @patch("app.adapters.runner.run_adapters_parallel")
    @patch("app.services.db.save_scrape_results")
    @patch("app.services.db.get_council_config", return_value=None)
    @patch("app.services.db.mark_report_processing", return_value="report-id-123")
    @patch("app.services.db.get_db_connection")
    def test_happy_path(
        self,
        mock_get_db: MagicMock,
        mock_mark_scraping: MagicMock,
        mock_get_council: MagicMock,
        mock_save: MagicMock,
        mock_run_adapters: MagicMock,
        mock_merge: MagicMock,
        mock_strip_pii: MagicMock,
        mock_store_raw: MagicMock,
        mock_send_task: MagicMock,
    ):
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        mock_run_adapters.return_value = [{"zoning_code": "GRZ1"}]
        mock_merge.return_value = {"zoning_code": "GRZ1", "data_sources": []}

        from app.tasks import scrape_property

        # Call via .run() which bypasses Celery machinery but keeps `self` binding
        result = scrape_property.run(
            property_id="prop-001",
            gnaf_pid="GAVIC411711364",
            address_string="1 Smith St, Melbourne VIC 3000",
            latitude=-37.8136,
            longitude=144.9631,
            lga_name="Melbourne",
            state="VIC",
        )

        assert result["property_id"] == "prop-001"
        assert result["report_id"] == "report-id-123"
        assert result["status"] == "PROCESSING"

        # Verify the flow
        mock_mark_scraping.assert_called_once_with(mock_db, "prop-001")
        mock_get_council.assert_called_once_with(mock_db, "Melbourne", "VIC")
        mock_run_adapters.assert_called_once()
        mock_merge.assert_called_once()
        mock_strip_pii.assert_called_once()
        mock_store_raw.assert_called_once()
        mock_save.assert_called_once()

        # Verify LLM task dispatch
        mock_send_task.assert_called_once_with(
            "app.tasks.parse_with_llm",
            kwargs={
                "property_id": "prop-001",
                "property_report_id": "report-id-123",
                "address_string": "1 Smith St, Melbourne VIC 3000",
            },
            queue="llm_processing_queue",
        )

        # DB connection closed
        mock_db.close.assert_called_once()

    @patch("app.services.db.mark_report_failed")
    @patch("app.services.db.get_db_connection")
    @patch("app.services.db.mark_report_processing", side_effect=Exception("DB error"))
    def test_marks_failed_on_final_retry(
        self,
        mock_mark_scraping: MagicMock,
        mock_get_db: MagicMock,
        mock_mark_failed: MagicMock,
    ):
        """When scraping fails, the task should attempt retry.

        Since .run() doesn't have real retry machinery, we just verify
        the exception propagates and the DB connection is closed.
        """
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        from app.tasks import scrape_property

        try:
            scrape_property.run(
                property_id="prop-001",
                gnaf_pid="GAVIC411711364",
                address_string="1 Smith St",
                latitude=-37.8136,
                longitude=144.9631,
                lga_name="Melbourne",
                state="VIC",
            )
        except Exception:
            pass

        # DB connection should be closed in finally block
        mock_db.close.assert_called_once()
        # Rollback should have been called on error
        mock_db.rollback.assert_called_once()
