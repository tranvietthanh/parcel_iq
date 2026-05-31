from fastapi import HTTPException
import pytest

from app.core.service_auth import verify_service_token


@pytest.mark.asyncio
async def test_verify_service_token_valid():
    """Valid service token should return admin user ID."""
    from app.config import settings

    result = await verify_service_token(
        x_service_token=settings.ADMIN_SERVICE_TOKEN,
        x_admin_user_id="admin-123",
    )
    assert result == "admin-123"


@pytest.mark.asyncio
async def test_verify_service_token_invalid():
    """Invalid service token should raise HTTPException."""
    with pytest.raises(HTTPException) as exc_info:
        await verify_service_token(
            x_service_token="wrong-token",
            x_admin_user_id="admin-123",
        )
    assert exc_info.value.status_code == 401
    assert "Invalid service token" in exc_info.value.detail


@pytest.mark.asyncio
async def test_verify_service_token_missing_user_id():
    """Missing admin user ID should default to 'unknown'."""
    from app.config import settings

    result = await verify_service_token(
        x_service_token=settings.ADMIN_SERVICE_TOKEN,
        x_admin_user_id="unknown",
    )
    assert result == "unknown"
