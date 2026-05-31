"""Admin endpoints for property management."""

from fastapi import APIRouter, HTTPException, Depends
from fastapi.concurrency import run_in_threadpool
from typing import Literal
from asyncpg import Connection
import json
from celery.result import AsyncResult

from app.celery import celery_app
from app.dependencies import get_db
from app.core.service_auth import verify_service_token
from app.schemas.properties import (
    PropertyListItem,
    PropertyDetail,
    PropertyReport,
    PropertyReportListItem,
    TriggerScrapeRequest,
    TriggerScrapeResponse,
    DeletePropertyReportResponse,
)
from app.services.report_pdf_storage import build_report_pdf_object_key, delete_report_pdf

router = APIRouter(
    prefix="/properties",
    tags=["properties"],
    dependencies=[Depends(verify_service_token)],
)


async def _resolve_lga_if_missing(db: Connection, property_id: str) -> None:
    """Resolve and persist ``properties.lga_id`` from geometry when missing."""
    await db.execute(
        """
        UPDATE properties p
        SET lga_id = sz.id,
            updated_at = NOW()
        FROM spatial_zones sz
        WHERE p.id = $1
          AND p.lga_id IS NULL
          AND p.geom IS NOT NULL
          AND sz.zone_type = 'LGA'
          AND ST_Contains(sz.geom, p.geom)
        """,
        property_id,
    )

@router.get("", response_model=list[PropertyListItem])
async def get_properties(
    db: Connection = Depends(get_db),
    state: str | None = None,
    lga_id: str | None = None,
    status: str | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    """
    Get paginated list of properties with filters.
    
    Filters:
    - state: Filter by state code (VIC, NSW, etc.)
    - lga_id: Filter by LGA ID
    - status: Filter by report status (QUEUING, PROCESSING, READY, FAILED)
    - search: Search in address string
    - limit: Max results (default 50, max 200)
    - offset: Pagination offset
    """
    # Limit validation
    if limit > 200:
        limit = 200
    if limit < 1:
        limit = 1
    
    # Build WHERE clause
    where_clauses = []
    params = []
    param_idx = 1
    
    if state:
        where_clauses.append(f"p.state = ${param_idx}")
        params.append(state.upper())
        param_idx += 1
    
    if lga_id:
        where_clauses.append(f"p.lga_id = ${param_idx}")
        params.append(lga_id)
        param_idx += 1
    
    if status:
        where_clauses.append(f"pr.status = ${param_idx}")
        params.append(status.upper())
        param_idx += 1


    if search:
        where_clauses.append(f"p.address_string ILIKE ${param_idx}")
        params.append(f"%{search}%")
        param_idx += 1
    
    where_clause = " AND ".join(where_clauses) if where_clauses else "TRUE"
    
    # Add limit and offset params
    params.append(limit)
    params.append(offset)
    
    query = f"""
        SELECT 
            p.id::text,
            p.gnaf_pid,
            p.address_string,
            p.state,
            sz.name AS lga_name,
            p.last_scraped_at,
            CASE
                WHEN p.last_scraped_at IS NULL THEN 'NEVER_SCRAPED'
                WHEN p.last_scraped_at < NOW() - INTERVAL '30 days' THEN 'NEEDS_REFRESH'
                WHEN pr.status = 'FAILED' THEN 'FAILED'
                ELSE 'UP_TO_DATE'
            END AS scrape_status,
            pr.status AS report_status,
            pr.overall_confidence
        FROM properties p
        LEFT JOIN spatial_zones sz ON sz.id = p.lga_id
        -- Join only the latest report per property to avoid duplicate rows
        LEFT JOIN LATERAL (
            SELECT * FROM property_reports pr2
            WHERE pr2.property_id = p.id
            ORDER BY pr2.created_at DESC
            LIMIT 1
        ) pr ON TRUE
        WHERE {where_clause}
        ORDER BY p.last_scraped_at DESC NULLS LAST, p.created_at DESC
        LIMIT ${param_idx} OFFSET ${param_idx + 1}
    """
    
    rows = await db.fetch(query, *params)
    
    return [
        PropertyListItem(
            id=row["id"],
            gnaf_pid=row["gnaf_pid"],
            address_string=row["address_string"],
            state=row["state"],
            lga_name=row["lga_name"],
            last_scraped_at=row["last_scraped_at"],
            scrape_status=row["scrape_status"],
            report_status=row["report_status"],
            overall_confidence=row["overall_confidence"],
        )
        for row in rows
    ]


@router.get("/{property_id}", response_model=PropertyDetail)
async def get_property_detail(
    property_id: str,
    db: Connection = Depends(get_db),
):
    """Get detailed information for a single property."""

    # Thin imports leave lga_id NULL; resolve it lazily on first access.
    await _resolve_lga_if_missing(db, property_id)
    
    query = """
        SELECT 
            p.id::text,
            p.gnaf_pid,
            p.address_string,
            p.state,
            lga.name AS lga_name,
            suburb.name AS suburb_name,
            ST_Y(p.geom::geometry) AS latitude,
            ST_X(p.geom::geometry) AS longitude,
            p.beds,
            p.baths,
            p.cars,
            p.land_size_sqm,
            p.estimated_value,
            p.estimated_rent,
            p.last_scraped_at,
            p.created_at,
            p.updated_at
        FROM properties p
        LEFT JOIN spatial_zones lga ON lga.id = p.lga_id
        LEFT JOIN spatial_zones suburb ON suburb.id = p.suburb_id
        WHERE p.id = $1
    """
    
    row = await db.fetchrow(query, property_id)
    
    if not row:
        raise HTTPException(status_code=404, detail="Property not found")
    
    return PropertyDetail(**dict(row))


@router.get("/{property_id}/report", response_model=PropertyReport)
async def get_property_report(
    property_id: str,
    db: Connection = Depends(get_db),
    mode: Literal["lite", "full"] = "lite"
):
    """
    Get report for a property.
    
    - lite: Excludes raw_scraped_data and llm_insights (faster)
    - full: Includes all data including raw JSONB
    """
    
    # Build SELECT based on mode
    if mode == "lite":
        select_fields = """
            pr.id::text,
            pr.property_id::text,
            pr.status,
            pr.overall_confidence,
            NULL AS raw_scraped_data,
            NULL AS llm_parsed_insights,
            pr.created_at,
            pr.updated_at
        """
    else:
        select_fields = """
            pr.id::text,
            pr.property_id::text,
            pr.status,
            pr.overall_confidence,
            pr.raw_scraped_data,
            pr.llm_parsed_insights,
            pr.created_at,
            pr.updated_at
        """
    
    query = f"""
        SELECT {select_fields}
        FROM property_reports pr
        WHERE pr.property_id = $1
        ORDER BY pr.updated_at DESC
        LIMIT 1
    """
    
    row = await db.fetchrow(query, property_id)
    
    if not row:
        raise HTTPException(status_code=404, detail="No report found for this property")
    
    # Convert row to dict and parse JSONB columns
    data = dict(row)
    
    # Parse JSON strings if needed (asyncpg may return JSONB as strings)
    if data.get("raw_scraped_data") and isinstance(data["raw_scraped_data"], str):
        data["raw_scraped_data"] = json.loads(data["raw_scraped_data"])
    
    if data.get("llm_parsed_insights") and isinstance(data["llm_parsed_insights"], str):
        data["llm_parsed_insights"] = json.loads(data["llm_parsed_insights"])
    
    return PropertyReport(**data)


@router.get("/{property_id}/reports", response_model=list[PropertyReportListItem])
async def get_property_reports(
    property_id: str,
    db: Connection = Depends(get_db),
):
    """Get the canonical report for a property (single report per property).
    
    Returns a single-item list for backward compatibility with admin UI.
    """
    property_exists = await db.fetchval(
        "SELECT 1 FROM properties WHERE id = $1",
        property_id,
    )
    if not property_exists:
        raise HTTPException(status_code=404, detail="Property not found")

    rows = await db.fetch(
        """
        SELECT
            pr.id::text,
            pr.property_id::text,
            pr.status,
            pr.overall_confidence,
            EXISTS(
                SELECT 1
                FROM credit_ledger cl
                WHERE cl.related_property_id = pr.property_id
                  AND cl.entry_type = 'DOWNLOAD_DEBIT'
            ) AS is_downloaded,
            pr.created_at,
            pr.updated_at
        FROM property_reports pr
        WHERE pr.property_id = $1
        LIMIT 1
        """,
        property_id,
    )

    return [
        PropertyReportListItem(
            id=row["id"],
            property_id=row["property_id"],
            status=row["status"],
            overall_confidence=row["overall_confidence"],
            is_purchased=row["is_downloaded"],  # Renamed but kept for schema compat
            can_delete=not row["is_downloaded"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        for row in rows
    ]


@router.delete(
    "/{property_id}/reports/{report_id}",
    response_model=DeletePropertyReportResponse,
)
async def delete_property_report(
    property_id: str,
    report_id: str,
    db: Connection = Depends(get_db),
):
    """Delete a canonical report if it has not been downloaded by any users."""

    report_row = await db.fetchrow(
        """
        SELECT id::text, property_id::text
        FROM property_reports
        WHERE id = $1
          AND property_id = $2
        """,
        report_id,
        property_id,
    )
    if not report_row:
        raise HTTPException(status_code=404, detail="Report not found for this property")

    # Check if any user has downloaded this property
    is_downloaded = bool(
        await db.fetchval(
            "SELECT EXISTS(SELECT 1 FROM credit_ledger WHERE related_property_id = $1 AND entry_type = 'DOWNLOAD_DEBIT')",
            property_id,
        )
    )
    if is_downloaded:
        raise HTTPException(
            status_code=409,
            detail="Cannot delete a report that has been downloaded by users",
        )

    # Delete cached PDFs
    object_keys = [
        build_report_pdf_object_key(report_id, "full"),
        build_report_pdf_object_key(report_id, "lite"),
    ]
    try:
        for object_key in object_keys:
            await run_in_threadpool(delete_report_pdf, object_key)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Failed to delete cached report PDF",
        ) from exc

    # Delete the report row
    await db.execute(
        """
        DELETE FROM property_reports
        WHERE id = $1
          AND property_id = $2
        """,
        report_id,
        property_id,
    )

    return DeletePropertyReportResponse(
        property_id=property_id,
        report_id=report_id,
        message="Report deleted",
    )


@router.post("/{property_id}/force-scrape", response_model=TriggerScrapeResponse)
async def force_scrape_property(
    property_id: str,
    request: TriggerScrapeRequest,
    db: Connection = Depends(get_db),
):
    """
    Trigger a forced re-scrape for a single property.
    
    This will:
    1. Queue a scraper_worker task for this specific property
    2. Set mode=FORCE_ALL to ignore last_scraped_at timestamp
    3. Return the Celery task ID for tracking
    """

    # Thin imports leave lga_id NULL; resolve it lazily before dispatch.
    await _resolve_lga_if_missing(db, property_id)
    
    # Verify property exists and fetch helpful fields to pass to the scraper task
    row = await db.fetchrow(
        """
        SELECT
            p.id::text,
            p.gnaf_pid,
            p.address_string,
            p.state,
            ST_Y(p.geom::geometry) AS latitude,
            ST_X(p.geom::geometry) AS longitude,
            lga.name AS lga_name
        FROM properties p
        LEFT JOIN spatial_zones lga ON lga.id = p.lga_id
        WHERE p.id = $1
        """,
        property_id,
    )
    
    if not row:
        raise HTTPException(status_code=404, detail="Property not found")

    # Ensure the worker always has a canonical report row to transition.
    report_id = await db.fetchval(
        """
        INSERT INTO property_reports (property_id, status)
        VALUES ($1, 'QUEUING')
        ON CONFLICT (property_id) DO UPDATE
        SET status = 'QUEUING',
            raw_scraped_data = NULL,
            llm_parsed_insights = NULL,
            confidence_scores = NULL,
            overall_confidence = NULL,
            error_message = NULL,
            updated_at = NOW()
        RETURNING id
        """,
        property_id,
    )
    
    # Dispatch Celery task; include coordinates and other fields so the
    # scraper task doesn't need to re-query the DB for them.
    task_result = celery_app.send_task(
        "scraper_worker.tasks.scrape_property",
        kwargs={
            "property_id": property_id,
            "gnaf_pid": row.get("gnaf_pid"),
            "address_string": row.get("address_string"),
            "latitude": float(row["latitude"]) if row.get("latitude") is not None else None,
            "longitude": float(row["longitude"]) if row.get("longitude") is not None else None,
            "lga_name": row.get("lga_name"),
            "state": row.get("state"),
            "mode": request.mode,
            "priority": request.priority,
        },
        queue="data_acquisition_queue",
    )
    
    return TriggerScrapeResponse(
        property_id=property_id,
        task_id=task_result.id,
        message=f"Scrape task queued for {row['address_string']}",
    )


@router.post("/{property_id}/re-ai-validate", response_model=TriggerScrapeResponse)
async def re_ai_validate_property(
    property_id: str,
    db: Connection = Depends(get_db),
):
    """Queue LLM parsing again for the latest report of a property."""

    row = await db.fetchrow(
        """
        SELECT
            p.id::text AS property_id,
            p.address_string,
            pr.id::text AS report_id
        FROM properties p
        LEFT JOIN LATERAL (
            SELECT id
            FROM property_reports pr2
            WHERE pr2.property_id = p.id
            ORDER BY pr2.updated_at DESC, pr2.created_at DESC
            LIMIT 1
        ) pr ON TRUE
        WHERE p.id = $1
        """,
        property_id,
    )

    if not row:
        raise HTTPException(status_code=404, detail="Property not found")

    if not row.get("report_id"):
        raise HTTPException(
            status_code=409,
            detail="No report found for this property. Run Re-scrape Property first.",
        )

    task_result = celery_app.send_task(
        "app.tasks.parse_with_llm",
        kwargs={
            "property_id": row["property_id"],
            "property_report_id": row["report_id"],
            "address_string": row["address_string"],
        },
        queue="llm_processing_queue",
    )

    return TriggerScrapeResponse(
        property_id=row["property_id"],
        task_id=task_result.id,
        message=f"AI validation queued for {row['address_string']}",
    )
