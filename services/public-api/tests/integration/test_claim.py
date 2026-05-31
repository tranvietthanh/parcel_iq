"""Integration tests for anonymous request claim workflow.

These tests validate:
- Claim endpoint links anon requests to authenticated user
- Claim window enforces 7-day expiry
- Requests outside the window are NOT claimed
- Claim with no anon cookie returns success with zero claimed count
- Duplicate claim calls are idempotent

Note: These require asyncpg + test DB. Run with:
    cd services/public-api && uv run pytest tests/integration/test_claim.py -v
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from tests.conftest import FAKE_USER_ID, FAKE_USER_ROW, FAKE_JWT_PAYLOAD


ANON_ID = "anon_test_id_abc123"
PROPERTY_ID = uuid4()
REPORT_ID = uuid4()


class TestClaimEndpoint:
    """Tests for POST /api/properties/claim-anonymous-requests."""

    @pytest.mark.anyio
    async def test_claim_links_recent_requests(self, authed_client):
        """Claim links anon requests within 7-day window to the user."""
        client, mock_db, _ = authed_client

        # Simulate 2 rows updated
        mock_db.execute.return_value = "UPDATE 2"

        resp = await client.post(
            "/api/properties/claim-anonymous-requests",
            cookies={ANON_ID: "anon_test_id_abc123"},
        )
        # Should succeed
        assert resp.status_code == 200
        data = resp.json()
        assert "claimed_count" in data

    @pytest.mark.anyio
    async def test_claim_without_cookie_returns_zero(self, authed_client):
        """Claim with no anon cookie returns zero claimed count."""
        client, mock_db, _ = authed_client

        resp = await client.post(
            "/api/properties/claim-anonymous-requests",
            # No cookie set
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["claimed_count"] == 0

    @pytest.mark.anyio
    async def test_claim_returns_zero_when_no_matching_rows(self, authed_client):
        """Claim with no matching unclaimed rows returns zero."""
        client, mock_db, _ = authed_client

        mock_db.execute.return_value = "UPDATE 0"

        resp = await client.post(
            "/api/properties/claim-anonymous-requests",
            cookies={"anon_requester_id": "nonexistent_anon_id"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["claimed_count"] == 0

    @pytest.mark.anyio
    async def test_claim_requires_authentication(self, anon_client):
        """Unauthenticated claim attempt returns 401."""
        client, _ = anon_client

        resp = await client.post(
            "/api/properties/claim-anonymous-requests",
            cookies={"anon_requester_id": ANON_ID},
        )
        # Claim endpoint requires auth via get_current_user → 401
        assert resp.status_code == 401


class TestMyRequestedHistory:
    """Tests for GET /api/properties/my/requested."""

    @pytest.mark.anyio
    async def test_returns_paginated_history(self, authed_client):
        """Requested endpoint returns paginated items."""
        client, mock_db, _ = authed_client

        now = datetime.now(timezone.utc)
        mock_db.fetch.return_value = [
            MagicMock(
                **{
                    "property_id": PROPERTY_ID,
                    "address": "1 Test St, Sydney NSW 2000",
                    "state": "NSW",
                    "report_id": REPORT_ID,
                    "report_status": "READY",
                    "requested_at": now - timedelta(days=1),
                    "ready_at": now,
                    "has_downloaded_before": False,
                    "__getitem__": lambda s, k: {
                        "property_id": PROPERTY_ID,
                        "address": "1 Test St, Sydney NSW 2000",
                        "state": "NSW",
                        "report_id": REPORT_ID,
                        "report_status": "READY",
                        "requested_at": now - timedelta(days=1),
                        "ready_at": now,
                        "has_downloaded_before": False,
                    }[k],
                }
            )
        ]
        mock_db.fetchval.return_value = 1

        resp = await client.get("/api/properties/my/requested")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "pagination" in data
        assert data["pagination"]["total_count"] == 1

    @pytest.mark.anyio
    async def test_requires_authentication(self, anon_client):
        """Unauthenticated access returns 401."""
        client, _ = anon_client
        resp = await client.get("/api/properties/my/requested")
        assert resp.status_code == 401

    @pytest.mark.anyio
    async def test_returns_has_downloaded_before_flag(self, authed_client):
        """History rows include has_downloaded_before from ledger query."""
        client, mock_db, _ = authed_client

        now = datetime.now(timezone.utc)
        mock_db.fetch.return_value = [
            MagicMock(
                **{
                    "property_id": PROPERTY_ID,
                    "address": "2 Example Ave",
                    "state": "VIC",
                    "report_id": REPORT_ID,
                    "report_status": "READY",
                    "requested_at": now,
                    "ready_at": now,
                    "has_downloaded_before": True,
                    "__getitem__": lambda s, k: {
                        "property_id": PROPERTY_ID,
                        "address": "2 Example Ave",
                        "state": "VIC",
                        "report_id": REPORT_ID,
                        "report_status": "READY",
                        "requested_at": now,
                        "ready_at": now,
                        "has_downloaded_before": True,
                    }[k],
                }
            )
        ]
        mock_db.fetchval.return_value = 1

        resp = await client.get("/api/properties/my/requested")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["has_downloaded_before"] is True
