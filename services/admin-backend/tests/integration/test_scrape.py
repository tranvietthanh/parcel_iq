from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.asyncio
@patch("app.routers.properties.celery_app")
async def test_force_scrape_property_queues_task(mock_celery, mock_db):
    """Force scrape should queue one property scrape task."""
    from app.routers.properties import force_scrape_property
    from app.schemas.properties import TriggerScrapeRequest

    task_result = MagicMock()
    task_result.id = "task-123"
    mock_celery.send_task.return_value = task_result

    mock_db.fetchrow.return_value = {
        "id": "property-123",
        "gnaf_pid": "GAVIC411711441",
        "address_string": "1 Test St",
        "latitude": -37.8136,
        "longitude": 144.9631,
        "lga_name": "Melbourne",
        "state": "VIC",
    }

    response = await force_scrape_property(
        property_id="property-123",
        request=TriggerScrapeRequest(priority="HIGH", mode="FORCE_ALL"),
        db=mock_db,
    )

    assert response.property_id == "property-123"
    assert response.task_id == "task-123"
    assert "1 Test St" in response.message

    mock_celery.send_task.assert_called_once_with(
        "scraper_worker.tasks.scrape_property",
        kwargs={
            "property_id": "property-123",
            "gnaf_pid": "GAVIC411711441",
            "address_string": "1 Test St",
            "latitude": -37.8136,
            "longitude": 144.9631,
            "lga_name": "Melbourne",
            "state": "VIC",
            "mode": "FORCE_ALL",
            "priority": "HIGH",
        },
        queue="data_acquisition_queue",
    )


@pytest.mark.asyncio
async def test_force_scrape_property_not_found(mock_db):
    """Force scrape should 404 when the property does not exist."""
    from fastapi import HTTPException

    from app.routers.properties import force_scrape_property
    from app.schemas.properties import TriggerScrapeRequest

    mock_db.fetchrow.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        await force_scrape_property(
            property_id="missing-property",
            request=TriggerScrapeRequest(priority="NORMAL", mode="FORCE_ALL"),
            db=mock_db,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Property not found"


@pytest.mark.asyncio
@patch("app.routers.properties.celery_app")
async def test_re_ai_validate_queues_latest_report(mock_celery, mock_db):
    """Re-AI validate should queue the latest report for LLM parsing."""
    from app.routers.properties import re_ai_validate_property

    task_result = MagicMock()
    task_result.id = "llm-task-123"
    mock_celery.send_task.return_value = task_result

    mock_db.fetchrow.return_value = {
        "property_id": "property-123",
        "address_string": "1 Test St",
        "report_id": "report-123",
    }

    response = await re_ai_validate_property(property_id="property-123", db=mock_db)
    assert response.property_id == "property-123"
    assert response.task_id == "llm-task-123"

    mock_celery.send_task.assert_called_once_with(
        "app.tasks.parse_with_llm",
        kwargs={
            "property_id": "property-123",
            "property_report_id": "report-123",
            "address_string": "1 Test St",
        },
        queue="llm_processing_queue",
    )


@pytest.mark.asyncio
async def test_get_property_detail_does_not_reset_report_data(mock_db):
    """Property detail read should not null report payloads or set status to QUEUING."""
    from app.routers.properties import get_property_detail

    mock_db.fetchrow.return_value = {
        "id": "property-123",
        "gnaf_pid": "GAVIC411711441",
        "address_string": "1 Test St",
        "state": "VIC",
        "lga_name": "Melbourne",
        "suburb_name": "Melbourne",
        "latitude": -37.8136,
        "longitude": 144.9631,
        "beds": 3,
        "baths": 2,
        "cars": 1,
        "land_size_sqm": 300,
        "estimated_value": 900000,
        "estimated_rent": 750,
        "last_scraped_at": None,
        "created_at": "2026-05-26T10:00:00Z",
        "updated_at": "2026-05-26T10:00:00Z",
    }

    response = await get_property_detail(property_id="property-123", db=mock_db)

    assert response.id == "property-123"
    assert response.address_string == "1 Test St"
    # Read path should not call fetchval upsert that clears report payload columns.
    mock_db.fetchval.assert_not_called()
    # Lazy LGA backfill check runs on reads for thin-imported properties.
    mock_db.execute.assert_called_once()
