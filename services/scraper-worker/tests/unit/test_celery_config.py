"""Tests for the Celery app configuration."""

from __future__ import annotations

from app.celery_app import celery_app


class TestCeleryConfig:
    """Tests for Celery app configuration."""

    def test_task_serializer_is_json(self):
        assert celery_app.conf.task_serializer == "json"

    def test_accepts_json_only(self):
        assert "json" in celery_app.conf.accept_content

    def test_acks_late_is_true(self):
        assert celery_app.conf.task_acks_late is True

    def test_reject_on_worker_lost_is_true(self):
        assert celery_app.conf.task_reject_on_worker_lost is True

    def test_prefetch_multiplier_is_one(self):
        assert celery_app.conf.worker_prefetch_multiplier == 1

    def test_task_routes_configured(self):
        routes = celery_app.conf.task_routes
        assert "scraper_worker.tasks.*" in routes
        assert routes["scraper_worker.tasks.*"]["queue"] == "data_acquisition_queue"
