from pydantic import BaseModel


class GeminiQuotaStats(BaseModel):
    """LLM API quota statistics. Field name kept as `gemini_quota` for admin-web compatibility."""

    used_today: int
    daily_limit: int
    remaining: int
    reset_time: str  # ISO 8601 format: "2026-03-01T00:00:00Z"


class DashboardStats(BaseModel):
    """Statistics for the admin dashboard."""

    total_properties: int
    reports_ready: int
    awaiting_review: int
    failed_7d: int
    lga_coverage: int
    sales_mtd: int
    revenue_mtd: float
    gemini_quota: GeminiQuotaStats
