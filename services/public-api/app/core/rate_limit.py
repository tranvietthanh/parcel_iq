"""slowapi rate-limiter configuration.

Key function uses Clerk user ID for authenticated requests, IP for anonymous.
"""

from __future__ import annotations

from jose import jwt
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request


def rate_limit_key(request: Request) -> str:
    """Use Clerk user ID for authenticated requests, IP for anonymous."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        try:
            payload = jwt.get_unverified_claims(auth[7:])
            sub = payload.get("sub")
            if isinstance(sub, str) and 1 <= len(sub) <= 64:
                return f"clerk:{sub}"
        except Exception:
            pass
    return get_remote_address(request)


limiter = Limiter(key_func=rate_limit_key)
