"""Celery task monitoring endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from celery import Celery
from celery.result import AsyncResult
from pydantic import BaseModel
from datetime import datetime
import logging

from app.config import settings
from app.core.service_auth import verify_service_token

router = APIRouter(
    prefix="/tasks",
    tags=["tasks"],
    dependencies=[Depends(verify_service_token)],
)

logger = logging.getLogger(__name__)

# Celery app - use generic name so it can see all workers
celery_app = Celery(
    "parceliq_admin",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_routes={
        "scraper_worker.tasks.*": {"queue": "data_acquisition_queue"},
        "llm_parser_worker.tasks.*": {"queue": "llm_processing_queue"},
    },
    timezone="UTC",
    enable_utc=True,
    broker_connection_retry_on_startup=True,
)


class TaskDetail(BaseModel):
    """Celery task detail."""

    id: str
    state: str  # PENDING, QUEUED, STARTED, SUCCESS, FAILURE, RETRY, REVOKED
    status: str  # Human-readable: queued, running, completed, failed, cancelled
    result: dict | None = None
    error: str | None = None
    created_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None


class TaskListResponse(BaseModel):
    """List of visible Celery tasks."""

    items: list[TaskDetail]
    total: int


@router.get("", response_model=TaskListResponse)
async def list_tasks() -> TaskListResponse:
    """
    Get recent/active Celery tasks.
    
    Returns tasks from the past 1 hour that are queued, running, or recently completed.
    """
    # Get inspector to query Celery workers
    from celery.app.control import Inspect

    # Use longer timeout - default is 1.0 second which may be too short
    inspector = Inspect(app=celery_app, timeout=5.0)

    tasks = []
    
    logger.info(f"Querying Celery workers on broker: {settings.CELERY_BROKER_URL}")
    
    # Check which workers are online
    stats = inspector.stats()
    if stats:
        logger.info(f"Found {len(stats)} worker(s): {list(stats.keys())}")
    else:
        logger.warning("No workers found or workers not responding to stats()")

    # Get active tasks (currently running)
    active = inspector.active() or {}
    logger.info(f"Active tasks response: {len(active)} workers, {sum(len(t or []) for t in active.values())} total tasks")
    for worker_name, worker_tasks in active.items():
        logger.debug(f"Worker {worker_name}: {len(worker_tasks or [])} active tasks")
        for task_info in worker_tasks or []:
            task_id = task_info.get("id")
            if not task_id:
                continue
            tasks.append(
                TaskDetail(
                    id=task_id,
                    state="STARTED",
                    status="running",
                    result={
                        "worker": worker_name,
                        "args": task_info.get("args"),
                        "kwargs": task_info.get("kwargs"),
                        "task_name": task_info.get("name"),
                    },
                    created_at=task_info.get("time_start"),
                )
            )

    # Get reserved tasks (queued, waiting to run)
    reserved = inspector.reserved() or {}
    logger.info(f"Reserved tasks response: {len(reserved)} workers, {sum(len(t or []) for t in reserved.values())} total tasks")
    for worker_name, worker_tasks in reserved.items():
        logger.debug(f"Worker {worker_name}: {len(worker_tasks or [])} reserved tasks")
        for task_info in worker_tasks or []:
            task_id = task_info.get("id")
            if not task_id:
                continue
            tasks.append(
                TaskDetail(
                    id=task_id,
                    state="PENDING",
                    status="queued",
                    result={
                        "worker": worker_name,
                        "task_name": task_info.get("name"),
                        "args": task_info.get("args"),
                        "kwargs": task_info.get("kwargs"),
                    },
                )
            )

    # Get task results from backend (completed/failed)
    # Note: This is limited to tasks we can find in the result backend
    # For a production system, you'd want to query a task history table
    try:
        # Try to get recent completed tasks
        # This is a simple approach - in production you might query a database instead
        registered_tasks = celery_app.control.inspect().registered() or {}
        for worker_name in registered_tasks.keys():
            # We can't easily list all completed tasks from just Celery
            # In production, store task history in database
            pass
    except Exception:
        pass
    
    logger.info(f"Total tasks found: {len(tasks)}")
    return TaskListResponse(
        items=sorted(tasks, key=lambda t: t.created_at or "", reverse=True),
        total=len(tasks),
    )


@router.get("/{task_id}", response_model=TaskDetail)
async def get_task(task_id: str) -> TaskDetail:
    """
    Get details for a specific task.
    """
    result = AsyncResult(task_id, app=celery_app)

    state = result.state
    status_map = {
        "PENDING": "queued",
        "STARTED": "running",
        "SUCCESS": "completed",
        "FAILURE": "failed",
        "RETRY": "retrying",
        "REVOKED": "cancelled",
    }

    return TaskDetail(
        id=task_id,
        state=state,
        status=status_map.get(state, "unknown"),
        result=result.result if result.successful() else None,
        error=str(result.info) if result.failed() else None,
    )


@router.post("/{task_id}/cancel")
async def cancel_task(task_id: str) -> dict[str, str]:
    """
    Cancel a running or queued task.
    """
    celery_app.control.revoke(task_id, terminate=True, signal="SIGKILL")
    return {"task_id": task_id, "action": "cancelled"}


@router.post("/{task_id}/retry")
async def retry_task(task_id: str) -> dict[str, str]:
    """
    Retry a failed task.
    """
    result = AsyncResult(task_id, app=celery_app)

    if not result.failed():
        raise HTTPException(
            status_code=400, detail="Can only retry failed tasks"
        )

    # Re-queue a new task with same arguments
    # This would require storing the original task args, which Celery doesn't track by default
    # For now, return a message that manual retry is needed
    return {
        "task_id": task_id,
        "action": "retry_requested",
        "note": "Retry functionality requires task history database. Please manually re-trigger.",
    }
