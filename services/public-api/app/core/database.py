"""asyncpg connection pool lifecycle — attached to FastAPI app.state."""

from __future__ import annotations

import asyncpg
from fastapi import FastAPI

from app.config import settings


async def create_db_pool(app: FastAPI) -> None:
    """Create the asyncpg connection pool during startup."""
    app.state.db_pool = await asyncpg.create_pool(
        dsn=settings.asyncpg_dsn,
        min_size=2,
        max_size=10,
        command_timeout=30,
    )


async def close_db_pool(app: FastAPI) -> None:
    """Gracefully close the pool during shutdown."""
    pool: asyncpg.Pool | None = getattr(app.state, "db_pool", None)
    if pool:
        await pool.close()
