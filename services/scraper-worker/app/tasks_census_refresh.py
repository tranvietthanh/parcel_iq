"""Celery task to refresh ABS Census data.

Background job that downloads Census statistics from the ABS API
and updates the database cache.

Run by: Admin refresh action or scheduled job
"""

import logging

from app.adapters.national.abs_census import AbsCensusAdapter
from app.celery_app import celery_app as app
from app.services.abs_census_db import (
    clear_regional_data,
    count_cached_regional_data,
    store_regional_data_to_db,
)
from app.services.db import get_db_connection

logger = logging.getLogger(__name__)


@app.task(
    bind=True,
    name="app.tasks.refresh_abs_census_complete",
    max_retries=1,
    time_limit=600,  # 10 minutes max
)
def refresh_abs_census_complete(self, delete_existing: bool = True, force: bool = False):
    """Refresh ABS regional demographics cache.

    This task:
    1. Resolves representative points for each known LGA
    2. Fetches ABS Data by Region payloads for each resolved LGA
    3. Stores enriched demographics in abs_census_data.raw_data

    Args:
        delete_existing: If True, delete all old cached data before downloading
        force: If True, ignore recency and refresh anyway

    Returns:
        Dict with refresh statistics
    """
    try:
        db = get_db_connection()
        adapter = AbsCensusAdapter()

        count_before = count_cached_regional_data(db)
        logger.info(
            "Starting regional demographics refresh. Current cache: %d rows",
            count_before,
        )

        # Clear existing data if requested
        if delete_existing:
            logger.info("Clearing existing regional demographics cache...")
            clear_regional_data(db)
            count_before = 0

        # Build representative points for known LGAs from spatial zones.
        with db.cursor() as cur:
            cur.execute(
                """
                SELECT
                    ST_Y(ST_PointOnSurface(geom)::geometry) AS latitude,
                    ST_X(ST_PointOnSurface(geom)::geometry) AS longitude,
                    name
                FROM spatial_zones
                WHERE zone_type = 'LGA'
                """
            )
            lga_rows = cur.fetchall()

        # Resolve ABS LGA codes from representative points.
        lga_codes: set[str] = set()
        for row in lga_rows:
            try:
                lat = float(row["latitude"])
                lng = float(row["longitude"])
            except Exception:
                continue
            code = adapter._resolve_lga(lat, lng)
            if code:
                lga_codes.add(code)

        logger.info("Found %d unique LGA codes to refresh", len(lga_codes))

        # Fetch and store each LGA's regional demographics.
        stored_count = 0
        for i, lga_code in enumerate(sorted(lga_codes)):
            if i % 100 == 0:
                logger.debug("Progress: %d/%d LGAs", i, len(lga_codes))

            try:
                raw = adapter._fetch_lga_data(lga_code)
                demographics = adapter._parse_demographics(raw, lga_code)

                # Store in database
                success = store_regional_data_to_db(
                    db,
                    region_code=lga_code,
                    region_name=demographics.get("lga_name"),
                    region_type="LGA2021",
                    raw_data={"regional": raw, "enriched_demographics": demographics},
                )

                if success:
                    stored_count += 1

            except Exception as exc:
                logger.warning("Failed to cache LGA %s: %s", lga_code, exc)
                continue

        count_after = count_cached_regional_data(db)
        db.close()

        logger.info(
            "Regional refresh complete. Cached: %d LGAs (before: %d, after: %d)",
            stored_count,
            count_before,
            count_after,
        )

        return {
            "status": "success",
            "lga_codes_found": len(lga_codes),
            "lga_codes_stored": stored_count,
            "cache_count_before": count_before,
            "cache_count_after": count_after,
            "message": f"Successfully cached {stored_count} ABS regional LGA records",
        }

    except Exception as exc:
        logger.exception("Census refresh task failed: %s", exc)

        # Retry once on failure
        if self.request.retries < self.max_retries:
            logger.info("Retrying Census refresh...")
            raise self.retry(exc=exc, countdown=60)

        return {
            "status": "failed",
            "error": str(exc),
            "message": f"Census refresh failed after {self.max_retries} retries",
        }
