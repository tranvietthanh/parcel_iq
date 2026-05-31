"""Retry with exponential backoff utility."""

from __future__ import annotations

import logging
import time
from typing import Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def retry_with_backoff(
    func: Callable[[], T],
    retries: int = 3,
    delay: float = 2.0,
    backoff_factor: float = 2.0,
) -> T:
    """Call *func* with exponential backoff on failure.

    Parameters
    ----------
    func:
        Zero-argument callable to retry.
    retries:
        Maximum number of retry attempts.
    delay:
        Initial delay in seconds before the first retry.
    backoff_factor:
        Multiplier applied to the delay after each failure.

    Returns
    -------
    The return value of *func* on success.

    Raises
    ------
    Exception
        The last exception raised by *func* after all retries are exhausted.
    """
    last_exc: Exception | None = None

    for attempt in range(retries + 1):
        try:
            return func()
        except Exception as exc:
            last_exc = exc
            if attempt < retries:
                wait = delay * (backoff_factor**attempt)
                logger.warning(
                    "Attempt %d/%d failed (%s).  Retrying in %.1fs…",
                    attempt + 1,
                    retries + 1,
                    exc,
                    wait,
                )
                time.sleep(wait)
            else:
                logger.error(
                    "All %d attempts failed.  Last error: %s",
                    retries + 1,
                    exc,
                )

    raise last_exc  # type: ignore[misc]
