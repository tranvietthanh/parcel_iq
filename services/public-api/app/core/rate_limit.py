"""slowapi rate-limiter configuration.

Key function uses the Clerk user ID for authenticated requests and the client
IP for anonymous ones. The JWT is *verified* against Clerk's JWKS before its
``sub`` is trusted — otherwise a client could forge or rotate the ``sub`` claim
to evade its per-user limit or poison another user's bucket.

Storage is Redis so limits are shared across API replicas (in-memory storage
would make every limit per-pod).
"""

from __future__ import annotations

from jose import jwt
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from app.config import settings
from app.core.clerk import get_jwks


def rate_limit_key(request: Request) -> str:
    """Verified Clerk user ID for authenticated requests, IP for anonymous."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
        try:
            payload = jwt.decode(
                token,
                get_jwks(),
                algorithms=["RS256"],
                options={"verify_aud": False},  # Clerk tokens don't use standard aud
            )
            sub = payload.get("sub")
            if isinstance(sub, str) and 1 <= len(sub) <= 64:
                return f"clerk:{sub}"
        except Exception:
            # Invalid/unverifiable token, or JWKS unavailable — fall back to IP
            # rather than trusting an unverified claim.
            pass
    return get_remote_address(request)


limiter = Limiter(key_func=rate_limit_key, storage_uri=settings.REDIS_URL)
