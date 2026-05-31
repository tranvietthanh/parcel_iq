from typing import Literal
from pydantic import BaseModel, Field


class ScrapeRequest(BaseModel):
    """Request body for triggering a scrape job."""

    scope: Literal["STATE", "LGA", "POSTCODE"]
    state: Literal["VIC", "NSW", "QLD", "SA", "WA", "TAS", "ACT", "NT"] | None = None
    lga: str | None = None
    postcode: str | None = None
    priority: Literal["NORMAL", "HIGH"] = "NORMAL"
    mode: Literal["STALE_ONLY", "FORCE_ALL"] = "STALE_ONLY"
    dry_run: bool = False


class ScrapeResponse(BaseModel):
    """Response from triggering a scrape job."""

    dry_run: bool = False
    jobs_queued: int
    estimated_completion_minutes: int | None = None
    message: str
