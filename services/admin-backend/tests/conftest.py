from unittest.mock import AsyncMock, MagicMock
import pytest
from fastapi.testclient import TestClient


class MockConnection:
    """Mock asyncpg Connection for testing."""

    def __init__(self):
        self.fetchrow = AsyncMock()
        self.fetch = AsyncMock()
        self.fetchval = AsyncMock()
        self.execute = AsyncMock()
        self.transaction = MagicMock()
        self.transaction.return_value.__aenter__ = AsyncMock()
        self.transaction.return_value.__aexit__ = AsyncMock()



@pytest.fixture
def mock_db():
    """Provide a mock database connection."""
    return MockConnection()


@pytest.fixture
def mock_db_pool():
    """Provide a mock database pool."""
    pool = AsyncMock()
    pool.acquire = AsyncMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=MockConnection())
    pool.acquire.return_value.__aexit__ = AsyncMock()
    return pool


@pytest.fixture
def client(mock_db):
    """Provide a FastAPI test client with mocked dependencies."""
    from app.main import create_app
    from app.dependencies import get_db

    app = create_app()

    # Override get_db dependency to return mock connection
    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db

    return TestClient(app)


@pytest.fixture
def auth_headers():
    """Provide valid service token headers."""
    from app.config import settings

    return {
        "X-Service-Token": settings.ADMIN_SERVICE_TOKEN,
        "X-Admin-User-Id": "test-admin-123",
    }
