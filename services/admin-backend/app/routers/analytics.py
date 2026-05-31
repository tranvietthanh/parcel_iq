from fastapi import APIRouter, Depends
from asyncpg import Connection
from datetime import datetime, timedelta

from app.dependencies import get_db
from app.core.service_auth import verify_service_token
from app.schemas.analytics import AnalyticsResponse, DailyStat

router = APIRouter(
    prefix="/analytics",
    tags=["analytics"],
    dependencies=[Depends(verify_service_token)],
)


@router.get("", response_model=AnalyticsResponse)
async def get_analytics(
    days: int = 30,
    db: Connection = Depends(get_db),
) -> AnalyticsResponse:
    """
    Get analytics dashboard data.
    
    Returns daily stats for the last N days, top LGAs by downloads,
    and average processing times.
    """
    # Get daily stats for the last N days
    daily_rows = await db.fetch(
        """
        WITH date_series AS (
            SELECT generate_series(
                CURRENT_DATE - $1::int,
                CURRENT_DATE,
                '1 day'::interval
            )::date AS date
        )
        SELECT 
            ds.date,
            COALESCE(COUNT(DISTINCT pr.id) FILTER (WHERE pr.status = 'READY'), 0) AS reports_completed,
            COALESCE(COUNT(DISTINCT cl.related_property_id), 0) AS reports_unlocked,
            0.0 AS revenue_aud
        FROM date_series ds
        LEFT JOIN property_reports pr ON pr.updated_at::date = ds.date
        LEFT JOIN credit_ledger cl ON cl.created_at::date = ds.date
            AND cl.entry_type = 'DOWNLOAD_DEBIT'
        GROUP BY ds.date
        ORDER BY ds.date
        """,
        days,
    )
    
    daily_stats = [DailyStat(**dict(row)) for row in daily_rows]
    
    # Get top 10 LGAs by download count
    top_lgas = await db.fetch(
        """
        SELECT 
            sz.name AS lga_name,
            sz.state,
            COUNT(DISTINCT cl.related_property_id) AS unlock_count
        FROM credit_ledger cl
        JOIN properties p ON p.id = cl.related_property_id
        JOIN spatial_zones sz ON sz.id = p.lga_id
        WHERE cl.entry_type = 'DOWNLOAD_DEBIT'
          AND cl.created_at >= CURRENT_DATE - $1::int
        GROUP BY sz.id, sz.name, sz.state
        ORDER BY unlock_count DESC
        LIMIT 10
        """,
        days,
    )
    
    top_lgas_list = [dict(row) for row in top_lgas]
    
    # Get average processing times
    avg_times = await db.fetchrow(
        """
        SELECT 
            COALESCE(AVG(
                EXTRACT(EPOCH FROM (updated_at - created_at))
            ) FILTER (WHERE raw_scraped_data IS NOT NULL), 0)::float AS avg_scrape_time_seconds,
            COALESCE(AVG(
                EXTRACT(EPOCH FROM (updated_at - created_at))
            ) FILTER (WHERE llm_parsed_insights IS NOT NULL), 0)::float AS avg_llm_time_seconds
        FROM property_reports
        WHERE updated_at >= CURRENT_DATE - $1::int
        """,
        days,
    )
    
    return AnalyticsResponse(
        daily_stats=daily_stats,
        top_lgas_by_unlocks=top_lgas_list,
        avg_scrape_time_seconds=avg_times["avg_scrape_time_seconds"],
        avg_llm_time_seconds=avg_times["avg_llm_time_seconds"],
    )
