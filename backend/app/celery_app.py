"""
Celery application configuration.

Configures Celery with Redis broker and beat schedule for
periodic tasks like queue processing.
"""

import asyncio
from celery import Celery
from celery.schedules import crontab
from celery.signals import worker_process_init

from backend.app.core.config import settings
from backend.app.core.logging import get_logger

logger = get_logger(__name__)

# Global event loop for Celery worker - MUST be reused for all async operations
# to avoid "Cannot use AsyncMongoClient in different event loop" errors
_worker_event_loop = None


def get_worker_event_loop():
    """
    Get the worker's event loop that was created during initialization.
    This MUST be used for all async operations to ensure MongoDB client compatibility.
    """
    global _worker_event_loop
    if _worker_event_loop is None or _worker_event_loop.is_closed():
        # Create new loop if needed (shouldn't happen after worker init)
        _worker_event_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_worker_event_loop)
        logger.warning("Created new event loop - this may cause issues if DB was initialized on different loop")
    return _worker_event_loop


# Create Celery app
celery_app = Celery(
    "patient_feedback_api",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

# Celery configuration
celery_app.conf.update(
    # Task settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,

    # Task execution
    task_track_started=True,
    task_time_limit=settings.max_call_duration_seconds + 60,  # Call duration + buffer
    task_soft_time_limit=settings.max_call_duration_seconds,

    # Worker settings
    worker_prefetch_multiplier=1,  # One task at a time for voice calls
    worker_max_tasks_per_child=100,  # Restart worker after 100 tasks
    worker_concurrency=settings.celery_worker_concurrency,

    # Result backend settings
    result_expires=3600,  # Results expire after 1 hour
    result_extended=True,

    # Retry settings
    task_acks_late=True,  # Acknowledge after task completion
    task_reject_on_worker_lost=True,
    broker_connection_retry_on_startup=True,  # Retry broker connection on startup

    # Beat schedule for periodic tasks
    beat_schedule={
        "process-campaign-queues": {
            "task": "process_campaign_queues",
            "schedule": 30.0,  # Every 30 seconds
            "options": {
                "expires": 25,  # Prevent overlap (30 - 5)
            },
        },
    },
)

# Auto-discover tasks from task modules
# Tasks will be registered in Phase 5, 6, 7
celery_app.autodiscover_tasks([
    "backend.app.tasks",
])

logger.info(
    "Celery app configured",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    concurrency=settings.celery_worker_concurrency,
)


@worker_process_init.connect
def init_worker(**kwargs):
    """Initialize event loop and Beanie when Celery worker starts."""
    global _worker_event_loop
    
    # 1. Create and store the event loop globally
    _worker_event_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_worker_event_loop)
    logger.info("Event loop created and stored for Celery worker")

    # 2. Initialize Beanie with models
    from backend.app.core.database import db
    from backend.app.models.user import User
    from backend.app.models.geography import Geography
    from backend.app.models.campaign import Campaign
    from backend.app.models.call_record import CallRecord
    from backend.app.models.queue_entry import QueueEntry

    _worker_event_loop.run_until_complete(db.connect(
        document_models=[User, Geography, Campaign, CallRecord, QueueEntry]
    ))

    logger.info("Celery worker initialized with event loop and Beanie models")
