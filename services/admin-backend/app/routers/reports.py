from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from asyncpg import Connection
from datetime import datetime, UTC
from uuid import UUID
import json
import base64
from typing import Literal

from app.dependencies import get_db
from app.core.service_auth import verify_service_token
from app.schemas.reports import (
    ReportListItem,
    ReportPdfResponse,
    ReportDeletePdfResponse,
)
from pdf_renderer import (
    generate_report_pdf_bytes,
    build_report_pdf_object_key,
    delete_report_pdf,
    get_report_pdf_bytes,
    put_report_pdf_bytes,
    report_pdf_exists,
)

router = APIRouter(
    prefix="/reports",
    tags=["reports"],
    dependencies=[Depends(verify_service_token)],
)


@router.get("", response_model=list[ReportListItem])
async def list_reports(
    status: str | None = None,
    state: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: Connection = Depends(get_db),
) -> list[ReportListItem]:
    """List property reports with optional filters by status and state."""
    conditions = []
    params = []
    
    if status:
        conditions.append(f"pr.status = ${len(params) + 1}")
        params.append(status)
    

    if state:
        conditions.append(f"p.state = ${len(params) + 1}")
        params.append(state)
    
    where_clause = " AND ".join(conditions) if conditions else "TRUE"
    
    query = f"""
        SELECT 
            pr.id::text,
            pr.property_id::text,
            p.address_string AS property_address,
            pr.status,
            pr.overall_confidence,
            pr.updated_at,
            p.state
        FROM property_reports pr
        JOIN properties p ON p.id = pr.property_id
        WHERE {where_clause}
        ORDER BY pr.updated_at DESC
        LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
    """
    params.extend([limit, offset])
    
    rows = await db.fetch(query, *params)
    return [ReportListItem(**dict(row)) for row in rows]


@router.get("/{report_id}")
async def get_report_detail(
    report_id: str,
    db: Connection = Depends(get_db),
):
    """
    Get full details for a single report.
    
    Returns raw scraped data, LLM insights, and metadata.
    """
    row = await db.fetchrow(
        """
        SELECT 
            pr.*,
            p.address_string,
            p.state,
            sz.name as lga_name
        FROM property_reports pr
        JOIN properties p ON p.id = pr.property_id
        LEFT JOIN spatial_zones sz ON p.lga_id = sz.id
        WHERE pr.id = $1
        """,
        UUID(report_id),
    )
    
    if not row:
        raise HTTPException(status_code=404, detail="Report not found")
    
    return dict(row)


@router.get("/{report_id}/pdf", response_model=ReportPdfResponse)
async def get_report_pdf(
    report_id: str,
    mode: Literal["full", "lite"] = Query("full"),
    db: Connection = Depends(get_db),
):
    """Get PDF for a property report.

    Returns cached PDF from MinIO if present; otherwise generates from
    llm_parsed_insights, stores in MinIO, and returns the new PDF.
    """
    row = await db.fetchrow(
        """
        SELECT
            pr.id::text AS report_id,
            pr.property_id::text AS property_id,
            pr.llm_parsed_insights,
            pr.raw_scraped_data,
            p.address_string,
            ST_Y(p.geom::geometry) AS latitude,
            ST_X(p.geom::geometry) AS longitude
        FROM property_reports pr
        JOIN properties p ON p.id = pr.property_id
        WHERE pr.id = $1
        """,
        UUID(report_id),
    )

    if not row:
        raise HTTPException(status_code=404, detail="Report not found")

    llm_parsed_insights = row["llm_parsed_insights"]
    if not llm_parsed_insights:
        raise HTTPException(
            status_code=400,
            detail="Report has no parsed insights yet; cannot generate PDF",
        )

    if isinstance(llm_parsed_insights, str):
        try:
            llm_parsed_insights = json.loads(llm_parsed_insights)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=500,
                detail="Report insights payload is invalid JSON",
            ) from exc

    if not isinstance(llm_parsed_insights, dict):
        raise HTTPException(
            status_code=500,
            detail="Report insights payload must be a JSON object",
        )

    raw_scraped_data = row["raw_scraped_data"]
    if isinstance(raw_scraped_data, str):
        try:
            raw_scraped_data = json.loads(raw_scraped_data)
        except json.JSONDecodeError:
            raw_scraped_data = None

    if isinstance(raw_scraped_data, dict):
        demographics = raw_scraped_data.get("demographics") or {}
        time_series = demographics.get("time_series")
        if isinstance(time_series, dict) and time_series:
            llm_parsed_insights["_raw_demographics_time_series"] = time_series

    if row["latitude"] is not None and row["longitude"] is not None:
        llm_parsed_insights["_property_location"] = {
            "latitude": float(row["latitude"]),
            "longitude": float(row["longitude"]),
        }

    object_key = build_report_pdf_object_key(report_id, mode)
    filename = f"property-report-{report_id}-{mode}.pdf"
    generated = False

    exists = await run_in_threadpool(report_pdf_exists, object_key)
    if exists:
        pdf_bytes = await run_in_threadpool(get_report_pdf_bytes, object_key)
    else:
        generated = True
        pdf_bytes = await run_in_threadpool(
            generate_report_pdf_bytes,
            llm_parsed_insights,
            row["address_string"] or "",
            mode,
        )
        await run_in_threadpool(put_report_pdf_bytes, object_key, pdf_bytes)

    return ReportPdfResponse(
        report_id=row["report_id"],
        property_id=row["property_id"],
        mode=mode,
        filename=filename,
        generated=generated,
        content_type="application/pdf",
        pdf_base64=base64.b64encode(pdf_bytes).decode("utf-8"),
    )


@router.delete("/{report_id}/pdf", response_model=ReportDeletePdfResponse)
async def delete_report_pdf_cache(
    report_id: str,
    mode: Literal["full", "lite", "all"] = Query("all"),
    db: Connection = Depends(get_db),
):
    """Delete cached PDF object(s) for a property report from MinIO."""
    row = await db.fetchrow(
        """
        SELECT
            pr.id::text AS report_id,
            pr.property_id::text AS property_id
        FROM property_reports pr
        WHERE pr.id = $1
        """,
        UUID(report_id),
    )

    if not row:
        raise HTTPException(status_code=404, detail="Report not found")

    variants = ["full", "lite"] if mode == "all" else [mode]
    deleted: list[str] = []

    try:
        for variant in variants:
            object_key = build_report_pdf_object_key(report_id, variant)
            await run_in_threadpool(delete_report_pdf, object_key)
            deleted.append(variant)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Failed to delete cached report PDF",
        ) from exc

    return ReportDeletePdfResponse(
        report_id=row["report_id"],
        property_id=row["property_id"],
        mode=mode,
        deleted=deleted,
        message="Cached report PDF deleted",
    )



