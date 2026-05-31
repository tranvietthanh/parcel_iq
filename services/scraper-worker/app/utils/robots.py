"""robots.txt compliance checker.

Before any headless browser scrape, we check the target domain's
robots.txt to ensure the path is allowed.  This is non-negotiable —
violating robots.txt is both a legal and ethical risk.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

logger = logging.getLogger(__name__)

# Bot name used in robots.txt checks
USER_AGENT = "OZPropertyReportBot/1.0"


@lru_cache(maxsize=256)
def _fetch_robots(domain: str) -> RobotFileParser:
    """Fetch and parse robots.txt for a domain.  Cached per domain."""
    robots_url = f"{domain}/robots.txt"
    rp = RobotFileParser()
    rp.set_url(robots_url)

    try:
        resp = httpx.get(robots_url, timeout=10, follow_redirects=True)
        if resp.status_code == 200:
            rp.parse(resp.text.splitlines())
        else:
            # No robots.txt or error — allow everything
            rp.allow_all = True
    except Exception:
        logger.warning("Could not fetch %s — allowing by default", robots_url)
        rp.allow_all = True

    return rp


def is_scraping_allowed(base_url: str, path: str = "/") -> bool:
    """Check whether *path* on *base_url* is allowed by robots.txt.

    Parameters
    ----------
    base_url:
        The full base URL of the site (e.g. ``https://planning.council.vic.gov.au``).
    path:
        The path to check (default ``/``).

    Returns
    -------
    ``True`` if scraping is allowed (or robots.txt is unavailable).
    """
    if not base_url:
        return True

    parsed = urlparse(base_url)
    domain = f"{parsed.scheme}://{parsed.netloc}"

    try:
        rp = _fetch_robots(domain)
        return rp.can_fetch(USER_AGENT, path)
    except Exception:
        logger.warning("robots.txt check failed for %s — allowing by default", domain)
        return True
