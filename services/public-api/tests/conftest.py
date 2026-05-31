"""Shared test fixtures and helpers."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.dependencies import get_db, require_auth, verify_clerk_token
from app.main import app

# ── Fake user data ────────────────────────────────────────────────────────────

FAKE_USER_ID = uuid4()
FAKE_CLERK_USER_ID = "user_test_123456"
FAKE_EMAIL = "test@example.com"

FAKE_JWT_PAYLOAD = {
    "sub": FAKE_CLERK_USER_ID,
    "iss": "https://clerk.test.dev",
    "exp": 9999999999,
}

FAKE_USER_ROW = {
    "id": FAKE_USER_ID,
    "clerk_user_id": FAKE_CLERK_USER_ID,
    "email": FAKE_EMAIL,
    "created_at": "2025-01-01T00:00:00",
}


# ── Mock DB connection ────────────────────────────────────────────────────────


class MockConnection:
    """Minimal mock of asyncpg.Connection for unit tests."""

    def __init__(self):
        self.fetchrow = AsyncMock(return_value=None)
        self.fetchval = AsyncMock(return_value=1)
        self.fetch = AsyncMock(return_value=[])
        self.execute = AsyncMock(return_value="INSERT 0 1")


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_db():
    """Return a MockConnection that can be pre-loaded with results."""
    return MockConnection()


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def authed_client(mock_db):
    """AsyncClient where auth is bypassed and DB is mocked."""
    from app.schemas.user import UserRow

    fake_user = UserRow(**FAKE_USER_ROW)

    async def _override_db():
        yield mock_db

    async def _override_auth():
        return FAKE_JWT_PAYLOAD

    async def _override_verify():
        return FAKE_JWT_PAYLOAD

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_auth] = _override_auth
    app.dependency_overrides[verify_clerk_token] = _override_verify

    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")

    yield client, mock_db, fake_user

    app.dependency_overrides.clear()


@pytest.fixture
def anon_client(mock_db):
    """AsyncClient with no auth — for anonymous endpoints."""

    async def _override_db():
        yield mock_db

    async def _override_verify():
        return None  # anonymous

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[verify_clerk_token] = _override_verify

    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")

    yield client, mock_db

    app.dependency_overrides.clear()
