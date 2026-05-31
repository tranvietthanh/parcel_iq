"""Celery app used by admin-backend for task dispatch."""

from __future__ import annotations

from celery import Celery

from app.config import settings


def make_celery() -> Celery:
    """Build the admin-backend Celery client."""
    app = Celery(
        "admin-backend",
        broker=settings.CELERY_BROKER_URL,
        backend=settings.CELERY_RESULT_BACKEND,
    )
    app.conf.update(
        task_routes={
            "scraper_worker.tasks.*": {"queue": "data_acquisition_queue"},
            "llm_parser_worker.tasks.*": {"queue": "llm_processing_queue"},
        },
        task_track_started=True,
        task_acks_late=True,
        worker_prefetch_multiplier=1,
    )
    return app


celery_app = make_celery()
