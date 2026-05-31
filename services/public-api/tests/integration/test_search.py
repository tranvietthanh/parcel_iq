"""Integration tests for search endpoints."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies import get_db, verify_clerk_token
from app.main import app
from app.middleware.turnstile import verify_turnstile
from tests.conftest import MockConnection


@pytest.fixture
def search_client():
    """Client with Turnstile bypassed (anonymous, no auth)."""
    mock_db = MockConnection()

    async def _override_db():
        yield mock_db

    async def _no_turnstile():
        return None

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[verify_turnstile] = _no_turnstile

    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")

    yield client, mock_db

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_search_requires_q_or_bbox(search_client):
    client, _ = search_client
    resp = await client.get("/api/search", headers={"X-Turnstile-Token": "t"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_search_bbox(search_client):
    client, mock_db = search_client

    prop_id = str(uuid4())
    mock_db.fetch.return_value = [
        {
            "id": prop_id,
            "address_string": "1 Test St, VIC 3000",
            "geometry": {"type": "Point", "coordinates": [144.96, -37.81]},
            "estimated_value": 500000,
            "report_status": "READY",
        }
    ]

    resp = await client.get(
        "/api/search",
        params={"bbox": "144.5,-37.9,145.0,-37.7"},
        headers={"X-Turnstile-Token": "t"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "FeatureCollection"
    assert len(data["features"]) == 1
    assert data["features"][0]["properties"]["id"] == prop_id


@pytest.mark.asyncio
async def test_search_bbox_invalid(search_client):
    client, _ = search_client
    resp = await client.get(
        "/api/search",
        params={"bbox": "invalid"},
        headers={"X-Turnstile-Token": "t"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_search_text(search_client):
    client, mock_db = search_client

    mock_db.fetch.return_value = [
        {
            "type": "ADDRESS",
            "label": "1 Test St, VIC 3000",
            "property_id": str(uuid4()),
            "zone_id": None,
            "lng": 144.96,
            "lat": -37.81,
            "bbox": None,
        },
    ]

    resp = await client.get(
        "/api/search",
        params={"q": "test st"},
        headers={"X-Turnstile-Token": "t"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert "suggestions" in data
    assert len(data["suggestions"]) == 1
    assert data["suggestions"][0]["type"] == "ADDRESS"


@pytest.mark.asyncio
async def test_search_zones():
    mock_db = MockConnection()
    zone_id = uuid4()

    mock_db.fetchrow.return_value = {
        "zone_type": "LGA",
        "name": "Wyndham",
        "state": "VIC",
        "geometry": {"type": "MultiPolygon", "coordinates": [[[[144.5, -37.9]]]]},
        "metadata": {"population": 300000},
    }

    async def _override_db():
        yield mock_db

    app.dependency_overrides[get_db] = _override_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/search/zones", params={"zone_id": str(zone_id)})

    app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "Feature"
    assert data["properties"]["name"] == "Wyndham"


@pytest.mark.asyncio
async def test_search_zones_not_found():
    mock_db = MockConnection()
    mock_db.fetchrow.return_value = None

    async def _override_db():
        yield mock_db

    app.dependency_overrides[get_db] = _override_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/search/zones", params={"zone_id": str(uuid4())})

    app.dependency_overrides.clear()
    assert resp.status_code == 404
