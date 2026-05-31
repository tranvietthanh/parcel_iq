"""Celery app used by public-api for task dispatch."""

from __future__ import annotations

from celery import Celery

from app.config import settings


def make_celery() -> Celery:
    """Build the public-api Celery client."""
    app = Celery(
        "public-api",
        broker=settings.REDIS_URL,
        backend=settings.REDIS_URL,
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
