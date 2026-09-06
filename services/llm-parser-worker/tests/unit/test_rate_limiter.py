"""Unit tests for the Redis token-bucket rate limiter.

Uses mocked Redis to test token acquisition logic, bounded wait timeout,
read-only daily quota checks, and quota increment behaviour without a running Redis server.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import redis as redis_lib

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
        mock_pipe.get.side_effect = [str(rl_mod.settings.LLM_MAX_RPM), "1000.0"]

        # No WatchError — transaction succeeds
        mock_pipe.watch = MagicMock()
        mock_pipe.multi = MagicMock()
        mock_pipe.set = MagicMock()
        mock_pipe.execute = MagicMock(return_value=[True, True])

        with patch("app.services.rate_limiter.time") as mock_time:
            mock_time.time.return_value = 1000.0
            mock_time.monotonic.return_value = 100.0
            rl_mod.wait_for_token()

        # Should have called set for token count and last_refill
        assert mock_pipe.set.call_count == 2
        set_keys = [call[0][0] for call in mock_pipe.set.call_args_list]
        assert rl_mod.TOKEN_KEY in set_keys
        assert rl_mod.LAST_REFILL_KEY in set_keys

    @patch.object(rl_mod, "redis_client")
    @patch("app.services.rate_limiter.time")
    def test_waits_when_no_tokens(self, mock_time: MagicMock, mock_redis: MagicMock) -> None:
        """Should sleep and retry when no tokens are available."""
        mock_time.time.return_value = 1000.0
        mock_time.monotonic.side_effect = [100.0, 100.1, 101.0, 102.0, 103.0]

        call_count = 0

        def pipe_get_side_effect(key: str) -> str:
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                # First iteration: 0 tokens, refill time = now (no refill)
                if key == rl_mod.TOKEN_KEY:
                    return "0"
                return "1000.0"
            # Second iteration: tokens available after sleep
            if key == rl_mod.TOKEN_KEY:
                return str(rl_mod.settings.LLM_MAX_RPM)
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

    @patch.object(rl_mod, "redis_client")
    @patch("app.services.rate_limiter.time")
    def test_raises_when_wait_exceeds_max_seconds(
        self, mock_time: MagicMock, mock_redis: MagicMock
    ) -> None:
        """Should raise RuntimeError with RATE_LIMIT prefix when max_wait_seconds exceeded."""
        mock_time.time.return_value = 1000.0
        # Start at monotonic 100.0; inside loop it exceeds deadline (100 + 10 = 110)
        mock_time.monotonic.side_effect = [100.0, 111.0]

        with pytest.raises(RuntimeError, match="RATE_LIMIT: token wait exceeded max_wait_seconds"):
            rl_mod.wait_for_token(max_wait_seconds=10)


class TestDailyQuota:
    """Tests for is_daily_quota_exhausted() and record_llm_request()."""

    @patch.object(rl_mod, "redis_client")
    def test_is_daily_quota_exhausted_false_when_under_limit(self, mock_redis: MagicMock) -> None:
        """Should return False and never call incr when below limit."""
        mock_redis.get.return_value = str(rl_mod.settings.LLM_DAILY_QUOTA - 1)

        result = rl_mod.is_daily_quota_exhausted()

        assert result is False
        mock_redis.incr.assert_not_called()

    @patch.object(rl_mod, "redis_client")
    def test_is_daily_quota_exhausted_false_when_no_key(self, mock_redis: MagicMock) -> None:
        """Should return False when key does not exist."""
        mock_redis.get.return_value = None

        result = rl_mod.is_daily_quota_exhausted()

        assert result is False
        mock_redis.incr.assert_not_called()

    @patch.object(rl_mod, "redis_client")
    def test_is_daily_quota_exhausted_true_when_at_limit(self, mock_redis: MagicMock) -> None:
        """Should return True when count reaches daily limit."""
        mock_redis.get.return_value = str(rl_mod.settings.LLM_DAILY_QUOTA)

        result = rl_mod.is_daily_quota_exhausted()

        assert result is True
        mock_redis.incr.assert_not_called()

    @patch.object(rl_mod, "redis_client")
    def test_is_daily_quota_exhausted_true_when_exceeded(self, mock_redis: MagicMock) -> None:
        """Should return True when count exceeds daily limit."""
        mock_redis.get.return_value = str(rl_mod.settings.LLM_DAILY_QUOTA + 10)

        result = rl_mod.is_daily_quota_exhausted()

        assert result is True
        mock_redis.incr.assert_not_called()

    @patch.object(rl_mod, "redis_client")
    def test_is_daily_quota_exhausted_handles_redis_error(self, mock_redis: MagicMock) -> None:
        """Should return False if Redis raises an error, allowing processing."""
        mock_redis.get.side_effect = redis_lib.RedisError("Connection refused")

        result = rl_mod.is_daily_quota_exhausted()

        assert result is False

    @patch.object(rl_mod, "redis_client")
    def test_record_llm_request_increments_and_sets_ttl(self, mock_redis: MagicMock) -> None:
        """First increment of the day should set 86400s TTL."""
        mock_redis.incr.return_value = 1

        rl_mod.record_llm_request()

        mock_redis.incr.assert_called_once()
        mock_redis.expire.assert_called_once_with(mock_redis.incr.call_args[0][0], 86_400)

    @patch.object(rl_mod, "redis_client")
    def test_record_llm_request_no_ttl_on_subsequent_calls(self, mock_redis: MagicMock) -> None:
        """Subsequent increments should not re-set TTL."""
        mock_redis.incr.return_value = 2

        rl_mod.record_llm_request()

        mock_redis.incr.assert_called_once()
        mock_redis.expire.assert_not_called()

    @patch.object(rl_mod, "redis_client")
    def test_record_llm_request_handles_redis_error(self, mock_redis: MagicMock) -> None:
        """Should catch RedisError without raising."""
        mock_redis.incr.side_effect = redis_lib.RedisError("Connection refused")

        # Must not raise
        rl_mod.record_llm_request()


class TestGetDailyUsage:
    """Tests for get_daily_usage() — monitoring helper."""

    @patch.object(rl_mod, "redis_client")
    def test_returns_usage_tuple(self, mock_redis: MagicMock) -> None:
        """Should return (current_count, daily_limit) tuple."""
        mock_redis.get.return_value = "42"
        count, limit = rl_mod.get_daily_usage()
        assert count == 42
        assert limit == rl_mod.settings.LLM_DAILY_QUOTA

    @patch.object(rl_mod, "redis_client")
    def test_returns_zero_when_no_key(self, mock_redis: MagicMock) -> None:
        """Should return 0 count when the daily key doesn't exist."""
        mock_redis.get.return_value = None
        count, limit = rl_mod.get_daily_usage()
        assert count == 0
        assert limit == rl_mod.settings.LLM_DAILY_QUOTA

    @patch.object(rl_mod, "redis_client")
    def test_returns_zero_on_redis_error(self, mock_redis: MagicMock) -> None:
        """Should return 0 count when Redis raises an error."""
        mock_redis.get.side_effect = redis_lib.RedisError("Connection error")
        count, limit = rl_mod.get_daily_usage()
        assert count == 0
        assert limit == rl_mod.settings.LLM_DAILY_QUOTA


class TestRedisKeys:
    """Tests verifying provider-neutral Redis key names."""

    def test_keys_are_provider_neutral(self) -> None:
        assert rl_mod.TOKEN_KEY == "llm:rate_limit:tokens"
        assert rl_mod.LAST_REFILL_KEY == "llm:rate_limit:last_refill"
        assert rl_mod.DAILY_COUNT_KEY_PREFIX == "llm:daily_count:"
