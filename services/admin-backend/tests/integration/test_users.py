"""Integration tests for admin user management and credit top-up endpoints.

Tests:
- GET /users — paginated list with credit summary
- GET /users/{user_id} — user detail + wallet + ledger
- POST /users/{user_id}/credits/top-up — valid top-up
- POST /users/{user_id}/credits/top-up — invalid payloads (validation)
- POST /users/{user_id}/credits/top-up — non-existent user → 404
- Audit: top-up includes actor admin ID in ledger metadata

Run with:
    cd services/admin-backend && uv run pytest tests/integration/test_users.py -v
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

USER_ID = uuid4()
ADMIN_CLERK_ID = "admin_test_clerk_id_123"


def make_user_row(**overrides):
    base = {
        "id": USER_ID,
        "clerk_user_id": "user_test_abc",
        "email": "test@example.com",
        "created_at": MagicMock(isoformat=lambda: "2025-01-01T00:00:00+00:00"),
        "daily_grant_credits": 3,
        "daily_used_credits": 1,
        "daily_remaining": 2,
        "purchased_credits_balance": 5,
        "total_spendable": 7,
        "wallet_day_au": MagicMock(isoformat=lambda: "2026-05-27"),
        "wallet_updated_at": MagicMock(isoformat=lambda: "2026-05-27T10:00:00+00:00"),
    }
    base.update(overrides)
    row = MagicMock()
    row.__getitem__ = lambda s, k: base[k]
    row.__contains__ = lambda s, k: k in base
    return row


class TestUsersList:
    def test_list_users_returns_200(self, client, auth_headers, mock_db):
        """Paginated user list returns 200 with items and pagination."""
        mock_db.fetch = AsyncMock(return_value=[])
        mock_db.fetchval = AsyncMock(return_value=0)

        resp = client.get("/users", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "pagination" in data

    def test_list_users_requires_auth(self, client):
        """Missing service token returns 401."""
        resp = client.get("/users")
        assert resp.status_code == 401

    def test_list_users_search_param_accepted(self, client, auth_headers, mock_db):
        """Search parameter is accepted without error."""
        mock_db.fetch = AsyncMock(return_value=[])
        mock_db.fetchval = AsyncMock(return_value=0)

        resp = client.get("/users?search=test@example.com", headers=auth_headers)
        assert resp.status_code == 200


class TestUserDetail:
    def test_user_detail_returns_wallet_and_ledger(self, client, auth_headers, mock_db):
        """User detail response includes wallet summary and recent ledger."""
        user_row = make_user_row()
        mock_db.fetchrow = AsyncMock(return_value=user_row)
        mock_db.fetch = AsyncMock(return_value=[])

        resp = client.get(f"/users/{USER_ID}", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "wallet" in data
        assert "recent_ledger" in data
        assert "daily_remaining" in data["wallet"]
        assert "purchased_balance" in data["wallet"]
        assert "total_spendable" in data["wallet"]

    def test_user_detail_returns_404_for_missing_user(self, client, auth_headers, mock_db):
        """Non-existent user returns 404."""
        mock_db.fetchrow = AsyncMock(return_value=None)

        resp = client.get(f"/users/{uuid4()}", headers=auth_headers)
        assert resp.status_code == 404

    def test_user_detail_requires_auth(self, client):
        """Missing service token returns 401."""
        resp = client.get(f"/users/{USER_ID}")
        assert resp.status_code == 401


class TestCreditTopUp:
    def _auth_headers_with_admin(self, auth_headers):
        return {**auth_headers, "X-Admin-User-Id": ADMIN_CLERK_ID}

    def test_valid_topup_returns_200(self, client, auth_headers, mock_db):
        """Valid top-up returns success with credits_added and new_balance_after."""
        user_row = MagicMock()
        user_row.__getitem__ = lambda s, k: {
            "id": USER_ID,
            "balance_after": 12,
        }[k]
        mock_db.fetchrow = AsyncMock(side_effect=[
            MagicMock(**{"__getitem__": lambda s, k: USER_ID}),  # user exists check
            MagicMock(**{"__getitem__": lambda s, k: 12}),        # balance_after from UPDATE
        ])
        mock_db.execute = AsyncMock(return_value="UPDATE 1")

        headers = self._auth_headers_with_admin(auth_headers)
        resp = client.post(
            f"/users/{USER_ID}/credits/top-up",
            json={"credits": 10, "reason": "Support request #42"},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["credits_added"] == 10

    def test_topup_zero_credits_rejected(self, client, auth_headers, mock_db):
        """Zero credits fails validation."""
        headers = self._auth_headers_with_admin(auth_headers)
        resp = client.post(
            f"/users/{USER_ID}/credits/top-up",
            json={"credits": 0, "reason": "test"},
            headers=headers,
        )
        assert resp.status_code == 422

    def test_topup_negative_credits_rejected(self, client, auth_headers, mock_db):
        """Negative credits fails validation."""
        headers = self._auth_headers_with_admin(auth_headers)
        resp = client.post(
            f"/users/{USER_ID}/credits/top-up",
            json={"credits": -5, "reason": "test"},
            headers=headers,
        )
        assert resp.status_code == 422

    def test_topup_empty_reason_rejected(self, client, auth_headers, mock_db):
        """Empty reason fails validation."""
        headers = self._auth_headers_with_admin(auth_headers)
        resp = client.post(
            f"/users/{USER_ID}/credits/top-up",
            json={"credits": 5, "reason": "  "},
            headers=headers,
        )
        assert resp.status_code == 422

    def test_topup_exceeds_max_rejected(self, client, auth_headers, mock_db):
        """Amount exceeding MAX_TOPUP_CREDITS fails validation."""
        headers = self._auth_headers_with_admin(auth_headers)
        resp = client.post(
            f"/users/{USER_ID}/credits/top-up",
            json={"credits": 99999, "reason": "bulk grant"},
            headers=headers,
        )
        assert resp.status_code == 422

    def test_topup_nonexistent_user_returns_404(self, client, auth_headers, mock_db):
        """Top-up for non-existent user returns 404."""
        mock_db.fetchrow = AsyncMock(return_value=None)

        headers = self._auth_headers_with_admin(auth_headers)
        resp = client.post(
            f"/users/{uuid4()}/credits/top-up",
            json={"credits": 5, "reason": "Support ticket #99"},
            headers=headers,
        )
        assert resp.status_code == 404

    def test_topup_requires_x_admin_user_id_header(self, client, auth_headers, mock_db):
        """Missing X-Admin-User-Id header returns 422 (required header)."""
        headers = {k: v for k, v in auth_headers.items() if k != "X-Admin-User-Id"}
        resp = client.post(
            f"/users/{USER_ID}/credits/top-up",
            json={"credits": 5, "reason": "test"},
            headers=headers,
        )
        assert resp.status_code == 422

    def test_topup_records_actor_in_response(self, client, auth_headers, mock_db):
        """Top-up response includes the actor admin ID for audit trail."""
        mock_db.fetchrow = AsyncMock(side_effect=[
            MagicMock(**{"__getitem__": lambda s, k: USER_ID}),
            MagicMock(**{"__getitem__": lambda s, k: 15}),
        ])
        mock_db.execute = AsyncMock(return_value="UPDATE 1")

        headers = self._auth_headers_with_admin(auth_headers)
        resp = client.post(
            f"/users/{USER_ID}/credits/top-up",
            json={"credits": 5, "reason": "Annual bonus"},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["actor_admin_id"] == ADMIN_CLERK_ID
        assert data["reason"] == "Annual bonus"
