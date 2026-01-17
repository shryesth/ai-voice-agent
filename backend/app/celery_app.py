"""
Celery application configuration.

Configures Celery with Redis broker and beat schedule for
periodic tasks like queue processing.
"""

from celery import Celery
from celery.schedules import crontab

from backend.app.core.config import settings
from backend.app.core.logging import get_logger

logger = get_logger(__name__)

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

    # Beat schedule for periodic tasks
    beat_schedule={
        "process-campaign-queues": {
            "task": "backend.app.tasks.queue_processor.process_campaign_queues",
            "schedule": settings.queue_processor_interval,  # Every 30 seconds
            "options": {
                "expires": settings.queue_processor_interval - 5,  # Prevent overlap
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
