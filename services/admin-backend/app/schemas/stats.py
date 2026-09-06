from pydantic import BaseModel


class LlmQuotaStats(BaseModel):
    """LLM API quota statistics."""

    used_today: int
    daily_limit: int
    remaining: int
    reset_time: str  # ISO 8601 format: "2026-03-01T00:00:00Z"


GeminiQuotaStats = LlmQuotaStats  # Backward-compatible alias


class DashboardStats(BaseModel):
    """Statistics for the admin dashboard."""

    total_properties: int
    reports_ready: int
    awaiting_review: int
    failed_7d: int
    lga_coverage: int
    sales_mtd: int
    revenue_mtd: float
    llm_quota: LlmQuotaStats
    gemini_quota: LlmQuotaStats  # Deprecated alias kept for rollout compatibility
