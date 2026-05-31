"""Redis token bucket rate limiter for LLM API calls.

Cross-process safe — multiple Celery worker processes on the same pod
all share one rate limit counter via Redis.

Uses Redis WATCH/MULTI for optimistic locking.
Supports Gemini, NVIDIA, GitHub Models, and Ollama APIs.
"""

from __future__ import annotations

import logging
import time

import redis as redis_lib

from app.config import settings

logger = logging.getLogger(__name__)

redis_client = redis_lib.from_url(settings.REDIS_URL, decode_responses=True)

# Rate limit settings (OpenAI)
# The worker uses OpenAI via `OPENAI_*` settings. Keep keys namespaced
# under `openai:` in Redis to avoid collisions with other services.
MAX_RPM = settings.OPENAI_MAX_RPM
DAILY_QUOTA = settings.OPENAI_DAILY_QUOTA
TOKEN_KEY = "openai:rate_limit:tokens"
LAST_REFILL_KEY = "openai:rate_limit:last_refill"
DAILY_COUNT_KEY_PREFIX = "openai:daily_count:"

WINDOW_SECONDS = 60


def wait_for_token() -> None:
    """Block until a rate-limit token is available.

    Safe to call from multiple Celery worker processes simultaneously.
    Uses Redis optimistic locking (WATCH) to prevent race conditions.
    """
    while True:
        with redis_client.pipeline() as pipe:
            try:
                pipe.watch(TOKEN_KEY, LAST_REFILL_KEY)

                tokens = int(pipe.get(TOKEN_KEY) or MAX_RPM)
                last_refill = float(pipe.get(LAST_REFILL_KEY) or time.time())
                now = time.time()
                elapsed = now - last_refill

                # Refill tokens based on elapsed time
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
                    logger.debug("Rate limit token acquired (%d remaining)", tokens - 1)
                    return  # Token acquired — proceed with API call
                else:
                    # No tokens — wait one token interval before retrying
                    sleep_secs = token_interval - (elapsed % token_interval)
                    sleep_secs = max(0.5, sleep_secs)
                    logger.debug("No tokens available, sleeping %.1fs", sleep_secs)
                    time.sleep(sleep_secs)

            except redis_lib.WatchError:
                # Another worker modified the keys — retry immediately
                continue


def check_daily_quota() -> None:
    """Raise an exception if the daily quota is exhausted.

    The job stays in the queue and will be retried later.
    """
    today = time.strftime("%Y-%m-%d")
    key = f"{DAILY_COUNT_KEY_PREFIX}{today}"

    count = redis_client.incr(key)
    if count == 1:
        redis_client.expire(key, 86_400)  # Auto-expire at end of day

    if count > DAILY_QUOTA:
        raise RuntimeError(
            f"DAILY_QUOTA_EXCEEDED: {count}/{DAILY_QUOTA} OpenAI requests used today. "
            "Task will retry tomorrow."
        )


def get_daily_usage() -> tuple[int, int]:
    """Return (current_count, daily_limit) for monitoring."""
    today = time.strftime("%Y-%m-%d")
    key = f"{DAILY_COUNT_KEY_PREFIX}{today}"
    count = int(redis_client.get(key) or 0)
    return count, DAILY_QUOTA
