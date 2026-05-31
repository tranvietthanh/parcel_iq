"""VicPlan cache persistence service.

Stores and retrieves VicPlan adapter payloads by a snapped coordinate key.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta

logger = logging.getLogger(__name__)


def _build_cache_key(lat: float, lng: float, precision: int = 5) -> str:
    """Build a deterministic cache key by snapping coordinates."""
    return f"{lat:.{precision}f},{lng:.{precision}f}"


def get_cached_vic_plan_data(db_connection, lat: float, lng: float) -> dict | None:
    """Return cached VicPlan payload if cache entry exists and is not expired."""
    cache_key = _build_cache_key(lat, lng)

    try:
        cursor = db_connection.cursor()
        cursor.execute(
            """
            SELECT raw_data
            FROM vic_plan_cache
            WHERE cache_key = %s
              AND expires_at > NOW()
            LIMIT 1
            """,
            (cache_key,),
        )
        row = cursor.fetchone()
        cursor.close()

        if not row:
            return None

        raw_data = row[0] if not isinstance(row, dict) else row.get("raw_data")
        if isinstance(raw_data, dict):
            return raw_data
        if isinstance(raw_data, str):
            try:
                parsed = json.loads(raw_data)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                return None

        return None
    except Exception as exc:
        logger.exception("Failed reading VicPlan cache for key %s: %s", cache_key, exc)
        return None


def store_vic_plan_data(
    db_connection,
    lat: float,
    lng: float,
    raw_data: dict,
    ttl_hours: int,
) -> bool:
    """Upsert VicPlan payload into cache."""
    cache_key = _build_cache_key(lat, lng)
    fetched_at = datetime.now(UTC)
    expires_at = fetched_at + timedelta(hours=ttl_hours)

    try:
        cursor = db_connection.cursor()
        cursor.execute(
            """
            INSERT INTO vic_plan_cache (
                cache_key,
                latitude,
                longitude,
                raw_data,
                fetched_at,
                expires_at
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (cache_key)
            DO UPDATE SET
                latitude = EXCLUDED.latitude,
                longitude = EXCLUDED.longitude,
                raw_data = EXCLUDED.raw_data,
                fetched_at = EXCLUDED.fetched_at,
                expires_at = EXCLUDED.expires_at,
                updated_at = NOW()
            """,
            (
                cache_key,
                lat,
                lng,
                json.dumps(raw_data),
                fetched_at,
                expires_at,
            ),
        )
        db_connection.commit()
        cursor.close()
        return True
    except Exception as exc:
        logger.exception("Failed storing VicPlan cache for key %s: %s", cache_key, exc)
        db_connection.rollback()
        return False
