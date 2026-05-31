"""Celery tasks for the scraper worker.

The main entry point is :func:`scrape_property`, dispatched by the
Admin Backend API via ``celery_app.send_task()``.
"""

from __future__ import annotations

import json
import logging

from app.celery_app import celery_app
from app.services.schools_enrichment import enrich_property_with_schools

logger = logging.getLogger(__name__)

SCRAPER_VERSION = "1.0.0"


@celery_app.task(
    bind=True,
    name="scraper_worker.tasks.scrape_property",
    max_retries=3,
    acks_late=True,
    reject_on_worker_lost=True,
)
def scrape_property(
    self,
    *,
    property_id: str,
    gnaf_pid: str | None = None,
    address_string: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    lga_name: str | None = None,
    state: str | None = None,
    **kwargs,
) -> dict:
    """Scrape all available data for a single property.

    Steps:
    1. Mark report as PROCESSING
    2. Load council adapter config from ``data_source_configs``
    3. Run national + state + council adapters in parallel
    4. Merge results, strip PII
    5. Store raw data in MinIO
    6. Save raw data to ``property_reports`` (status stays PROCESSING)
    7. Dispatch LLM parsing task
    """
    from app.adapters.runner import merge_adapter_results, run_adapters_parallel
    from app.services.db import (
        get_council_config,
        get_db_connection,
        mark_report_failed,
        mark_report_processing,
        save_scrape_results,
    )
    from app.services.minio_client import store_raw_scrape
    from app.utils.pii import strip_pii_from_scraped_data

    db = None
    try:
        db = get_db_connection()

        # If callers didn't provide location / address fields, load them
        # from the properties table so adapters (e.g. NBN, planning) can run.
        if any(x is None for x in (gnaf_pid, address_string, latitude, longitude, lga_name, state)):
            with db.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        p.gnaf_pid,
                        p.address_string,
                        p.state,
                        ST_Y(p.geom::geometry) AS latitude,
                        ST_X(p.geom::geometry) AS longitude,
                        lga.name AS lga_name
                    FROM properties p
                    LEFT JOIN spatial_zones lga ON lga.id = p.lga_id
                    WHERE p.id = %s
                    """,
                    (property_id,),
                )
                row = cur.fetchone()
            if row:
                # only fill values that were missing from the task args
                gnaf_pid = gnaf_pid or row.get("gnaf_pid")
                address_string = address_string or row.get("address_string")
                state = state or row.get("state")
                lga_name = lga_name or row.get("lga_name")
                # latitude/longitude may be Decimal from PG; cast to float if present
                lat_val = row.get("latitude")
                lng_val = row.get("longitude")
                latitude = latitude if latitude is not None else (float(lat_val) if lat_val is not None else None)
                longitude = longitude if longitude is not None else (float(lng_val) if lng_val is not None else None)

        # 1. Update report status to PROCESSING
        report_id = mark_report_processing(db, property_id)
        logger.info(
            "Scraping property %s (report %s): %s",
            property_id,
            report_id,
            address_string,
        )

        # 2. Load council adapter config
        council_config = get_council_config(db, lga_name, state)

        # 3. Build job dict for adapters
        job = {
            "property_id": property_id,
            "gnaf_pid": gnaf_pid,
            "address_string": address_string,
            "latitude": latitude,
            "longitude": longitude,
            "lga_name": lga_name,
            "state": state,
        }
        # Propagate admin mode (e.g. FORCE_ALL) so adapters can bypass caches
        # when requested.
        job["mode"] = kwargs.get("mode")

        # 4. Run adapters in parallel
        partials = run_adapters_parallel(job, council_config, state)

        # 5. Merge results
        merged_data = merge_adapter_results(partials)

        # 5b. Enrich with nearby schools
        schools_data = enrich_property_with_schools(db, property_id, radius_km=3.0)
        if schools_data:
            merged_data["nearby_schools"] = schools_data
            logger.info(
                "Enriched property %s with %d nearby schools",
                property_id,
                schools_data["total_count"],
            )

        # 6. Strip PII from text fields
        merged_data = strip_pii_from_scraped_data(merged_data)

        # 7. Store raw data in MinIO (audit trail)
        store_raw_scrape(property_id, merged_data)

        # 8. Save to property_reports
        save_scrape_results(db, property_id, report_id, merged_data, SCRAPER_VERSION)

        logger.info(
            "Scrape complete for property %s (report %s).  "
            "Dispatching LLM parsing.",
            property_id,
            report_id,
        )

        # 9. Dispatch LLM parsing task
        celery_app.send_task(
            "app.tasks.parse_with_llm",
            kwargs={
                "property_id": property_id,
                "property_report_id": report_id,
                "address_string": address_string,
            },
            queue="llm_processing_queue",
        )

        return {
            "property_id": property_id,
            "report_id": report_id,
            "status": "PROCESSING",
        }

    except Exception as exc:
        logger.exception(
            "Scrape failed for property %s: %s", property_id, exc
        )
        if db:
            try:
                db.rollback()
                if self.request.retries >= self.max_retries:
                    mark_report_failed(db, property_id, str(exc))
            except Exception:
                logger.exception("Failed to mark report as FAILED")

        raise self.retry(
            exc=exc,
            countdown=30 * (2**self.request.retries),
        )
    finally:
        if db:
            try:
                db.close()
            except Exception:
                pass
