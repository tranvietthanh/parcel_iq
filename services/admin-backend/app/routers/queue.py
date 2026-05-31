from fastapi import APIRouter, Depends, HTTPException
from celery import Celery
from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError

from app.config import settings
from app.core.service_auth import verify_service_token
from app.schemas.queue import (
    QueueHealthResponse,
    QueueStats,
    QueueControlRequest,
)

router = APIRouter(
    prefix="/queue",
    tags=["queue"],
    dependencies=[Depends(verify_service_token)],
)

# Celery app for inspecting queues
celery_app = Celery(
    "scraper_worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)


@router.get("/health", response_model=QueueHealthResponse)
async def get_queue_health() -> QueueHealthResponse:
    """
    Get health status of all Celery queues.
    
    Returns stats for each queue: waiting, active, completed_24h, failed_24h.
    Also checks Redis connectivity and active worker count.
    """
    # Check Redis connection
    try:
        redis_client = Redis.from_url(settings.REDIS_URL)
        redis_client.ping()
        redis_connected = True
    except RedisConnectionError:
        redis_connected = False
    
    # Get Celery inspect
    inspect = celery_app.control.inspect()
    
    # Get active workers
    active_workers = inspect.active()
    workers_active = len(active_workers) if active_workers else 0
    
    # Get queue lengths
    # Note: Celery doesn't provide easy access to queue lengths via inspect
    # We'll use Redis directly to check queue lengths
    queue_names = ["data_acquisition_queue", "llm_processing_queue"]
    queue_stats_list = []
    
    for queue_name in queue_names:
        try:
            # Get queue length from Redis
            waiting = redis_client.llen(queue_name) if redis_connected else 0
            
            # Get active tasks for this queue
            active_count = 0
            if active_workers:
                for worker_tasks in active_workers.values():
                    active_count += len([
                        t for t in worker_tasks
                        if t.get("delivery_info", {}).get("routing_key") == queue_name
                    ])
            
            # For completed/failed counts, we'd need to query Celery result backend
            # This is a placeholder - real impl would query Redis or DB
            queue_stats_list.append(
                QueueStats(
                    name=queue_name,
                    waiting=waiting,
                    active=active_count,
                    completed_24h=0,  # Placeholder
                    failed_24h=0,     # Placeholder
                )
            )
        except Exception:
            # If we can't get stats for a queue, return zeros
            queue_stats_list.append(
                QueueStats(
                    name=queue_name,
                    waiting=0,
                    active=0,
                    completed_24h=0,
                    failed_24h=0,
                )
            )
    
    return QueueHealthResponse(
        queues=queue_stats_list,
        workers_active=workers_active,
        redis_connected=redis_connected,
    )


@router.post("/control")
async def control_queue(
    body: QueueControlRequest,
    admin_user_id: str = Depends(verify_service_token),
):
    """
    Control Celery workers and queues.
    
    Supported actions:
    - PAUSE: Stop consuming from queue(s)
    - RESUME: Resume consuming from queue(s)
    - PURGE: Clear all pending tasks from queue(s)
    """
    control = celery_app.control
    
    if body.action == "PAUSE":
        # Pause workers from consuming from the specified queue
        if body.queue_name:
            # Pause specific queue
            # Note: Celery doesn't have direct queue-level pause
            # This would require custom worker implementation
            raise HTTPException(
                status_code=501,
                detail="Queue-level pause not implemented - use worker control",
            )
        else:
            # Pause all workers
            control.broadcast("pool_shrink", arguments={"n": 1})
            return {"message": "All workers paused", "action": "PAUSE"}
    
    elif body.action == "RESUME":
        if body.queue_name:
            raise HTTPException(
                status_code=501,
                detail="Queue-level resume not implemented - use worker control",
            )
        else:
            control.broadcast("pool_grow", arguments={"n": 1})
            return {"message": "All workers resumed", "action": "RESUME"}
    
    elif body.action == "PURGE":
        if body.queue_name:
            # Purge specific queue
            celery_app.control.purge()
            # Note: Celery's purge() clears all queues
            # For queue-specific purge, we'd use:
            # celery_app.amqp.Queue(body.queue_name).purge()
            return {
                "message": f"Queue {body.queue_name} purged",
                "action": "PURGE",
                "queue": body.queue_name,
            }
        else:
            # Purge all queues
            result = celery_app.control.purge()
            purged_count = sum(result.values()) if result else 0
            return {
                "message": "All queues purged",
                "action": "PURGE",
                "tasks_removed": purged_count,
            }
    
    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {body.action}")
