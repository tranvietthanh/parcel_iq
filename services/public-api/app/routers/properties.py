"""Property endpoints — detail payload + PDF downloads.

GET /api/properties/{property_id}/detail  — curated detail sections
POST /api/properties/{property_id}/request-scrape  — request property scrape
GET /api/properties/{property_id}/lite-report/pdf  — lite report PDF download
GET /api/properties/{property_id}/full/pdf  — full report PDF download (auth + credits)
"""

from __future__ import annotations

import json
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from pdf_renderer import (
    generate_report_pdf_bytes,
    generate_lite_pdf_bytes,
    build_report_pdf_object_key,
    get_report_pdf_bytes,
    put_report_pdf_bytes,
    report_pdf_exists,
)

import uuid

from app.core.credits import debit_credit, get_spendable_credits
from app.core.rate_limit import limiter
from app.middleware.turnstile import verify_turnstile
from app.celery import celery_app
from app.dependencies import get_current_user, get_db, get_optional_user, require_credits_available
from app.routers.my_properties import get_or_create_anon_id
from app.schemas.property import (
    PropertyDetail,
)
from app.schemas.user import UserRow

router = APIRouter(tags=["properties"])

# ── SQL ───────────────────────────────────────────────────────────────────────

PROPERTY_LITE_QUERY = """
    SELECT p.*, pr.id::text AS report_id, pr.status AS report_status, pr.llm_parsed_insights, pr.raw_scraped_data
    FROM properties p
    LEFT JOIN LATERAL (
        SELECT id, status, llm_parsed_insights, raw_scraped_data
        FROM property_reports
        WHERE property_id = p.id
        ORDER BY created_at DESC LIMIT 1
    ) pr ON TRUE
    WHERE p.id = $1
"""

FULL_REPORT_QUERY = """
    SELECT p.*, 
        ST_Y(p.geom::geometry) AS latitude,
        ST_X(p.geom::geometry) AS longitude,
        pr.id::text AS report_id,
        pr.status AS report_status, pr.llm_parsed_insights,
        pr.raw_scraped_data, pr.confidence_scores, pr.overall_confidence,
        pr.created_at
    FROM properties p
    LEFT JOIN LATERAL (
        SELECT id, status, llm_parsed_insights, raw_scraped_data,
               confidence_scores, overall_confidence, created_at
        FROM property_reports
        WHERE property_id = p.id
        ORDER BY created_at DESC
        LIMIT 1
    ) pr ON TRUE
    WHERE p.id = $1
"""

DETAIL_QUERY = """
    SELECT p.id, p.address_string, p.state, p.slug,
        ST_Y(p.geom) AS latitude,
        ST_X(p.geom) AS longitude,
        pr.status AS report_status,
        pr.llm_parsed_insights,
        pr.raw_scraped_data
    FROM properties p
    LEFT JOIN LATERAL (
        SELECT status, llm_parsed_insights, raw_scraped_data, created_at
        FROM property_reports
        WHERE property_id = p.id
        ORDER BY created_at DESC
        LIMIT 1
    ) pr ON TRUE
    WHERE p.id = $1
"""


# ── Routes ────────────────────────────────────────────────────────────────────


@router.get("/{property_id}/lite-report/pdf")
@limiter.limit("100/hour")
async def lite_report_pdf(
    request: Request,
    property_id: UUID,
    db: asyncpg.Connection = Depends(get_db),
) -> StreamingResponse:
    """Generate and stream a lite report PDF with raw scraped data.

    Checks MinIO for cached PDF first; if not found, generates and caches it.
    Uses the same comprehensive template as full reports, but with raw data only.
    """
    await verify_turnstile(request)
    row = await db.fetchrow(PROPERTY_LITE_QUERY, property_id)
    if not row:
        raise HTTPException(status_code=404, detail="Property not found.")

    # Extract raw scraped data
    raw_scraped = _normalize_insights(row.get("raw_scraped_data"))
    
    if not raw_scraped:
        raise HTTPException(
            status_code=400,
            detail="Property has no scraped data yet. Request a scrape to generate a lite report.",
        )

    report_id = row.get("report_id")
    if not report_id:
        raise HTTPException(
            status_code=400,
            detail="Property report metadata is missing; cannot resolve PDF cache key.",
        )

    # Check MinIO cache first
    object_key = build_report_pdf_object_key(str(report_id), "lite")
    exists = await run_in_threadpool(report_pdf_exists, object_key)
    
    if exists:
        # Return cached PDF from MinIO
        pdf_data = await run_in_threadpool(get_report_pdf_bytes, object_key)
    else:
        # Generate PDF using the dedicated lite template for raw data
        pdf_data = await run_in_threadpool(
            generate_lite_pdf_bytes,
            raw_data=raw_scraped,
            address=row["address_string"] or "Property Report",
        )
        
        # Cache in MinIO for future requests
        await run_in_threadpool(put_report_pdf_bytes, object_key, pdf_data)

    # Return as streaming PDF response
    return StreamingResponse(
        iter([pdf_data]),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="property-report-{report_id}-lite.pdf"',
        },
    )


async def _get_property_detail(property_id: UUID, db: asyncpg.Connection) -> PropertyDetail:
    """Helper to fetch and format PropertyDetail."""
    row = await db.fetchrow(DETAIL_QUERY, property_id)
    if not row:
        raise HTTPException(status_code=404, detail="Property not found.")

    insights = _normalize_insights(row.get("llm_parsed_insights")) or {}
    raw_scraped = _normalize_insights(row.get("raw_scraped_data")) or {}

    detail_sections = _build_detail_sections(insights, raw_scraped)

    return PropertyDetail(
        id=row["id"],
        address=row["address_string"],
        state=row["state"],
        slug=row["slug"],
        report_status=row["report_status"],
        latitude=row["latitude"],
        longitude=row["longitude"],
        education=detail_sections["education"],
        connectivity=detail_sections["connectivity"],
        risk_factors=detail_sections["risk_factors"],
        zoning_and_planning=detail_sections["zoning_and_planning"],
        demographic_snapshot=detail_sections["demographic_snapshot"],
    )


@router.get("/slug/{slug}/detail")
@limiter.limit("200/hour")
async def property_detail_by_slug(
    request: Request,
    slug: str,
    db: asyncpg.Connection = Depends(get_db),
) -> PropertyDetail:
    """Resolve property by slug and return detail payload."""
    row = await db.fetchrow("SELECT id FROM properties WHERE slug = $1", slug)
    if not row:
        raise HTTPException(status_code=404, detail="Property not found.")
    return await _get_property_detail(row["id"], db)


@router.get("/{property_id}/detail")
@limiter.limit("200/hour")
async def property_detail(
    request: Request,
    property_id: UUID,
    db: asyncpg.Connection = Depends(get_db),
) -> PropertyDetail:
    """Curated property detail payload.

    Extraction order is LLM-first and falls back to raw scraped data when
    the LLM section is missing. Only returns relevant section data.
    """
    return await _get_property_detail(property_id, db)


@router.get("/{property_id}/full/pdf")
@limiter.limit("60/hour")
async def property_full_pdf(
    request: Request,
    property_id: UUID,
    current_user: UserRow = Depends(require_credits_available),
    db: asyncpg.Connection = Depends(get_db),
) -> StreamingResponse:
    """Download full property report as PDF — requires login + 1 spendable credit.

    Flow:
    1. Pre-flight credit check (non-locking, advisory).
    2. Validate report is READY and has parsed insights.
    3. Retrieve or generate the PDF.
    4. Atomically debit 1 credit (daily first, then purchased).
    5. Stream PDF to client.

    If the atomic debit fails (race: credits drained by concurrent session
    between steps 1 and 4) the request returns 403 and the PDF is not streamed.
    Once the PDF is streaming, the debit is final — no refund mechanism exists.
    """
    # Fetch the report
    row = await db.fetchrow(FULL_REPORT_QUERY, property_id)
    if not row:
        raise HTTPException(status_code=404, detail="Property not found.")

    insights = _normalize_insights(row.get("llm_parsed_insights"))
    if not insights:
        raise HTTPException(
            status_code=400,
            detail="Property has no parsed insights yet. The report may still be processing.",
        )

    report_id = row.get("report_id")
    if not report_id:
        raise HTTPException(
            status_code=400,
            detail="Property report metadata is missing; cannot resolve PDF cache key.",
        )

    # Enrich insights with raw demographics time series if available
    raw_scraped = _normalize_insights(row.get("raw_scraped_data"))
    if raw_scraped and isinstance(raw_scraped.get("demographics"), dict):
        demo = raw_scraped["demographics"]
        if "time_series" in demo:
            insights["_raw_demographics_time_series"] = demo["time_series"]

    # Add location for map enrichment if available
    if row.get("latitude") and row.get("longitude"):
        insights["_property_location"] = {
            "latitude": float(row["latitude"]),
            "longitude": float(row["longitude"]),
        }

    # Check MinIO cache
    object_key = build_report_pdf_object_key(str(report_id), "full")
    exists = await run_in_threadpool(report_pdf_exists, object_key)

    if exists:
        pdf_data = await run_in_threadpool(get_report_pdf_bytes, object_key)
    else:
        pdf_data = await run_in_threadpool(
            generate_report_pdf_bytes,
            data=insights,
            address=row["address_string"] or "Property Report",
            variant="full",
        )
        await run_in_threadpool(put_report_pdf_bytes, object_key, pdf_data)

    # Atomic debit — only after PDF is in hand.
    # The random suffix makes each request unique: this prevents accidental
    # double-submission (e.g. user clicks twice quickly) via ON CONFLICT
    # in the same transaction, while still charging 1 credit for intentional
    # re-downloads of the same report.
    idempotency_key = f"download:{current_user.id}:{report_id}:{uuid.uuid4().hex[:8]}"
    debited = await debit_credit(
        user_id=current_user.id,
        property_id=property_id,
        report_id=uuid.UUID(str(report_id)),
        idempotency_key=idempotency_key,
        db=db,
    )
    if not debited:
        raise HTTPException(
            status_code=403,
            detail=(
                "Insufficient credits. Your balance was updated by a concurrent "
                "session. Please check your credit balance and try again."
            ),
        )

    return StreamingResponse(
        iter([pdf_data]),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="property-report-{report_id}-full.pdf"',
        },
    )


@router.post("/{property_id}/request-scrape")
@limiter.limit("10/hour")
async def request_property_scrape(
    request: Request,
    response: Response,
    property_id: UUID,
    current_user: UserRow | None = Depends(get_optional_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    """Request a property scrape to populate detailed information.

    This endpoint allows users to request scraping of a property if no data exists yet.
    Anonymous users can request scrapes, but authenticated users get higher priority.

    Returns the current report status and task ID if a new scrape was queued.
    """
    await verify_turnstile(request)

    # Check if a report already exists for this property
    existing_report = await db.fetchrow(
        """
        SELECT id, status, created_at
        FROM property_reports
        WHERE property_id = $1
        ORDER BY created_at DESC
        LIMIT 1
        """,
        property_id,
    )
    
    # If report exists and is in a terminal state (READY or failed), allow re-scrape
    # If report is in progress, return current status
    if existing_report:
        status = existing_report["status"]
        if status in ("QUEUING", "PROCESSING"):
            return {
                "status": "processing",
                "report_status": status,
                "report_id": str(existing_report["id"]),
                "message": "Property data is currently being processed.",
            }
        elif status == "READY":
            return {
                "status": "ready",
                "report_status": status,
                "report_id": str(existing_report["id"]),
                "message": "Property data is ready. Refresh to view details.",
            }
    
    # Fetch property details to pass to scraper
    row = await db.fetchrow(
        """
        SELECT
            p.id::text,
            p.gnaf_pid,
            p.address_string,
            p.state,
            p.lga_id,
            ST_Y(p.geom::geometry) AS latitude,
            ST_X(p.geom::geometry) AS longitude
        FROM properties p
        WHERE p.id = $1
        """,
        property_id,
    )
    
    if not row:
        raise HTTPException(status_code=404, detail="Property not found.")

    lga_id = row.get("lga_id")
    # Lazy LGA resolution if lga_id is NULL
    if not lga_id and row.get("longitude") is not None and row.get("latitude") is not None:
        resolved_lga = await db.fetchrow(
            """
            SELECT id FROM spatial_zones
            WHERE zone_type = 'LGA'
              AND ST_Contains(geom, (SELECT geom FROM properties WHERE id = $1))
            LIMIT 1
            """,
            property_id
        )
        if resolved_lga:
            lga_id = resolved_lga["id"]
            await db.execute(
                "UPDATE properties SET lga_id = $1, updated_at = NOW() WHERE id = $2",
                lga_id, property_id
            )

    lga_name = None
    if lga_id:
        lga_row = await db.fetchrow("SELECT name FROM spatial_zones WHERE id = $1", lga_id)
        if lga_row:
            lga_name = lga_row["name"]

    user_id = current_user.id if current_user else None

    # For anonymous users, issue/read anon_requester_id cookie for later claim
    anon_id: str | None = None
    if not current_user:
        anon_id = await get_or_create_anon_id(request, response)

    # Upsert property report to QUEUING
    report_id = await db.fetchval(
        """
        INSERT INTO property_reports (property_id, status, requested_by_user_id, anon_requester_id)
        VALUES ($1, 'QUEUING', $2, $3)
        ON CONFLICT (property_id) DO UPDATE
        SET status = 'QUEUING',
            requested_by_user_id = EXCLUDED.requested_by_user_id,
            anon_requester_id = EXCLUDED.anon_requester_id,
            raw_scraped_data = NULL,
            llm_parsed_insights = NULL,
            confidence_scores = NULL,
            overall_confidence = NULL,
            error_message = NULL,
            updated_at = NOW()
        RETURNING id
        """,
        property_id, user_id, anon_id
    )
    
    # Dispatch Celery task
    task_result = celery_app.send_task(
        "scraper_worker.tasks.scrape_property",
        kwargs={
            "property_id": str(property_id),
            "gnaf_pid": row.get("gnaf_pid"),
            "address_string": row.get("address_string"),
            "latitude": float(row["latitude"]) if row.get("latitude") is not None else None,
            "longitude": float(row["longitude"]) if row.get("longitude") is not None else None,
            "lga_name": lga_name,
            "state": row.get("state"),
            "priority": 5 if current_user else 7,  # Higher priority for authenticated users
        },
        queue="data_acquisition_queue",
    )
    
    return {
        "status": "queued",
        "task_id": task_result.id,
        "report_id": str(report_id),
        "property_id": str(property_id),
        "message": f"Scrape task queued for {row['address_string']}. Check back soon.",
    }


# ── Helpers ───────────────────────────────────────────────────────────────────


def _normalize_insights(insights: object) -> dict | None:
    """Normalize LLM insights to a dictionary regardless of DB representation."""
    if insights is None:
        return None

    if isinstance(insights, dict):
        return insights

    if isinstance(insights, str):
        try:
            parsed = json.loads(insights)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None

    return None


def _transform_raw_data_for_pdf(raw_data: dict, address: str) -> dict:
    """Transform raw scraped data into minimal structure for lite PDF generation.
    
    The full PDF generator expects LLM-structured insights. For lite reports with
    only raw data, we create a minimal structure with the data we have.
    """
    result = {
        "address": address,
        "summary": "This lite preview includes raw data from public sources. Sign in for the full AI-analyzed report.",
    }
    
    # Demographics
    if "demographics" in raw_data and isinstance(raw_data["demographics"], dict):
        demo = raw_data["demographics"]
        latest = demo.get("latest", {})
        if latest:
            result["demographics"] = {
                "population": latest.get("total_population"),
                "median_age": latest.get("median_age_persons_years"),
                "lga_name": latest.get("lga_name"),
            }
        # Include time series for charts
        if "time_series" in demo:
            result["_raw_demographics_time_series"] = demo["time_series"]
    
    # NBN
    if "nbn" in raw_data:
        nbn = raw_data["nbn"]
        result["connectivity"] = {
            "nbn_technology": nbn.get("tech_type"),
            "nbn_status": nbn.get("service_status"),
        }
    
    # Risk factors
    result["risk_factors"] = {}
    if "zoning_code" in raw_data:
        result["risk_factors"]["zoning"] = raw_data["zoning_code"]
    if "flood_risk" in raw_data:
        result["risk_factors"]["flood"] = raw_data["flood_risk"]
    if "bushfire_risk" in raw_data:
        result["risk_factors"]["bushfire"] = raw_data["bushfire_risk"]
    
    return result


def _build_detail_sections(insights: dict, raw_scraped: dict) -> dict[str, dict | None]:
    """Build curated detail sections (LLM-first with raw fallback)."""
    education = _extract_detail_education(insights, raw_scraped)
    connectivity = _extract_detail_connectivity(insights, raw_scraped)
    risk_factors = _extract_detail_risk_factors(insights, raw_scraped)
    zoning_and_planning = _extract_detail_zoning(insights, raw_scraped)
    demographic_snapshot = _extract_detail_demographics(insights, raw_scraped)

    return {
        "education": education,
        "connectivity": connectivity,
        "risk_factors": risk_factors,
        "zoning_and_planning": zoning_and_planning,
        "demographic_snapshot": demographic_snapshot,
    }


def _extract_detail_education(insights: dict, raw_scraped: dict) -> dict | None:
    llm_education = insights.get("education")
    if isinstance(llm_education, dict) and llm_education:
        return {
            "primary_schools": llm_education.get("primary_schools", [])[:5],
            "secondary_schools": llm_education.get("secondary_schools", [])[:5],
            "nearby_schools_summary": llm_education.get("nearby_schools_summary"),
        }

    nearby = raw_scraped.get("nearby_schools")
    if not isinstance(nearby, dict):
        return None

    by_type = nearby.get("schools_by_type")
    if not isinstance(by_type, dict):
        return None

    def _map_school(item: dict) -> dict:
        return {
            "name": item.get("name"),
            "distance_km": item.get("distance_km"),
            "in_catchment": item.get("in_catchment"),
            "sector": item.get("sector"),
            "enrolments": item.get("enrolments"),
        }

    primary = [
        _map_school(s) for s in by_type.get("Primary", []) if isinstance(s, dict)
    ][:5]
    secondary = [
        _map_school(s) for s in by_type.get("Secondary", []) if isinstance(s, dict)
    ][:5]

    if not primary and not secondary:
        return None

    return {
        "primary_schools": primary,
        "secondary_schools": secondary,
        "nearby_schools_summary": None,
    }


def _extract_detail_connectivity(insights: dict, raw_scraped: dict) -> dict | None:
    llm_connectivity = insights.get("connectivity")
    if isinstance(llm_connectivity, dict) and llm_connectivity:
        return {
            "nbn_tech_type": llm_connectivity.get("nbn_tech_type"),
            "nbn_service_status": llm_connectivity.get("nbn_service_status"),
            "nbn_tech_change_status": llm_connectivity.get("nbn_tech_change_status"),
            "nbn_target_eligibility_quarter": llm_connectivity.get("nbn_target_eligibility_quarter"),
        }

    nbn = raw_scraped.get("nbn")
    if not isinstance(nbn, dict):
        return None

    return {
        "nbn_tech_type": nbn.get("tech_type") or raw_scraped.get("nbn_type"),
        "nbn_service_status": nbn.get("service_status"),
        "nbn_tech_change_status": nbn.get("tech_change_status"),
        "nbn_target_eligibility_quarter": nbn.get("target_eligibility_quarter"),
    }


def _extract_detail_risk_factors(insights: dict, raw_scraped: dict) -> dict | None:
    llm_risk = insights.get("risk_factors")
    if isinstance(llm_risk, dict) and llm_risk:
        return llm_risk

    flood = raw_scraped.get("flood_risk")
    bushfire = raw_scraped.get("bushfire_risk")
    if flood is None and bushfire is None:
        return None

    return {
        "flood": {
            "risk": flood,
            "detail": "Derived from raw planning/risk payload",
        },
        "bushfire": {
            "risk": bushfire,
            "detail": "Derived from raw planning/risk payload",
        },
    }


def _extract_detail_zoning(insights: dict, raw_scraped: dict) -> dict | None:
    llm_zoning = insights.get("zoning_and_planning")
    if isinstance(llm_zoning, dict) and llm_zoning:
        return llm_zoning

    overlays = raw_scraped.get("overlays")
    mapped_overlays: list[dict] = []
    if isinstance(overlays, list):
        mapped_overlays = [
            {
                "code": ov.get("code"),
                "family": ov.get("family"),
                "summary": ov.get("summary"),
                "severity": ov.get("severity"),
            }
            for ov in overlays
            if isinstance(ov, dict)
        ]

    if not any([raw_scraped.get("zoning_code"), raw_scraped.get("zoning_label"), mapped_overlays]):
        return None

    return {
        "lga_name": raw_scraped.get("lga_name"),
        "zoning_code": raw_scraped.get("zoning_code"),
        "zoning_label": raw_scraped.get("zoning_label"),
        "heritage_area": raw_scraped.get("heritage_overlay"),
        "overlays": mapped_overlays,
    }


def _extract_detail_demographics(insights: dict, raw_scraped: dict) -> dict | None:
    llm_demo = insights.get("demographic_snapshot")
    if isinstance(llm_demo, dict) and llm_demo:
        return llm_demo

    demographics = raw_scraped.get("demographics")
    if not isinstance(demographics, dict):
        return None

    latest = demographics.get("latest")
    if not isinstance(latest, dict):
        return None

    return {
        "source": demographics.get("source"),
        "lga_name": demographics.get("lga_name"),
        "reference_year": demographics.get("latest_year"),
        "total_population": latest.get("total_population"),
        "median_age": latest.get("median_age_persons_years"),
        "population_growth_pct_yoy": latest.get("population_growth_pct_yoy"),
        "house_price_growth_pct_yoy": latest.get("house_price_growth_pct_yoy"),
        "dwelling_approvals_growth_pct_yoy": latest.get("dwelling_approvals_growth_pct_yoy"),
        "total_dwelling_approvals": latest.get("total_dwelling_approvals"),
    }


def _build_teaser(insights: dict | None) -> str | None:
    """Build a teaser message from insights to entice users to unlock the full report.

    Returns None if there's nothing noteworthy to tease.
    """
    if not insights:
        return None

    teaser_parts: list[str] = []

    # Check for planning overlays
    zoning = insights.get("zoning_and_planning", {})
    overlays = zoning.get("overlays", []) if isinstance(zoning, dict) else []
    if isinstance(overlays, list) and len(overlays) > 0:
        teaser_parts.append(f"{len(overlays)} planning overlay(s) identified — Unlock to view details")

    # Check for flood risk
    risk_factors = insights.get("risk_factors", {})
    if isinstance(risk_factors, dict):
        flood_risk = risk_factors.get("flood_risk")
        if flood_risk and flood_risk != "Low":
            teaser_parts.append("Flood risk identified — Unlock to view assessment")

        bushfire_risk = risk_factors.get("bushfire_risk")
        if bushfire_risk and bushfire_risk not in ("Negligible", "Low"):
            teaser_parts.append("Bushfire risk identified — Unlock to view assessment")

    return "; ".join(teaser_parts) if teaser_parts else None
