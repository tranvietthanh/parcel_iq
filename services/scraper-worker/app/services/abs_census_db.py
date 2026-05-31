"""ABS regional demographics persistence service.

Handles storing and retrieving ABS Data-by-Region payloads from the database.
Downloaded once via ABS API, persisted in DB, reused for all lookups.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

import psycopg2

logger = logging.getLogger(__name__)


def get_regional_data_from_db(db_connection, region_code: str) -> dict | None:
    """Retrieve cached regional demographics for a region code.

    Args:
        db_connection: psycopg2 database connection
        region_code: ABS region code (LGA2021 code)

    Returns:
        Dict with enriched demographics if found, None if not cached
    """
    try:
        cursor = db_connection.cursor()
        cursor.execute(
            """
            SELECT
                region_code,
                region_name,
                region_type,
                raw_data,
                fetched_at
            FROM abs_census_data
            WHERE region_code = %s
            """,
            (region_code,),
        )
        row = cursor.fetchone()
        cursor.close()

        if not row:
            logger.debug("Region %s not in ABS cache", region_code)
            return None

        code, name, region_type, raw_data, fetched = row
        logger.debug("Found region %s in cache (fetched %s)", code, fetched)

        # raw_data may be JSON/JSONB already or a string depending on driver
        raw_data_obj: dict | None = None
        if raw_data is not None:
            if isinstance(raw_data, dict):
                raw_data_obj = raw_data
            elif isinstance(raw_data, str):
                try:
                    parsed = json.loads(raw_data)
                    if isinstance(parsed, dict):
                        raw_data_obj = parsed
                except Exception:
                    raw_data_obj = None

        # fetched may be a datetime or a string depending on cursor/driver
        if fetched:
            try:
                if isinstance(fetched, datetime):
                    cached_at = fetched.isoformat()
                else:
                    # Try parsing ISO string, fallback to string
                    try:
                        cached_at = datetime.fromisoformat(fetched).isoformat()
                    except Exception:
                        cached_at = str(fetched)
            except Exception:
                cached_at = str(fetched)
        else:
            cached_at = None

        return {
            "region_code": code,
            "region_name": name,
            "region_type": region_type,
            "enriched_demographics": (
                raw_data_obj.get("enriched_demographics") if raw_data_obj else None
            ),
            "cached_at": cached_at,
        }

    except Exception as exc:
        logger.exception("Error querying ABS cache for region %s: %s", region_code, exc)
        return None


def store_regional_data_to_db(
    db_connection,
    region_code: str,
    region_name: str | None,
    region_type: str,
    raw_data: dict | None = None,
) -> bool:
    """Store ABS regional data for a region code in the database.

    Args:
        db_connection: psycopg2 database connection
        region_code: ABS region code
        region_name: Optional region name
        region_type: ABS region type (e.g., LGA2021)
        raw_data: Optional raw SDMX-JSON data for audit trail

    Returns:
        True if stored successfully, False on error
    """
    try:
        cursor = db_connection.cursor()
        
        # Convert raw_data to JSON string if provided
        raw_data_json = json.dumps(raw_data) if raw_data else None
        
        cursor.execute(
            """
            INSERT INTO abs_census_data (
                region_code,
                region_name,
                region_type,
                raw_data,
                fetched_at
            )
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (region_code)
            DO UPDATE SET
                region_name = EXCLUDED.region_name,
                region_type = EXCLUDED.region_type,
                raw_data = EXCLUDED.raw_data,
                fetched_at = EXCLUDED.fetched_at,
                updated_at = NOW()
            """,
            (
                region_code,
                region_name,
                region_type,
                raw_data_json,
                datetime.now(UTC),
            ),
        )
        db_connection.commit()
        cursor.close()
        logger.debug("Stored ABS regional data for region %s", region_code)
        return True

    except Exception as exc:
        logger.exception("Error storing ABS regional data for region %s: %s", region_code, exc)
        db_connection.rollback()
        return False


def count_cached_regional_data(db_connection) -> int:
    """Count how many regional ABS rows are cached in the database."""
    try:
        cursor = db_connection.cursor()
        cursor.execute("SELECT COUNT(*) FROM abs_census_data;")
        count = cursor.fetchone()[0]
        cursor.close()
        return count
    except Exception as exc:
        logger.exception("Error counting regional ABS cache: %s", exc)
        return 0


def clear_regional_data(db_connection) -> bool:
    """Clear all cached regional ABS data (called before refresh)."""
    try:
        cursor = db_connection.cursor()
        cursor.execute("DELETE FROM abs_census_data;")
        db_connection.commit()
        cursor.close()
        logger.info("Cleared all regional ABS data from cache")
        return True
    except Exception as exc:
        logger.exception("Error clearing regional ABS cache: %s", exc)
        db_connection.rollback()
        return False
