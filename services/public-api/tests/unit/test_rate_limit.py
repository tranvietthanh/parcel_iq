"""Unit tests for rate-limit key extraction.

The key function must only trust a Clerk ``sub`` after verifying the JWT
signature against the JWKS — otherwise a client could forge/rotate ``sub`` to
evade its per-user limit. An unverifiable token falls back to the client IP.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from jose import JWTError

from app.core.rate_limit import rate_limit_key


class TestRateLimitKey:
    def test_anonymous_returns_ip(self):
        request = MagicMock()
        request.headers = {}
        request.client.host = "1.2.3.4"
        key = rate_limit_key(request)
        assert key == "1.2.3.4"

    @patch("app.core.rate_limit.jwt.decode", return_value={"sub": "user_xyz"})
    @patch("app.core.rate_limit.get_jwks", return_value={"keys": []})
    def test_verified_token_returns_clerk_id(self, _jwks, _decode):
        """A JWT that verifies against the JWKS yields ``clerk:<sub>``."""
        request = MagicMock()
        request.headers = {"Authorization": "Bearer header.payload.sig"}
        request.client.host = "1.2.3.4"

        key = rate_limit_key(request)
        assert key == "clerk:user_xyz"

    @patch("app.core.rate_limit.jwt.decode", side_effect=JWTError("bad signature"))
    @patch("app.core.rate_limit.get_jwks", return_value={"keys": []})
    def test_unverifiable_token_falls_back_to_ip(self, _jwks, _decode):
        """A forged/invalid token must NOT be trusted — fall back to IP."""
        request = MagicMock()
        request.headers = {"Authorization": "Bearer forged.unsigned.token"}
        request.client.host = "5.6.7.8"

        key = rate_limit_key(request)
        assert key == "5.6.7.8"

    def test_malformed_bearer_falls_back_to_ip(self):
        request = MagicMock()
        request.headers = {"Authorization": "Bearer not.a.real.jwt"}
        request.client.host = "5.6.7.8"
        key = rate_limit_key(request)
        assert key == "5.6.7.8"
