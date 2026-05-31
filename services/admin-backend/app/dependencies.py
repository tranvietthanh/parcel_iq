"""FastAPI dependency injection functions."""

from __future__ import annotations

import asyncpg
from fastapi import Depends, Request

from app.core.service_auth import verify_service_token  # noqa: F401 (re-export)


async def get_db(request: Request) -> asyncpg.Connection:
    """Yield a connection from the asyncpg pool for the request lifetime."""
    async with request.app.state.db_pool.acquire() as conn:
        yield conn

