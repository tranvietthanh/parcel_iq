"""Unit tests for rate-limit key extraction."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.core.rate_limit import rate_limit_key


class TestRateLimitKey:
    def test_anonymous_returns_ip(self):
        request = MagicMock()
        request.headers = {}
        request.client.host = "1.2.3.4"
        key = rate_limit_key(request)
        assert key == "1.2.3.4"

    def test_bearer_token_returns_clerk_id(self):
        """When the Authorization header contains a valid JWT with a sub claim,
        the key should use ``clerk:<sub>``."""
        # Build a minimal unsigned JWT payload with sub
        import base64
        import json

        payload = base64.urlsafe_b64encode(
            json.dumps({"sub": "user_xyz"}).encode()
        ).decode().rstrip("=")
        # Fake JWT: header.payload.signature
        fake_jwt = f"eyJhbGciOiJSUzI1NiJ9.{payload}.fakesig"

        request = MagicMock()
        request.headers = {"Authorization": f"Bearer {fake_jwt}"}
        request.client.host = "1.2.3.4"

        key = rate_limit_key(request)
        assert key == "clerk:user_xyz"

    def test_malformed_bearer_falls_back_to_ip(self):
        request = MagicMock()
        request.headers = {"Authorization": "Bearer not.a.real.jwt"}
        request.client.host = "5.6.7.8"
        key = rate_limit_key(request)
        assert key == "5.6.7.8"
