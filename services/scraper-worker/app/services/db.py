"""Synchronous database helpers for Celery tasks.

Uses psycopg2 (sync) since Celery tasks are synchronous.
Each task gets its own connection — no shared pool.
"""

from __future__ import annotations

import logging

import psycopg2
import psycopg2.extras

from app.config import settings

logger = logging.getLogger(__name__)


def get_db_connection():
    """Create a new psycopg2 connection.

    Caller is responsible for closing the connection.
    """
    return psycopg2.connect(
        settings.psycopg2_dsn,
        cursor_factory=psycopg2.extras.RealDictCursor,
    )


def get_council_config(db, lga_name: str, state: str) -> dict | None:
    """Look up the council adapter config from ``data_source_configs``.

    Returns
    -------
    Dict with ``adapter_name``, ``base_url``, ``config`` keys — or ``None``
    if no enabled config exists for this LGA.
    """
    with db.cursor() as cur:
        cur.execute(
            """SELECT adapter_name, base_url, config
               FROM data_source_configs
               WHERE lga_name = %s
                 AND state = %s
                 AND enabled = TRUE
               LIMIT 1""",
            (lga_name, state),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def mark_report_processing(db, property_id: str) -> str:
    """Update the report status to PROCESSING.

    Returns the report ID (UUID as string).
    """
    with db.cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (property_id,))

        cur.execute(
            """
            INSERT INTO property_reports (property_id, status, updated_at)
            VALUES (%s, 'PROCESSING', NOW())
            ON CONFLICT (property_id) DO UPDATE
            SET status = 'PROCESSING',
                error_message = NULL,
                updated_at = NOW()
            RETURNING id
            """,
            (property_id,),
        )
        row = cur.fetchone()
        if not row:
            raise RuntimeError(
                f"Failed to create/update property_reports row for property_id={property_id}"
            )
        report_id = row["id"]
        db.commit()
        return str(report_id)


def save_scrape_results(
    db,
    property_id: str,
    report_id: str,
    merged_data: dict,
    scraper_version: str,
) -> None:
    """Update the property_reports row with scraped data.
    
    Status stays PROCESSING.
    """
    import json

    with db.cursor() as cur:
        cur.execute(
            """UPDATE property_reports
               SET raw_scraped_data = %s,
                   scraper_version = %s,
                   updated_at = NOW()
               WHERE id = %s""",
            (json.dumps(merged_data), scraper_version, report_id),
        )
        cur.execute(
            "UPDATE properties SET last_scraped_at = NOW() WHERE id = %s",
            (property_id,),
        )
        db.commit()


def mark_report_failed(db, property_id: str, error_message: str) -> None:
    """Mark the latest report for a property as FAILED."""
    with db.cursor() as cur:
        cur.execute(
            """UPDATE property_reports
               SET status = 'FAILED',
                   error_message = %s,
                   updated_at = NOW()
               WHERE property_id = %s
                 AND status IN ('QUEUING', 'PROCESSING')
               """,
            (error_message, property_id),
        )
        db.commit()


def update_property_nbn_loc_id(db, property_id: str, nbn_loc_id: str) -> None:
    """Persist the resolved NBN Location ID on the properties row.

    This is intentionally simple: overwrite `nbn_loc_id` and touch
    `updated_at` so other workers can re-use the locId without re-resolving.
    """
    with db.cursor() as cur:
        cur.execute(
            "UPDATE properties SET nbn_loc_id = %s, updated_at = NOW() WHERE id = %s",
            (nbn_loc_id, property_id),
        )
        db.commit()

