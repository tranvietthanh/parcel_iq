"""Integration tests for the credit endpoints (wallet summary + precheck).

Tests:
- GET /api/credits/me returns wallet summary
- GET /api/properties/{id}/full/precheck returns duplicate indicator
- Credit endpoints require authentication
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

PROPERTY_ID = uuid4()


class TestCreditsMeEndpoint:
    """Tests for GET /api/credits/me."""

    @pytest.mark.anyio
    async def test_returns_wallet_summary(self, authed_client):
        """Authenticated user receives their wallet summary."""
        client, mock_db, _ = authed_client

        wallet_row = {
            "daily_grant_credits": 3,
            "daily_used_credits": 1,
            "purchased_credits_balance": 5,
            "wallet_day_au": datetime.now(timezone.utc).date(),
            "daily_remaining": 2,
        }
        row = MagicMock()
        row.__getitem__ = lambda s, k: wallet_row[k]
        mock_db.fetchrow.return_value = row

        resp = await client.get("/api/credits/me")
        assert resp.status_code == 200
        data = resp.json()
        assert "daily_remaining" in data
        assert "purchased_balance" in data
        assert "total_spendable" in data
        assert "daily_grant" in data

    @pytest.mark.anyio
    async def test_requires_authentication(self, anon_client):
        """Unauthenticated request returns 401."""
        client, _ = anon_client
        resp = await client.get("/api/credits/me")
        assert resp.status_code == 401


class TestDownloadPrecheck:
    """Tests for GET /api/properties/{id}/full/precheck."""

    @pytest.mark.anyio
    async def test_returns_not_duplicate_for_first_download(self, authed_client):
        """No prior download returns is_duplicate_download=False."""
        client, mock_db, _ = authed_client

        # No ledger entry found
        mock_db.fetchrow.return_value = None

        resp = await client.get(f"/api/properties/{PROPERTY_ID}/full/precheck")
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_duplicate_download"] is False
        assert data["previous_download_at"] is None

    @pytest.mark.anyio
    async def test_returns_duplicate_for_prior_download(self, authed_client):
        """Prior DOWNLOAD_DEBIT entry returns is_duplicate_download=True."""
        client, mock_db, _ = authed_client

        prior_at = datetime.now(timezone.utc)
        prior_row = MagicMock()
        prior_row.__getitem__ = lambda s, k: {"created_at": prior_at}[k]

        # fetchrow returns ledger entry (prior download), then wallet row
        mock_db.fetchrow.side_effect = [prior_row, None]

        resp = await client.get(f"/api/properties/{PROPERTY_ID}/full/precheck")
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_duplicate_download"] is True
        assert data["previous_download_at"] is not None

    @pytest.mark.anyio
    async def test_precheck_requires_authentication(self, anon_client):
        """Unauthenticated precheck returns 401."""
        client, _ = anon_client
        resp = await client.get(f"/api/properties/{PROPERTY_ID}/full/precheck")
        assert resp.status_code == 401

    @pytest.mark.anyio
    async def test_precheck_includes_advisory_note(self, authed_client):
        """Precheck response includes the advisory note."""
        client, mock_db, _ = authed_client
        mock_db.fetchrow.return_value = None

        resp = await client.get(f"/api/properties/{PROPERTY_ID}/full/precheck")
        assert resp.status_code == 200
        data = resp.json()
        assert "note" in data
        assert "advisory" in data["note"].lower()
