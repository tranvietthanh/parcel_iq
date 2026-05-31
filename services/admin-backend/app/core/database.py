"""asyncpg connection pool lifecycle — attached to FastAPI app.state."""

from __future__ import annotations

import json

import asyncpg
from fastapi import FastAPI

from app.config import settings


async def _init_connection(conn: asyncpg.Connection) -> None:
    """Register JSON/JSONB codecs so asyncpg decodes JSONB columns to dicts."""
    await conn.set_type_codec(
        "jsonb",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
    )
    await conn.set_type_codec(
        "json",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
    )


async def create_db_pool(app: FastAPI) -> None:
    """Create the asyncpg connection pool during startup."""
    app.state.db_pool = await asyncpg.create_pool(
        dsn=settings.asyncpg_dsn,
        min_size=2,
        max_size=10,
        command_timeout=30,
        init=_init_connection,
    )


async def close_db_pool(app: FastAPI) -> None:
    """Gracefully close the pool during shutdown."""
    pool: asyncpg.Pool | None = getattr(app.state, "db_pool", None)
    if pool:
        await pool.close()
