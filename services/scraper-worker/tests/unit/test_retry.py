"""Tests for retry_with_backoff utility."""

from __future__ import annotations

import pytest

from app.utils.retry import retry_with_backoff


class TestRetryWithBackoff:
    """Tests for the retry decorator."""

    def test_succeeds_first_attempt(self):
        call_count = 0

        def succeed():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = retry_with_backoff(succeed, retries=3, delay=0.01)
        assert result == "ok"
        assert call_count == 1

    def test_succeeds_on_second_attempt(self):
        call_count = 0

        def fail_then_succeed():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("fail")
            return "ok"

        result = retry_with_backoff(fail_then_succeed, retries=3, delay=0.01)
        assert result == "ok"
        assert call_count == 2

    def test_exhausts_retries(self):
        call_count = 0

        def always_fail():
            nonlocal call_count
            call_count += 1
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            retry_with_backoff(always_fail, retries=2, delay=0.01)

        assert call_count == 3  # 1 initial + 2 retries
