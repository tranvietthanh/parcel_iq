"""OZ Property Report LLM Parser Worker — Celery app factory."""

from celery import Celery
from celery.schedules import crontab

from app.config import settings

celery_app = Celery("parceliq_llm_parser")

celery_app.conf.update(
    broker_url=settings.REDIS_URL,
    result_backend=settings.REDIS_URL,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Australia/Sydney",
    task_routes={
        "app.tasks.parse_with_llm": {"queue": "llm_processing_queue"},
        "app.tasks.trigger_state_refresh": {"queue": "llm_processing_queue"},
        "app.tasks.check_dlq": {"queue": "llm_processing_queue"},
    },
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_default_retry_delay=65,  # Respects 1-min rate limit window + buffer
    task_max_retries=3,
)

# ── Celery Beat schedule ────────────────────────────────────────────────────
celery_app.conf.beat_schedule = {
    # Re-scrape all VIC properties once per month (2am on the 1st)
    "refresh-vic-monthly": {
        "task": "app.tasks.trigger_state_refresh",
        "schedule": crontab(minute=0, hour=2, day_of_month="1"),
        "kwargs": {"state": "VIC"},
    },
    # Re-scrape NSW properties on the 8th of each month
    "refresh-nsw-monthly": {
        "task": "app.tasks.trigger_state_refresh",
        "schedule": crontab(minute=0, hour=2, day_of_month="8"),
        "kwargs": {"state": "NSW"},
    },
    # Check dead-letter queue every 15 minutes
    "check-dlq-every-15m": {
        "task": "app.tasks.check_dlq",
        "schedule": crontab(minute="*/15"),
    },
}

# Auto-discover tasks in app.tasks module
celery_app.autodiscover_tasks(["app"])
