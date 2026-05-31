"""Integration tests for the parse_with_llm task pipeline.

Mocks the Gemini API client and database to test the full task flow:
prompt building → LLM call → Pydantic validation → confidence scoring → DB upsert.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import SAMPLE_ADDRESS, SAMPLE_RAW_DATA, valid_llm_json


def _report_update_params(mock_cursor: MagicMock) -> tuple:
    """Return params for the final parsed-insights UPDATE."""
    for call in mock_cursor.execute.call_args_list:
        sql = call[0][0]
        if "llm_parsed_insights" in sql and "llm_model_version" in sql:
            return call[0][1]
    raise AssertionError("Parsed-insights UPDATE was not executed.")


class TestParseWithLlmTask:
    """Test the full parse_with_llm task pipeline with mocked externals."""

    @patch("app.tasks.get_db_connection")
    @patch("app.tasks.llm_client")
    def test_happy_path_ready(self, mock_gemini: MagicMock, mock_db_conn: MagicMock) -> None:
        """Valid LLM output with high confidence → status READY."""
        from app.tasks import parse_with_llm

        # Mock DB connection
        mock_db = MagicMock()
        mock_db_conn.return_value = mock_db
        mock_cursor = MagicMock()
        mock_db.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_db.cursor.return_value.__exit__ = MagicMock(return_value=False)

        # Mock fetchone returns raw_scraped_data
        mock_cursor.fetchone.return_value = {"raw_scraped_data": SAMPLE_RAW_DATA}

        # Mock Gemini returns valid JSON
        mock_gemini.generate_json.return_value = valid_llm_json()

        # Execute (use .run() to bypass Celery machinery)
        parse_with_llm.run(
            property_id="prop-123",
            property_report_id="report-456",
            address_string=SAMPLE_ADDRESS,
        )

        # Verify DB updates were made
        calls = mock_cursor.execute.call_args_list
        assert len(calls) >= 3  # PROCESSING_LLM, SELECT, final UPDATE

        last_update_params = _report_update_params(mock_cursor)
        # status param should be READY (high confidence output)
        assert "READY" in last_update_params or any(
            p == "READY" for p in last_update_params if isinstance(p, str)
        )

    @patch("app.tasks.get_db_connection")
    @patch("app.tasks.llm_client")
    def test_low_confidence_still_publishes_ready(
        self, mock_gemini: MagicMock, mock_db_conn: MagicMock
    ) -> None:
        """Low confidence output still publishes as READY."""
        from tests.conftest import low_confidence_llm_json

        from app.tasks import parse_with_llm

        mock_db = MagicMock()
        mock_db_conn.return_value = mock_db
        mock_cursor = MagicMock()
        mock_db.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_db.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchone.return_value = {"raw_scraped_data": SAMPLE_RAW_DATA}

        mock_gemini.generate_json.return_value = low_confidence_llm_json()

        parse_with_llm.run(
            property_id="prop-123",
            property_report_id="report-456",
            address_string=SAMPLE_ADDRESS,
        )

        # Final UPDATE should set status to READY; review queue was removed.
        last_update_params = _report_update_params(mock_cursor)
        assert "READY" in last_update_params or any(
            p == "READY" for p in last_update_params if isinstance(p, str)
        )

    @patch("app.tasks.get_db_connection")
    @patch("app.tasks.llm_client")
    def test_invalid_llm_json_causes_retry(
        self, mock_gemini: MagicMock, mock_db_conn: MagicMock
    ) -> None:
        """Invalid JSON from Gemini → task retries."""
        from app.tasks import parse_with_llm

        mock_db = MagicMock()
        mock_db_conn.return_value = mock_db
        mock_cursor = MagicMock()
        mock_db.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_db.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchone.return_value = {"raw_scraped_data": SAMPLE_RAW_DATA}

        mock_gemini.generate_json.return_value = '{"invalid": "json structure"}'

        # Task should raise (which triggers Celery retry in production)
        with pytest.raises(Exception):
            parse_with_llm.run(
                property_id="prop-123",
                property_report_id="report-456",
                address_string=SAMPLE_ADDRESS,
            )

    @patch("app.tasks.get_db_connection")
    @patch("app.tasks.llm_client")
    def test_rate_limit_triggers_retry(
        self, mock_gemini: MagicMock, mock_db_conn: MagicMock
    ) -> None:
        """RATE_LIMIT error from Gemini → task retries via Celery."""
        from app.tasks import parse_with_llm

        mock_db = MagicMock()
        mock_db_conn.return_value = mock_db
        mock_cursor = MagicMock()
        mock_db.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_db.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchone.return_value = {"raw_scraped_data": SAMPLE_RAW_DATA}

        mock_gemini.generate_json.side_effect = RuntimeError("RATE_LIMIT: 429 Too Many Requests")

        # The task calls self.retry() which raises Retry in production.
        # Running with .run() bypasses the Celery retry mechanism, so it raises RuntimeError
        with pytest.raises(Exception, match="RATE_LIMIT"):
            parse_with_llm.run(
                property_id="prop-123",
                property_report_id="report-456",
                address_string=SAMPLE_ADDRESS,
            )

    @patch("app.tasks.get_db_connection")
    @patch("app.tasks.llm_client")
    def test_no_report_found_raises(
        self, mock_gemini: MagicMock, mock_db_conn: MagicMock
    ) -> None:
        """Missing report row → ValueError."""
        from app.tasks import parse_with_llm

        mock_db = MagicMock()
        mock_db_conn.return_value = mock_db
        mock_cursor = MagicMock()
        mock_db.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_db.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchone.return_value = None

        with pytest.raises(Exception, match="No report found"):
            parse_with_llm.run(
                property_id="prop-123",
                property_report_id="report-456",
                address_string=SAMPLE_ADDRESS,
            )

    @patch("app.tasks.get_db_connection")
    @patch("app.tasks.llm_client")
    def test_stores_model_version(
        self, mock_gemini: MagicMock, mock_db_conn: MagicMock
    ) -> None:
        """The llm_model_version column should be set from config."""
        from app.config import settings
        from app.tasks import parse_with_llm

        mock_db = MagicMock()
        mock_db_conn.return_value = mock_db
        mock_cursor = MagicMock()
        mock_db.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_db.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchone.return_value = {"raw_scraped_data": SAMPLE_RAW_DATA}
        mock_gemini.generate_json.return_value = valid_llm_json()

        parse_with_llm.run(
            property_id="prop-123",
            property_report_id="report-456",
            address_string=SAMPLE_ADDRESS,
        )

        # Check model version is in the final UPDATE params
        last_update_params = _report_update_params(mock_cursor)
        assert settings.OPENAI_MODEL in last_update_params

    @patch("app.tasks.get_db_connection")
    @patch("app.tasks.llm_client")
    def test_upserts_parsed_insights_as_json(
        self, mock_gemini: MagicMock, mock_db_conn: MagicMock
    ) -> None:
        """llm_parsed_insights should be stored as valid JSON string."""
        from app.tasks import parse_with_llm

        mock_db = MagicMock()
        mock_db_conn.return_value = mock_db
        mock_cursor = MagicMock()
        mock_db.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_db.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchone.return_value = {"raw_scraped_data": SAMPLE_RAW_DATA}
        mock_gemini.generate_json.return_value = valid_llm_json()

        parse_with_llm.run(
            property_id="prop-123",
            property_report_id="report-456",
            address_string=SAMPLE_ADDRESS,
        )

        last_update_params = _report_update_params(mock_cursor)
        # First param should be the JSON-serialised insights
        insights_json = last_update_params[0]
        parsed = json.loads(insights_json)
        assert "zoning_and_planning" in parsed
        assert "risk_factors" in parsed

    @patch("app.tasks.get_db_connection")
    @patch("app.tasks.llm_client")
    def test_accepts_markdown_fenced_json(
        self, mock_gemini: MagicMock, mock_db_conn: MagicMock
    ) -> None:
        """Markdown fenced JSON should be cleaned and parsed successfully."""
        from app.tasks import parse_with_llm

        mock_db = MagicMock()
        mock_db_conn.return_value = mock_db
        mock_cursor = MagicMock()
        mock_db.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_db.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchone.return_value = {"raw_scraped_data": SAMPLE_RAW_DATA}

        fenced = f"```json\n{valid_llm_json()}\n```"
        mock_gemini.generate_json.return_value = fenced

        parse_with_llm.run(
            property_id="prop-123",
            property_report_id="report-456",
            address_string=SAMPLE_ADDRESS,
        )

        last_update_params = _report_update_params(mock_cursor)
        insights_json = last_update_params[0]
        parsed = json.loads(insights_json)
        assert "zoning_and_planning" in parsed


class TestCheckDlqTask:
    """Test the scheduled DLQ checker task."""

    @patch("app.tasks.get_db_connection")
    def test_no_stuck_reports(self, mock_db_conn: MagicMock) -> None:
        """When no stuck reports exist, should return retried=0."""
        from app.tasks import check_dlq

        mock_db = MagicMock()
        mock_db_conn.return_value = mock_db
        mock_cursor = MagicMock()
        mock_db.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_db.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchall.return_value = []
        mock_cursor.rowcount = 0

        result = check_dlq.run()
        assert result["retried"] == 0
        assert result["failed"] == 0

    @patch("app.tasks.parse_with_llm")
    @patch("app.tasks.get_db_connection")
    def test_retries_stuck_reports(
        self, mock_db_conn: MagicMock, mock_parse_task: MagicMock
    ) -> None:
        """Stuck PROCESSING_LLM reports should be reset and re-dispatched."""
        from app.tasks import check_dlq

        mock_db = MagicMock()
        mock_db_conn.return_value = mock_db
        mock_cursor = MagicMock()
        mock_db.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_db.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchall.return_value = [
            {
                "report_id": "rpt-1",
                "property_id": "prop-1",
                "address_string": "1 Test St",
            },
        ]
        mock_cursor.rowcount = 0

        result = check_dlq.run()
        assert result["retried"] == 1
        assert result["failed"] == 0
        mock_parse_task.apply_async.assert_called_once()


class TestTriggerStateRefreshTask:
    """Test the monthly state refresh task."""

    @patch("app.tasks.celery_app")
    @patch("app.tasks.get_db_connection")
    def test_dispatches_scrape_tasks(
        self, mock_db_conn: MagicMock, mock_celery: MagicMock
    ) -> None:
        """Should query properties and dispatch scrape tasks."""
        from app.tasks import trigger_state_refresh

        mock_db = MagicMock()
        mock_db_conn.return_value = mock_db
        mock_cursor = MagicMock()
        mock_db.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_db.cursor.return_value.__exit__ = MagicMock(return_value=False)
        rows = [
            {
                "property_id": "p1",
                "gnaf_pid": "GAVIC001",
                "address_string": "1 Test St, Melbourne VIC 3000",
                "latitude": -37.8,
                "longitude": 144.96,
                "lga_name": "Melbourne",
                "state": "VIC",
            },
            {
                "property_id": "p2",
                "gnaf_pid": "GAVIC002",
                "address_string": "2 Test St, Melbourne VIC 3000",
                "latitude": -37.81,
                "longitude": 144.97,
                "lga_name": "Melbourne",
                "state": "VIC",
            },
        ]
        mock_cursor.__iter__.return_value = iter(rows)

        result = trigger_state_refresh.run(state="VIC")

        assert result["state"] == "VIC"
        assert result["dispatched"] == 2
        assert mock_celery.send_task.call_count == 2

        # Verify task name and queue
        first_call = mock_celery.send_task.call_args_list[0]
        assert first_call[0][0] == "scraper_worker.tasks.scrape_property"
        assert first_call[1]["queue"] == "data_acquisition_queue"
