"""Redis token bucket rate limiter and daily quota tracking for LLM API calls.

Cross-process safe — multiple Celery worker processes on the same pod
all share one rate limit counter via Redis.

Uses Redis WATCH/MULTI for optimistic locking.
Supports any configured LLM provider (OpenAI, Anthropic, Google AI).
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import redis as redis_lib

from app.config import settings

logger = logging.getLogger(__name__)

redis_client = redis_lib.from_url(settings.REDIS_URL, decode_responses=True)

# Rate limit & quota Redis keys (provider-agnostic)
TOKEN_KEY = "llm:rate_limit:tokens"
LAST_REFILL_KEY = "llm:rate_limit:last_refill"
DAILY_COUNT_KEY_PREFIX = "llm:daily_count:"

WINDOW_SECONDS = 60


def wait_for_token(max_wait_seconds: int = 240) -> None:
    """Block until a rate-limit token is available, up to max_wait_seconds.

    Safe to call from multiple Celery worker processes simultaneously.
    Uses Redis optimistic locking (WATCH) to prevent race conditions.
    Raises RuntimeError with RATE_LIMIT prefix if deadline is exceeded.
    """
    deadline = time.monotonic() + max_wait_seconds
    while True:
        if time.monotonic() > deadline:
            raise RuntimeError("RATE_LIMIT: token wait exceeded max_wait_seconds")

        with redis_client.pipeline() as pipe:
            try:
                pipe.watch(TOKEN_KEY, LAST_REFILL_KEY)

                tokens = int(pipe.get(TOKEN_KEY) or settings.LLM_MAX_RPM)
                last_refill = float(pipe.get(LAST_REFILL_KEY) or time.time())
                now = time.time()
                elapsed = now - last_refill

                # Refill tokens based on elapsed time
                token_interval = WINDOW_SECONDS / settings.LLM_MAX_RPM
                tokens_to_add = int(elapsed / token_interval)

                if tokens_to_add > 0:
                    tokens = min(settings.LLM_MAX_RPM, tokens + tokens_to_add)
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
                    remaining_deadline = deadline - time.monotonic()
                    if remaining_deadline <= 0:
                        raise RuntimeError("RATE_LIMIT: token wait exceeded max_wait_seconds")
                    sleep_secs = token_interval - (elapsed % token_interval)
                    sleep_secs = max(0.5, min(sleep_secs, remaining_deadline))
                    logger.debug("No tokens available, sleeping %.1fs", sleep_secs)
                    time.sleep(sleep_secs)

            except redis_lib.WatchError:
                # Another worker modified the keys — retry immediately
                continue


def _get_today_utc_str() -> str:
    """Return current UTC date in YYYY-MM-DD format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def is_daily_quota_exhausted() -> bool:
    """Non-mutating check. Read-only GET, never increments."""
    today = _get_today_utc_str()
    key = f"{DAILY_COUNT_KEY_PREFIX}{today}"
    try:
        count = int(redis_client.get(key) or 0)
    except redis_lib.RedisError as e:
        logger.warning("Redis error checking daily quota: %s", e)
        return False
    return count >= settings.LLM_DAILY_QUOTA


def record_llm_request() -> None:
    """Call ONLY after a successful provider response — counts real usage."""
    today = _get_today_utc_str()
    key = f"{DAILY_COUNT_KEY_PREFIX}{today}"
    try:
        if redis_client.incr(key) == 1:
            redis_client.expire(key, 86_400)
    except redis_lib.RedisError as e:
        logger.warning("Failed to record LLM request count in Redis: %s", e)


def get_daily_usage() -> tuple[int, int]:
    """Return (current_count, daily_limit) for monitoring."""
    today = _get_today_utc_str()
    key = f"{DAILY_COUNT_KEY_PREFIX}{today}"
    try:
        count = int(redis_client.get(key) or 0)
    except redis_lib.RedisError:
        count = 0
    return count, settings.LLM_DAILY_QUOTA
