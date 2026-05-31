"""Pydantic schemas for property endpoints."""

from pydantic import BaseModel
from datetime import datetime
from typing import Literal


class PropertyListItem(BaseModel):
    """Property list item for browser view."""
    
    id: str
    gnaf_pid: str
    address_string: str
    state: str
    lga_name: str | None
    last_scraped_at: datetime | None
    scrape_status: str  # NEVER_SCRAPED, UP_TO_DATE, NEEDS_REFRESH, FAILED
    report_status: str | None  # QUEUING, PROCESSING, READY, FAILED
    overall_confidence: Literal["HIGH", "MEDIUM", "LOW"] | None


class PropertyDetail(BaseModel):
    """Full property details."""
    
    id: str
    gnaf_pid: str
    address_string: str
    state: str
    lga_name: str | None
    suburb_name: str | None
    latitude: float
    longitude: float
    beds: int | None
    baths: int | None
    cars: int | None
    land_size_sqm: int | None
    estimated_value: float | None
    estimated_rent: float | None
    last_scraped_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PropertyReport(BaseModel):
    """Property report (lite or full)."""
    
    id: str
    property_id: str
    status: str
    overall_confidence: Literal["HIGH", "MEDIUM", "LOW"] | None
    raw_scraped_data: dict | None
    llm_parsed_insights: dict | None
    created_at: datetime
    updated_at: datetime


class PropertyReportListItem(BaseModel):
    """Property report list item for property detail history."""

    id: str
    property_id: str
    status: str
    overall_confidence: Literal["HIGH", "MEDIUM", "LOW"] | None
    is_purchased: bool
    can_delete: bool
    created_at: datetime
    updated_at: datetime


class TriggerScrapeRequest(BaseModel):
    """Request to trigger scrape for a single property."""
    
    priority: str = "NORMAL"  # NORMAL or HIGH
    mode: str = "FORCE_ALL"   # Always force for single property scrapes


class TriggerScrapeResponse(BaseModel):
    """Response from triggering scrape."""
    
    property_id: str
    task_id: str | None
    message: str


class DeletePropertyReportResponse(BaseModel):
    """Response from deleting a property report."""

    property_id: str
    report_id: str
    message: str
