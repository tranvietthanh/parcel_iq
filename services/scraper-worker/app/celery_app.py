"""Celery application factory.

Configures the Celery app with Redis as broker/backend and sets up task
routing so scrape tasks go to ``data_acquisition_queue`` and LLM tasks
go to ``llm_processing_queue``.
"""

from __future__ import annotations

from celery import Celery

from app.config import settings

celery_app = Celery("scraper_worker", broker=settings.REDIS_URL)

celery_app.conf.update(
    # Serialisation
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    # Routing
    task_routes={
        "scraper_worker.tasks.*": {"queue": "data_acquisition_queue"},
        "llm_parser_worker.tasks.*": {"queue": "llm_processing_queue"},
    },
    # Reliability
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    # Misc
    timezone="UTC",
    enable_utc=True,
)

# Auto-discover tasks in app.tasks module
celery_app.autodiscover_tasks(["app"])
