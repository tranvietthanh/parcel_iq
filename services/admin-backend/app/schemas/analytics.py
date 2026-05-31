from datetime import date
from pydantic import BaseModel


class DailyStat(BaseModel):
    """Single day's metrics."""

    date: date
    reports_completed: int
    reports_unlocked: int
    revenue_aud: float


class AnalyticsResponse(BaseModel):
    """Analytics dashboard data."""

    daily_stats: list[DailyStat]
    top_lgas_by_unlocks: list[dict[str, str | int]]  # {lga_name, state, unlock_count}
    avg_scrape_time_seconds: float
    avg_llm_time_seconds: float
