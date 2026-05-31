"""Synchronous database helpers for the LLM parser worker.

Uses psycopg2 (sync) since Celery workers run synchronously.
Connection string comes from DATABASE_URL environment variable.
"""

from __future__ import annotations

import logging

import psycopg2
import psycopg2.extras

from app.config import settings

logger = logging.getLogger(__name__)


def get_db_connection():
    """Create a new psycopg2 connection.

    The caller is responsible for closing the connection.

    Returns:
        psycopg2 connection with RealDictCursor factory.
    """
    # Strip the +psycopg2 suffix if present (pydantic-settings may include it)
    dsn = settings.DATABASE_URL.replace("postgresql+psycopg2://", "postgresql://")

    return psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)
