"""Redis token bucket rate limiter for scraper HTTP requests.

Shared across worker processes to maintain a steady outbound request rate
to external services (default 20 RPM). Uses Redis WATCH/MULTI for optimistic
locking similar to the LLM worker's rate limiter.
"""

from __future__ import annotations

import logging
import time

import redis as redis_lib

from app.config import settings

logger = logging.getLogger(__name__)

redis_client = redis_lib.from_url(settings.REDIS_URL, decode_responses=True)

MAX_RPM = settings.SCRAPER_MAX_RPM
WINDOW_SECONDS = 60
TOKEN_KEY = "scraper:rate_limit:tokens"
LAST_REFILL_KEY = "scraper:rate_limit:last_refill"


def wait_for_token() -> None:
    """Block until a rate-limit token is available.

    Safe to call from multiple Celery worker processes simultaneously.
    """
    while True:
        with redis_client.pipeline() as pipe:
            try:
                pipe.watch(TOKEN_KEY, LAST_REFILL_KEY)

                tokens = int(pipe.get(TOKEN_KEY) or MAX_RPM)
                last_refill = float(pipe.get(LAST_REFILL_KEY) or time.time())
                now = time.time()
                elapsed = now - last_refill

                token_interval = WINDOW_SECONDS / MAX_RPM
                tokens_to_add = int(elapsed / token_interval)

                if tokens_to_add > 0:
                    tokens = min(MAX_RPM, tokens + tokens_to_add)
                    last_refill = now

                if tokens > 0:
                    pipe.multi()
                    pipe.set(TOKEN_KEY, tokens - 1)
                    pipe.set(LAST_REFILL_KEY, last_refill)
                    pipe.execute()
                    logger.debug("Scraper rate token acquired (%d remaining)", tokens - 1)
                    return
                else:
                    sleep_secs = token_interval - (elapsed % token_interval)
                    sleep_secs = max(0.5, sleep_secs)
                    logger.debug("No scraper tokens, sleeping %.1fs", sleep_secs)
                    time.sleep(sleep_secs)

            except redis_lib.WatchError:
                continue
