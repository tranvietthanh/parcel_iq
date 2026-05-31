"""Proxy configuration for headless browser adapters.

Proxy settings are optional — in local development, adapters that need
a proxy will run without one.  In production, the residential proxy
prevents IP bans from council domains.
"""

from __future__ import annotations

import logging

from app.config import settings

logger = logging.getLogger(__name__)


def get_proxy_config() -> dict | None:
    """Return proxy config dict for Playwright, or ``None`` if not configured.

    Returns
    -------
    Dict with ``url``, ``username``, ``password`` keys — or ``None``.
    """
    if not settings.PROXY_URL:
        return None

    return {
        "url": settings.PROXY_URL,
        "username": settings.PROXY_USERNAME,
        "password": settings.PROXY_PASSWORD,
    }
