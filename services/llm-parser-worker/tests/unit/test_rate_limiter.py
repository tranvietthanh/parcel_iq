"""Unit tests for the Redis token-bucket rate limiter.

Uses mocked Redis to test token acquisition logic, daily quota
enforcement, and refill behaviour without a running Redis server.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services import rate_limiter as rl_mod


class TestWaitForToken:
    """Tests for wait_for_token() — Redis token bucket logic."""

    @patch.object(rl_mod, "redis_client")
    def test_acquires_token_when_available(self, mock_redis: MagicMock) -> None:
        """Should acquire token and decrement counter on first try."""
        mock_pipe = MagicMock()
        mock_redis.pipeline.return_value.__enter__ = MagicMock(return_value=mock_pipe)
        mock_redis.pipeline.return_value.__exit__ = MagicMock(return_value=False)

        # pipe.get returns tokens and last_refill
        mock_pipe.get.side_effect = [str(rl_mod.MAX_RPM), "1000.0"]

        # No WatchError — transaction succeeds
        mock_pipe.watch = MagicMock()
        mock_pipe.multi = MagicMock()
        mock_pipe.set = MagicMock()
        mock_pipe.execute = MagicMock(return_value=[True, True])

        with patch("app.services.rate_limiter.time") as mock_time:
            mock_time.time.return_value = 1000.0
            rl_mod.wait_for_token()

        # Should have called set for token count and last_refill
        assert mock_pipe.set.call_count == 2

    @patch.object(rl_mod, "redis_client")
    @patch("app.services.rate_limiter.time")
    def test_waits_when_no_tokens(self, mock_time: MagicMock, mock_redis: MagicMock) -> None:
        """Should sleep and retry when no tokens are available."""
        mock_time.time.return_value = 1000.0
        mock_time.strftime = MagicMock()

        call_count = 0

        def pipe_get_side_effect(key):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                # First iteration: 0 tokens, refill time = now (no refill)
                if key == rl_mod.TOKEN_KEY:
                    return "0"
                return "1000.0"
            # Second iteration: tokens available after sleep
            if key == rl_mod.TOKEN_KEY:
                return str(rl_mod.MAX_RPM)
            return "1000.0"

        mock_pipe = MagicMock()
        mock_redis.pipeline.return_value.__enter__ = MagicMock(return_value=mock_pipe)
        mock_redis.pipeline.return_value.__exit__ = MagicMock(return_value=False)
        mock_pipe.get.side_effect = pipe_get_side_effect
        mock_pipe.watch = MagicMock()
        mock_pipe.multi = MagicMock()
        mock_pipe.set = MagicMock()
        mock_pipe.execute = MagicMock(return_value=[True, True])

        rl_mod.wait_for_token()

        # Should have slept once when no tokens were available
        mock_time.sleep.assert_called_once()


class TestCheckDailyQuota:
    """Tests for check_daily_quota() — daily usage counter."""

    @patch.object(rl_mod, "redis_client")
    def test_allows_within_quota(self, mock_redis: MagicMock) -> None:
        """Should not raise when count is within the daily limit."""
        mock_redis.incr.return_value = max(1, rl_mod.DAILY_QUOTA - 1)
        # Should not raise
        rl_mod.check_daily_quota()

    @patch.object(rl_mod, "redis_client")
    def test_raises_when_quota_exceeded(self, mock_redis: MagicMock) -> None:
        """Should raise RuntimeError when daily count exceeds limit."""
        mock_redis.incr.return_value = rl_mod.DAILY_QUOTA + 1
        with pytest.raises(RuntimeError, match="DAILY_QUOTA_EXCEEDED"):
            rl_mod.check_daily_quota()

    @patch.object(rl_mod, "redis_client")
    def test_sets_ttl_on_first_increment(self, mock_redis: MagicMock) -> None:
        """First increment of the day should set a TTL on the key."""
        mock_redis.incr.return_value = 1  # First call of the day
        rl_mod.check_daily_quota()
        mock_redis.expire.assert_called_once()

    @patch.object(rl_mod, "redis_client")
    def test_no_ttl_on_subsequent_increments(self, mock_redis: MagicMock) -> None:
        """Subsequent increments should not reset the TTL."""
        mock_redis.incr.return_value = 5  # Not the first call
        rl_mod.check_daily_quota()
        mock_redis.expire.assert_not_called()


class TestGetDailyUsage:
    """Tests for get_daily_usage() — monitoring helper."""

    @patch.object(rl_mod, "redis_client")
    def test_returns_usage_tuple(self, mock_redis: MagicMock) -> None:
        """Should return (current_count, daily_limit) tuple."""
        mock_redis.get.return_value = "42"
        count, limit = rl_mod.get_daily_usage()
        assert count == 42
        assert limit == rl_mod.settings.OPENAI_DAILY_QUOTA

    @patch.object(rl_mod, "redis_client")
    def test_returns_zero_when_no_key(self, mock_redis: MagicMock) -> None:
        """Should return 0 count when the daily key doesn't exist."""
        mock_redis.get.return_value = None
        count, limit = rl_mod.get_daily_usage()
        assert count == 0
