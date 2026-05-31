from typing import Literal
from pydantic import BaseModel


class QueueStats(BaseModel):
    """Statistics for a single Celery queue."""

    name: str
    waiting: int
    active: int
    completed_24h: int
    failed_24h: int


class QueueHealthResponse(BaseModel):
    """Overall queue health status."""

    queues: list[QueueStats]
    workers_active: int
    redis_connected: bool


class QueueControlRequest(BaseModel):
    """Request to control queue workers."""

    action: Literal["PAUSE", "RESUME", "PURGE"]
    queue_name: str | None = None  # None = all queues
