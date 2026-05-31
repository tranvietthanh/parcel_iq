"""Clerk JWT verification using JWKS endpoint.

The Public API verifies every JWT issued by the Public Clerk instance.
Clerk is the single source of truth for authentication — no self-issued JWTs.
"""

from __future__ import annotations

import threading
import time

import httpx
from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.config import settings

_bearer_scheme = HTTPBearer(auto_error=False)
_bearer_scheme_required = HTTPBearer()

_JWKS_TTL_SECONDS = 30 * 60
_jwks_cache: dict[str, object] = {"expires_at": 0.0, "jwks": None}
_jwks_lock = threading.Lock()


def get_jwks() -> dict:
    """Fetch Clerk JWKS with a short TTL to tolerate key rotation."""
    now = time.monotonic()
    with _jwks_lock:
        cached = _jwks_cache["jwks"]
        if cached is not None and now < float(_jwks_cache["expires_at"]):
            return cached  # type: ignore[return-value]

        resp = httpx.get(settings.CLERK_PUBLIC_JWKS_URL, timeout=10)
        resp.raise_for_status()
        jwks = resp.json()
        _jwks_cache["jwks"] = jwks
        _jwks_cache["expires_at"] = now + _JWKS_TTL_SECONDS
        return jwks


def clear_jwks_cache() -> None:
    """Clear JWKS cache so token verification can retry after key rotation."""
    with _jwks_lock:
        _jwks_cache["jwks"] = None
        _jwks_cache["expires_at"] = 0.0


get_jwks.cache_clear = clear_jwks_cache  # type: ignore[attr-defined]


async def verify_clerk_token(
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer_scheme),
) -> dict | None:
    """Verify the Clerk JWT.  Returns decoded payload or *None* if no token.

    Used for **optional auth** — anonymous endpoints that return more data when
    the user is signed in.
    """
    if not credentials:
        return None
    for should_refresh in (False, True):
        try:
            if should_refresh:
                clear_jwks_cache()
            jwks = get_jwks()
            payload = jwt.decode(
                credentials.credentials,
                jwks,
                algorithms=["RS256"],
                options={"verify_aud": False},  # Clerk tokens don't use standard aud
            )
            return payload
        except JWTError:
            if should_refresh:
                return None
    return None


async def require_auth(
    credentials: HTTPAuthorizationCredentials = Security(_bearer_scheme_required),
) -> dict:
    """Require a valid Clerk JWT.  Raises 401 if missing or invalid.

    Returns decoded payload with ``sub`` = clerk_user_id.
    """
    payload = await verify_clerk_token(credentials)
    if not payload:
        raise HTTPException(status_code=401, detail="Valid authentication required.")
    return payload
