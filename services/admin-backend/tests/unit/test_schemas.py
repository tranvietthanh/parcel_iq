import pytest
from pydantic import ValidationError

from app.schemas.scrape import ScrapeRequest, ScrapeResponse
from app.schemas.reports import ReportDeletePdfResponse, ReportPdfResponse
from app.schemas.data_sources import DataSourceCreate
from app.schemas.queue import QueueControlRequest


def test_scrape_request_valid():
    """Valid scrape request should pass validation."""
    req = ScrapeRequest(
        scope="STATE",
        state="VIC",
        priority="HIGH",
        mode="FORCE_ALL",
    )
    assert req.scope == "STATE"
    assert req.state == "VIC"
    assert req.priority == "HIGH"


def test_scrape_request_invalid_scope():
    """Invalid scope should raise validation error."""
    with pytest.raises(ValidationError):
        ScrapeRequest(scope="INVALID")


def test_scrape_response():
    """Scrape response should serialize correctly."""
    resp = ScrapeResponse(
        jobs_queued=42,
        estimated_completion_minutes=21,
        message="Test message",
    )
    assert resp.jobs_queued == 42
    assert resp.dry_run is False


def test_report_pdf_response():
    """Report PDF response should validate correctly."""
    req = ReportPdfResponse(
        report_id="report-123",
        property_id="property-123",
        mode="full",
        filename="report.pdf",
        generated=True,
        pdf_base64="ZmFrZQ==",
    )
    assert req.content_type == "application/pdf"
    assert req.mode == "full"


def test_report_delete_pdf_response():
    """Report PDF deletion response should validate correctly."""
    req = ReportDeletePdfResponse(
        report_id="report-123",
        property_id="property-123",
        mode="all",
        deleted=["full", "lite"],
        message="Deleted cached PDFs.",
    )
    assert req.deleted == ["full", "lite"]


def test_data_source_create():
    """Data source creation should validate URL."""
    req = DataSourceCreate(
        state="VIC",
        lga_name="Melbourne",
        adapter_name="VictoriaPlanningAdapter",
        base_url="https://example.com/api",
        enabled=True,
    )
    assert str(req.base_url) == "https://example.com/api"


def test_queue_control_request():
    """Queue control request should validate action."""
    req = QueueControlRequest(action="PAUSE", queue_name="data_acquisition_queue")
    assert req.action == "PAUSE"
    assert req.queue_name == "data_acquisition_queue"


def test_queue_control_invalid_action():
    """Invalid action should raise validation error."""
    with pytest.raises(ValidationError):
        QueueControlRequest(action="INVALID_ACTION")
