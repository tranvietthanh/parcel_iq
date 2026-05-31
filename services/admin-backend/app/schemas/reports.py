from typing import Any, Literal
from datetime import datetime
from pydantic import BaseModel, Field


class ReportListItem(BaseModel):
    """Single report in the list view."""

    id: str
    property_id: str
    property_address: str
    status: str
    overall_confidence: Literal["HIGH", "MEDIUM", "LOW"] | None

    updated_at: datetime
    state: str | None



class ReportPdfResponse(BaseModel):
    """Base64-encoded PDF payload for a specific property report."""

    report_id: str
    property_id: str
    mode: str
    filename: str
    generated: bool
    content_type: str = "application/pdf"
    pdf_base64: str


class ReportDeletePdfResponse(BaseModel):
    """Response payload after deleting cached report PDFs."""

    report_id: str
    property_id: str
    mode: str
    deleted: list[str]
    message: str
