"""Integration tests for saved properties endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies import get_current_user, get_db
from app.main import app
from app.schemas.user import UserRow
from tests.conftest import FAKE_USER_ROW, MockConnection


PROP_ID = uuid4()


@pytest.mark.asyncio
async def test_save_property():
    mock_db = MockConnection()
    # Property exists check
    mock_db.fetchrow.return_value = {"id": PROP_ID}
    fake_user = UserRow(**FAKE_USER_ROW)

    async def _override_db():
        yield mock_db

    async def _override_user():
        return fake_user

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(f"/api/saved/{PROP_ID}")

    app.dependency_overrides.clear()
    assert resp.status_code == 201
    assert resp.json() == {"saved": True}


@pytest.mark.asyncio
async def test_save_property_not_found():
    mock_db = MockConnection()
    mock_db.fetchrow.return_value = None  # property doesn't exist
    fake_user = UserRow(**FAKE_USER_ROW)

    async def _override_db():
        yield mock_db

    async def _override_user():
        return fake_user

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(f"/api/saved/{PROP_ID}")

    app.dependency_overrides.clear()
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_unsave_property():
    mock_db = MockConnection()
    mock_db.execute.return_value = "DELETE 1"
    fake_user = UserRow(**FAKE_USER_ROW)

    async def _override_db():
        yield mock_db

    async def _override_user():
        return fake_user

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.delete(f"/api/saved/{PROP_ID}")

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert resp.json() == {"unsaved": True}


@pytest.mark.asyncio
async def test_unsave_not_found():
    mock_db = MockConnection()
    mock_db.execute.return_value = "DELETE 0"
    fake_user = UserRow(**FAKE_USER_ROW)

    async def _override_db():
        yield mock_db

    async def _override_user():
        return fake_user

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.delete(f"/api/saved/{PROP_ID}")

    app.dependency_overrides.clear()
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_saved_empty():
    mock_db = MockConnection()
    mock_db.fetch.return_value = []
    fake_user = UserRow(**FAKE_USER_ROW)

    async def _override_db():
        yield mock_db

    async def _override_user():
        return fake_user

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/saved")

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_saved_returns_property_detail_shape():
    mock_db = MockConnection()
    mock_db.fetch.return_value = [
        {
            "id": PROP_ID,
            "address_string": "8 St Lawrence Close, Werribee VIC 3030",
            "state": "VIC",
            "report_status": "READY",
            "llm_parsed_insights": {
                "education": {
                    "primary_schools": [{"name": "Werribee Primary", "distance_km": 0.9}],
                    "secondary_schools": [],
                },
                "connectivity": {
                    "nbn_tech_type": "FTTP",
                    "nbn_service_status": "Serviceable",
                },
            },
            "raw_scraped_data": {
                "flood_risk": "LOW",
                "zoning_code": "GRZ1",
            },
        }
    ]
    fake_user = UserRow(**FAKE_USER_ROW)

    async def _override_db():
        yield mock_db

    async def _override_user():
        return fake_user

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/saved")

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["id"] == str(PROP_ID)
    assert body[0]["address"] == "8 St Lawrence Close, Werribee VIC 3030"
    assert body[0]["report_status"] == "READY"
    assert body[0]["education"]["primary_schools"][0]["name"] == "Werribee Primary"
    assert body[0]["connectivity"]["nbn_tech_type"] == "FTTP"
