"""robots.txt compliance checker.

Before any headless browser scrape, we check the target domain's robots.txt to
ensure the path is allowed. This is non-negotiable — violating robots.txt is
both a legal and ethical risk.

Failure policy:
  - HTTP 200            → parse and honour the rules.
  - HTTP 4xx (e.g. 404) → no robots.txt exists; scraping is allowed (convention).
  - Network error / 5xx → we could NOT verify the policy, so we FAIL CLOSED and
    disallow. Scraping on an unverified policy is the risk we're trying to avoid.

Results are cached per domain with a TTL so policy changes are eventually picked
up (an unbounded cache would pin a stale robots.txt for the worker's lifetime).
"""

from __future__ import annotations

import logging
import time
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

logger = logging.getLogger(__name__)

# Bot name used in robots.txt checks
USER_AGENT = "OZPropertyReportBot/1.0"

# How long a fetched robots.txt is trusted before we re-fetch.
_ROBOTS_TTL_SECONDS = 60 * 60  # 1 hour

# domain -> (expires_at_monotonic, parser_or_None). A None parser means the
# fetch failed and callers must fail closed.
_robots_cache: dict[str, tuple[float, RobotFileParser | None]] = {}


def _fetch_robots(domain: str) -> RobotFileParser | None:
    """Fetch and parse robots.txt for *domain*, cached with a TTL.

    Returns a parser on success (including the "no robots.txt" case, where all
    paths are allowed), or ``None`` when the policy could not be verified.
    """
    now = time.monotonic()
    cached = _robots_cache.get(domain)
    if cached is not None and now < cached[0]:
        return cached[1]

    robots_url = f"{domain}/robots.txt"
    rp: RobotFileParser | None

    try:
        resp = httpx.get(robots_url, timeout=10, follow_redirects=True)
        if resp.status_code == 200:
            rp = RobotFileParser()
            rp.parse(resp.text.splitlines())
        elif 400 <= resp.status_code < 500:
            # No robots.txt (or not accessible) — by convention, allow everything.
            rp = RobotFileParser()
            rp.allow_all = True
        else:
            # 5xx or other — policy unknown. Fail closed.
            logger.warning(
                "robots.txt for %s returned %s — failing closed", domain, resp.status_code
            )
            rp = None
    except Exception:
        logger.warning("Could not fetch %s — failing closed", robots_url)
        rp = None

    _robots_cache[domain] = (now + _ROBOTS_TTL_SECONDS, rp)
    return rp


def is_scraping_allowed(base_url: str, path: str = "/") -> bool:
    """Check whether *path* on *base_url* is allowed by robots.txt.

    Returns ``True`` only when the policy was verified and permits the path (or
    no robots.txt exists). Returns ``False`` when the policy could not be
    fetched/verified — we do not scrape on an unverified policy.
    """
    if not base_url:
        return True

    parsed = urlparse(base_url)
    domain = f"{parsed.scheme}://{parsed.netloc}"

    rp = _fetch_robots(domain)
    if rp is None:
        # Could not verify the policy — fail closed.
        return False
    return rp.can_fetch(USER_AGENT, path)
