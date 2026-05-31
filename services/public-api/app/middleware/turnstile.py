"""Cloudflare Turnstile verification middleware.

Applied to anonymous search endpoints. Verifies the X-Turnstile-Token header
against Cloudflare's siteverify API.
"""

from __future__ import annotations

import httpx
from fastapi import HTTPException, Request

from app.config import settings

TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


async def verify_turnstile(request: Request) -> None:
    """FastAPI dependency that verifies a Cloudflare Turnstile token.

    In development (secret = test key), Cloudflare always returns success.
    In development, token is optional — allows local testing without Turnstile widget.
    """
    token = request.headers.get("X-Turnstile-Token")
    
    # In development, allow requests without token (for easier local testing)
    if settings.ENVIRONMENT == "development" and not token:
        return

    if not token:
        raise HTTPException(status_code=403, detail="Turnstile token required.")

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            TURNSTILE_VERIFY_URL,
            data={
                "secret": settings.TURNSTILE_SECRET_KEY,
                "response": token,
                "remoteip": request.client.host if request.client else None,
            },
        )
    result = resp.json()
    if not result.get("success"):
        raise HTTPException(status_code=403, detail="Turnstile verification failed.")
