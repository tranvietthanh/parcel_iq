"""Integration tests for user endpoints."""

from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.dependencies import get_current_user, get_db
from app.main import app
from app.schemas.user import UserRow
from tests.conftest import FAKE_CLERK_USER_ID, FAKE_EMAIL, FAKE_USER_ID, FAKE_USER_ROW, MockConnection


@pytest.mark.asyncio
async def test_sync_user_success():
    mock_db = MockConnection()

    async def _override_db():
        yield mock_db

    app.dependency_overrides[get_db] = _override_db
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/users/sync",
            json={"clerk_user_id": "user_new", "email": "new@test.com"},
            headers={"X-Webhook-Secret": settings.INTERNAL_WEBHOOK_SECRET},
        )

    app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json() == {"synced": True}
    mock_db.execute.assert_called_once()


@pytest.mark.asyncio
async def test_sync_user_bad_secret():
    mock_db = MockConnection()

    async def _override_db():
        yield mock_db

    app.dependency_overrides[get_db] = _override_db
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/users/sync",
            json={"clerk_user_id": "user_new", "email": "new@test.com"},
            headers={"X-Webhook-Secret": "wrong-secret"},
        )

    app.dependency_overrides.clear()

    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_delete_account():
    mock_db = MockConnection()
    fake_user = UserRow(**FAKE_USER_ROW)

    async def _override_db():
        yield mock_db

    async def _override_user():
        return fake_user

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.delete("/api/users/me")

    app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json() == {"deleted": True}
    # Should have 2 DB calls: delete saved_properties, delete users (cascades to daily_downloads)
    assert mock_db.execute.call_count == 2


@pytest.mark.asyncio
async def test_delete_user_by_webhook_success():
    mock_db = MockConnection()

    async def _override_db():
        yield mock_db

    app.dependency_overrides[get_db] = _override_db
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.delete(
            f"/api/users/sync/{FAKE_CLERK_USER_ID}",
            headers={"X-Webhook-Secret": settings.INTERNAL_WEBHOOK_SECRET},
        )

    app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json() == {"deleted": True}
    assert mock_db.execute.call_count == 2


@pytest.mark.asyncio
async def test_delete_user_by_webhook_bad_secret():
    mock_db = MockConnection()

    async def _override_db():
        yield mock_db

    app.dependency_overrides[get_db] = _override_db
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.delete(
            f"/api/users/sync/{FAKE_CLERK_USER_ID}",
            headers={"X-Webhook-Secret": "wrong-secret"},
        )

    app.dependency_overrides.clear()

    assert resp.status_code == 401
