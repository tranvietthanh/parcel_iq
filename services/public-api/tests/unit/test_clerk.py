"""Unit tests for Clerk JWT verification logic and plan extraction."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.core.clerk import extract_plan_from_jwt, get_jwks, require_auth, verify_clerk_token
from jose import JWTError


class TestGetJwks:
    @patch("app.core.clerk.httpx.get")
    def test_returns_json(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"keys": [{"kty": "RSA"}]}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        # Clear cache first
        get_jwks.cache_clear()
        result = get_jwks()
        assert result == {"keys": [{"kty": "RSA"}]}
        get_jwks.cache_clear()

    @patch("app.core.clerk.httpx.get")
    def test_cached(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"keys": []}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        get_jwks.cache_clear()
        get_jwks()
        get_jwks()
        # Only one HTTP call due to caching
        assert mock_get.call_count == 1
        get_jwks.cache_clear()


class TestVerifyClerkToken:
    @pytest.mark.asyncio
    async def test_no_credentials_returns_none(self):
        result = await verify_clerk_token(None)
        assert result is None

    @pytest.mark.asyncio
    @patch("app.core.clerk.get_jwks")
    @patch("app.core.clerk.jwt.decode")
    async def test_valid_token(self, mock_decode, mock_jwks):
        mock_jwks.return_value = {"keys": []}
        mock_decode.return_value = {"sub": "user_123"}

        creds = MagicMock()
        creds.credentials = "valid.jwt.token"

        result = await verify_clerk_token(creds)
        assert result == {"sub": "user_123"}

    @pytest.mark.asyncio
    @patch("app.core.clerk.get_jwks")
    @patch("app.core.clerk.jwt.decode", side_effect=JWTError("bad"))
    async def test_invalid_token_returns_none(self, mock_decode, mock_jwks):
        mock_jwks.return_value = {"keys": []}

        creds = MagicMock()
        creds.credentials = "bad.jwt"

        result = await verify_clerk_token(creds)
        assert result is None


class TestRequireAuth:
    @pytest.mark.asyncio
    @patch("app.core.clerk.verify_clerk_token", return_value=None)
    async def test_no_token_raises_401(self, _):
        creds = MagicMock()
        creds.credentials = "bad"
        with pytest.raises(HTTPException) as exc:
            await require_auth(creds)
        assert exc.value.status_code == 401


class TestExtractPlanFromJwt:
    def test_no_pla_claim_returns_free(self):
        assert extract_plan_from_jwt({"sub": "user_123"}) == "FREE"

    def test_pla_pro(self):
        assert extract_plan_from_jwt({"sub": "user_123", "pla": "u:pro"}) == "PRO"

    def test_pla_unlimited(self):
        assert extract_plan_from_jwt({"sub": "user_123", "pla": "u:unlimited"}) == "UNLIMITED"

    def test_pla_unknown_slug_returns_free(self):
        assert extract_plan_from_jwt({"sub": "user_123", "pla": "u:enterprise"}) == "FREE"

    def test_pla_org_prefix_returns_free(self):
        # Org-level plans are not used in this app — treat as FREE
        assert extract_plan_from_jwt({"sub": "user_123", "pla": "o:pro"}) == "FREE"

    def test_pla_empty_string_returns_free(self):
        assert extract_plan_from_jwt({"sub": "user_123", "pla": ""}) == "FREE"

    def test_pla_free_slug_returns_free(self):
        assert extract_plan_from_jwt({"sub": "user_123", "pla": "u:free"}) == "FREE"
