"""Unit tests for Celery app configuration.

Validates task routes, Beat schedule, and worker settings match
the spec requirements.
"""

from __future__ import annotations


class TestCeleryConfig:
    """Test Celery app factory settings."""

    def test_app_imports(self) -> None:
        """Celery app should import without errors."""
        from app.celery_app import celery_app

        assert celery_app is not None
        assert celery_app.main == "parceliq_llm_parser"

    def test_task_routes(self) -> None:
        """All tasks should route to llm_processing_queue."""
        from app.celery_app import celery_app

        routes = celery_app.conf.task_routes
        assert routes["app.tasks.parse_with_llm"]["queue"] == "llm_processing_queue"
        assert routes["app.tasks.check_dlq"]["queue"] == "llm_processing_queue"



    def test_beat_schedule_has_dlq_check(self) -> None:
        """DLQ check should run every 15 minutes."""
        from app.celery_app import celery_app

        schedule = celery_app.conf.beat_schedule
        entry = schedule["check-dlq-every-15m"]
        assert entry["task"] == "app.tasks.check_dlq"

    def test_acks_late_enabled(self) -> None:
        """Worker should ack late for at-least-once delivery."""
        from app.celery_app import celery_app

        assert celery_app.conf.task_acks_late is True

    def test_prefetch_multiplier_is_one(self) -> None:
        """Prefetch should be 1 to avoid grabbing too many LLM tasks."""
        from app.celery_app import celery_app

        assert celery_app.conf.worker_prefetch_multiplier == 1

    def test_retry_delay_is_65(self) -> None:
        """Default retry delay should be 65s (rate limit window + buffer)."""
        from app.celery_app import celery_app

        assert celery_app.conf.task_default_retry_delay == 65

    def test_timezone_is_sydney(self) -> None:
        """Beat schedule timezone should be Australia/Sydney."""
        from app.celery_app import celery_app

        assert celery_app.conf.timezone == "Australia/Sydney"
