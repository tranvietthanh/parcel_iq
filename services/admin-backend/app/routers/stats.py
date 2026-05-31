import time
from datetime import datetime, timezone, timedelta

from asyncpg import Connection
from fastapi import APIRouter, Depends
import redis as redis_lib
from redis.exceptions import RedisError

from app.config import settings
from app.core.service_auth import verify_service_token
from app.dependencies import get_db
from app.schemas.stats import DashboardStats, GeminiQuotaStats

router = APIRouter(
    prefix="/stats",
    tags=["stats"],
    dependencies=[Depends(verify_service_token)],
)

# Initialize Redis client for quota tracking
redis_client = redis_lib.from_url(settings.REDIS_URL, decode_responses=True)


def get_gemini_quota_stats() -> GeminiQuotaStats:
    """Get current LLM quota usage from Redis.

    Kept as `gemini_quota` in the response model for API compatibility with
    the current admin-web client, but values come from the OpenAI worker keys.
    """
    today = time.strftime("%Y-%m-%d")
    key = f"openai:daily_count:{today}"

    daily_limit = settings.OPENAI_DAILY_QUOTA
    try:
        used_today = int(redis_client.get(key) or 0)
    except RedisError:
        # If Redis is unavailable, return a safe default instead of failing
        # the whole dashboard endpoint.
        used_today = 0

    remaining = max(0, daily_limit - used_today)

    # Calculate midnight UTC tomorrow for reset time using timedelta
    tomorrow_midnight = (datetime.now(timezone.utc) + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    reset_time = tomorrow_midnight.isoformat()

    return GeminiQuotaStats(
        used_today=used_today,
        daily_limit=daily_limit,
        remaining=remaining,
        reset_time=reset_time,
    )


@router.get("", response_model=DashboardStats)
async def get_dashboard_stats(db: Connection = Depends(get_db)) -> DashboardStats:
    """
    Get admin dashboard statistics.
    """
    try:
        row = await db.fetchrow("""
            SELECT
                (SELECT COUNT(*) FROM properties)                                    AS total_properties,
                (SELECT COUNT(*) FROM property_reports WHERE status = 'READY')       AS reports_ready,
                (SELECT COUNT(*) FROM property_reports
                  WHERE status IN ('FAILED_SCRAPE', 'FAILED_LLM')
                    AND updated_at > NOW() - INTERVAL '7 days')                     AS failed_7d,
                (SELECT COUNT(DISTINCT lga_id) FROM properties p
                  JOIN property_reports pr ON pr.property_id = p.id
                  WHERE pr.status = 'READY')                                         AS lga_coverage,
                (SELECT COUNT(DISTINCT user_id) FROM credit_ledger
                  WHERE entry_type = 'DOWNLOAD_DEBIT'
                    AND created_at >= date_trunc('month', NOW()))                    AS sales_mtd
        """)
        
        stats_dict = dict(row)
        stats_dict["awaiting_review"] = 0  # review queue removed; kept for dashboard compat
        stats_dict["revenue_mtd"] = 0.0    # payment integration deferred to separate change
        stats_dict["gemini_quota"] = get_gemini_quota_stats().model_dump()
        
        return DashboardStats(**stats_dict)
    except Exception as e:
        from fastapi import HTTPException
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Backend Error: {repr(e)}")
