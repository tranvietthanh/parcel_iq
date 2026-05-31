"""Health-check endpoint — used by K8s liveness/readiness probes and Traefik.

GET /api/health
"""

from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(db: asyncpg.Connection = Depends(get_db)) -> dict:
    """Return OK if the database is reachable."""
    try:
        await db.fetchval("SELECT 1")
        return {"status": "ok", "db": "connected"}
    except Exception:
        raise HTTPException(
            status_code=503,
            detail={"status": "unhealthy", "db": "unreachable"},
        )
