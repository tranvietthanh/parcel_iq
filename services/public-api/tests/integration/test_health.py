"""Integration tests for health endpoint."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies import get_db
from app.main import app
from tests.conftest import MockConnection


@pytest.mark.asyncio
async def test_health_ok():
    mock_db = MockConnection()
    mock_db.fetchval.return_value = 1

    async def _override_db():
        yield mock_db

    app.dependency_overrides[get_db] = _override_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/health")
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "db": "connected"}


@pytest.mark.asyncio
async def test_health_db_down():
    mock_db = MockConnection()
    mock_db.fetchval.side_effect = Exception("Connection refused")

    async def _override_db():
        yield mock_db

    app.dependency_overrides[get_db] = _override_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/health")
    app.dependency_overrides.clear()

    assert resp.status_code == 503
