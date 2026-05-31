"""Integration tests for property endpoints."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies import get_db
from app.main import app
from tests.conftest import MockConnection

PROP_ID = uuid4()


def _make_property_row(report_status="READY", llm_insights=None, raw_scraped=None):
    """Build a fake property + report joined row."""
    return {
        "id": PROP_ID,
        "address_string": "8 St Lawrence Close, Werribee VIC 3030",
        "state": "VIC",
        "estimated_value": 625000,
        "estimated_rent_weekly": 450,
        "gross_yield_percent": Decimal("3.74"),
        "beds": 3,
        "baths": 2,
        "cars": 2,
        "land_size_sqm": Decimal("527"),
        "report_status": report_status,
        "llm_parsed_insights": llm_insights,
        "raw_scraped_data": raw_scraped,
    }


@pytest.mark.asyncio
async def test_property_detail_llm_first():
    mock_db = MockConnection()
    mock_db.fetchrow.return_value = _make_property_row(
        llm_insights={
            "education": {
                "primary_schools": [{"name": "Werribee Primary", "distance_km": 0.9}],
                "secondary_schools": [{"name": "Werribee Secondary", "distance_km": 1.8}],
                "nearby_schools_summary": "Good nearby school access.",
            },
            "connectivity": {
                "nbn_tech_type": "FTTP",
                "nbn_service_status": "Serviceable",
            },
            "risk_factors": {"flood": {"risk": "LOW"}},
            "zoning_and_planning": {"zoning_code": "GRZ1"},
            "demographic_snapshot": {"total_population": 1000},
        }
    )

    async def _override_db():
        yield mock_db

    app.dependency_overrides[get_db] = _override_db
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/api/properties/{PROP_ID}/detail")

    app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert data["address"] == "8 St Lawrence Close, Werribee VIC 3030"
    assert data["state"] == "VIC"
    assert data["education"]["primary_schools"][0]["name"] == "Werribee Primary"
    assert data["connectivity"]["nbn_tech_type"] == "FTTP"
    assert data["zoning_and_planning"]["zoning_code"] == "GRZ1"


@pytest.mark.asyncio
async def test_property_detail_not_found():
    mock_db = MockConnection()
    mock_db.fetchrow.return_value = None

    async def _override_db():
        yield mock_db

    app.dependency_overrides[get_db] = _override_db
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/api/properties/{uuid4()}/detail")

    app.dependency_overrides.clear()
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_property_detail_raw_fallback():
    mock_db = MockConnection()
    mock_db.fetchrow.return_value = _make_property_row(
        llm_insights=None,
        raw_scraped={
            "nearby_schools": {
                "schools_by_type": {
                    "Primary": [{"name": "Primary A", "distance_km": 0.8, "in_catchment": True}],
                    "Secondary": [{"name": "Secondary A", "distance_km": 1.5, "in_catchment": False}],
                }
            },
            "nbn": {
                "tech_type": "FTTC",
                "service_status": "Connected",
            },
            "zoning_code": "GRZ2",
            "flood_risk": "LOW",
            "demographics": {
                "source": "ABS",
                "latest_year": 2021,
                "latest": {
                    "total_population": 22000,
                    "median_age_persons_years": 36,
                },
            },
        },
    )

    async def _override_db():
        yield mock_db

    app.dependency_overrides[get_db] = _override_db
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/api/properties/{PROP_ID}/detail")

    app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert data["education"]["primary_schools"][0]["name"] == "Primary A"
    assert data["connectivity"]["nbn_service_status"] == "Connected"
    assert data["risk_factors"]["flood"]["risk"] == "LOW"
    assert data["zoning_and_planning"]["zoning_code"] == "GRZ2"
    assert data["demographic_snapshot"]["total_population"] == 22000

@pytest.mark.asyncio
async def test_request_scrape_deduplication():
    """Test that requesting a scrape for an already queuing/processing/ready report returns the correct status."""
    mock_db = MockConnection()
    
    # Simulate an existing processing report
    mock_db.fetchrow.return_value = {
        "id": uuid4(),
        "status": "PROCESSING",
        "created_at": "2024-01-01T00:00:00"
    }

    async def _override_db():
        yield mock_db

    app.dependency_overrides[get_db] = _override_db
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(f"/api/properties/{PROP_ID}/request-scrape")

    app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "processing"
    assert data["report_status"] == "PROCESSING"

@pytest.mark.asyncio
async def test_request_scrape_lazy_lga_id():
    """Test that requesting a scrape for a property without lga_id resolves it."""
    mock_db = MockConnection()
    
    # Simulate no existing report
    mock_db.fetchrow.side_effect = [
        None,  # No existing report
        {
            "id": PROP_ID,
            "gnaf_pid": "GNAF123",
            "address_string": "123 Test St",
            "state": "VIC",
            "lga_id": None,
            "latitude": -37.8,
            "longitude": 144.9
        },
        {"id": "lga_123"}, # resolved lga
        {"name": "Melbourne City"} # lga name
    ]
    mock_db.fetchval.return_value = uuid4() # report id

    async def _override_db():
        yield mock_db

    # we also need to mock current_user to None
    from app.dependencies import get_optional_user
    async def _override_user():
        return None

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_optional_user] = _override_user
    
    transport = ASGITransport(app=app)

    from unittest.mock import patch
    with patch("app.routers.properties.celery_app.send_task") as mock_send_task:
        mock_send_task.return_value.id = "task_123"
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(f"/api/properties/{PROP_ID}/request-scrape")

    app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "queued"
    assert data["task_id"] == "task_123"

    # LGA resolution: no report → property fetch → spatial join → lga name
    assert mock_db.fetchrow.call_count == 4

    # lga_id was written back to the property row
    assert mock_db.execute.call_count == 1
    call_args = mock_db.execute.call_args[0]
    assert "UPDATE properties SET lga_id" in call_args[0]
    assert call_args[1] == "lga_123"

    # Resolved lga_name is forwarded to the scraper task
    sent_kwargs = mock_send_task.call_args[1]["kwargs"]
    assert sent_kwargs["lga_name"] == "Melbourne City"


@pytest.mark.asyncio
async def test_request_scrape_failed_report_requeues():
    """Requesting a scrape for a FAILED report creates a new QUEUING job."""
    mock_db = MockConnection()

    mock_db.fetchrow.side_effect = [
        {"id": uuid4(), "status": "FAILED", "created_at": "2024-01-01T00:00:00"},  # existing FAILED report
        {
            "id": PROP_ID,
            "gnaf_pid": "GNAF999",
            "address_string": "1 Broken St",
            "state": "NSW",
            "lga_id": "lga_abc",
            "latitude": -33.9,
            "longitude": 151.2,
        },
        {"name": "Sydney City"},  # lga name (lga_id already set, no spatial join)
    ]
    mock_db.fetchval.return_value = uuid4()

    from app.dependencies import get_optional_user

    async def _override_db():
        yield mock_db

    async def _override_user():
        return None

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_optional_user] = _override_user
    transport = ASGITransport(app=app)

    from unittest.mock import patch

    with patch("app.routers.properties.celery_app.send_task") as mock_send_task:
        mock_send_task.return_value.id = "task_requeue"
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(f"/api/properties/{PROP_ID}/request-scrape")

    app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "queued"
    assert data["task_id"] == "task_requeue"
    mock_send_task.assert_called_once()


@pytest.mark.asyncio
async def test_request_scrape_null_geom_skips_lga_resolution():
    """When geom is NULL (no lat/lng), LGA resolution is skipped and scrape proceeds."""
    mock_db = MockConnection()

    mock_db.fetchrow.side_effect = [
        None,  # no existing report
        {
            "id": PROP_ID,
            "gnaf_pid": "GNAF_NULL",
            "address_string": "2 Null St",
            "state": "QLD",
            "lga_id": None,
            "latitude": None,
            "longitude": None,
        },
    ]
    mock_db.fetchval.return_value = uuid4()

    from app.dependencies import get_optional_user

    async def _override_db():
        yield mock_db

    async def _override_user():
        return None

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_optional_user] = _override_user
    transport = ASGITransport(app=app)

    from unittest.mock import patch

    with patch("app.routers.properties.celery_app.send_task") as mock_send_task:
        mock_send_task.return_value.id = "task_null_geom"
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(f"/api/properties/{PROP_ID}/request-scrape")

    app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "queued"

    # No spatial join executed and no lga_id update
    assert mock_db.execute.call_count == 0
    sent_kwargs = mock_send_task.call_args[1]["kwargs"]
    assert sent_kwargs["lga_name"] is None
