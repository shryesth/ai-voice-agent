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

# Queue names for task routing
QUEUE_CALLS = "calls"  # Call execution - initiate, handle, recording
QUEUE_NEXUS = "nexus"  # Nexus sync - pull subjects, push results
QUEUE_POSTPROCESSING = "postprocessing"  # Translation, analytics

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

    # Queue configuration - separate queues for different concerns
    task_queues={
        QUEUE_CALLS: {"exchange": QUEUE_CALLS, "routing_key": QUEUE_CALLS},
        QUEUE_NEXUS: {"exchange": QUEUE_NEXUS, "routing_key": QUEUE_NEXUS},
        QUEUE_POSTPROCESSING: {"exchange": QUEUE_POSTPROCESSING, "routing_key": QUEUE_POSTPROCESSING},
    },
    task_default_queue=QUEUE_CALLS,

    # Task routing - send tasks to appropriate queues
    task_routes={
        # Call execution tasks -> calls queue
        "initiate_patient_call": {"queue": QUEUE_CALLS},
        "update_call_from_webhook": {"queue": QUEUE_CALLS},
        "download_twilio_recording": {"queue": QUEUE_CALLS},
        "retry_recording_from_fallback": {"queue": QUEUE_CALLS},
        "process_campaign_queues": {"queue": QUEUE_CALLS},
        "tasks.sync_recipient_from_call": {"queue": QUEUE_CALLS},
        # Nexus sync tasks -> nexus queue (separate from call execution)
        "tasks.sync_nexus_subjects": {"queue": QUEUE_NEXUS},
        "tasks.sync_all_queues_from_nexus": {"queue": QUEUE_NEXUS},
        "tasks.push_ready_recipients_to_nexus": {"queue": QUEUE_NEXUS},
        # Post-processing tasks -> postprocessing queue
        "translate_transcript": {"queue": QUEUE_POSTPROCESSING},
    },

    # Beat schedule for periodic tasks
    beat_schedule={
        "process-campaign-queues": {
            "task": "process_campaign_queues",
            "schedule": 30.0,  # Every 30 seconds
            "options": {
                "expires": 25,  # Prevent overlap (30 - 5)
                "queue": QUEUE_CALLS,
            },
        },
        "sync-nexus-queues": {
            "task": "tasks.sync_all_queues_from_nexus",
            "schedule": 60.0,  # Every 60 seconds
            "options": {
                "expires": 55,  # Prevent overlap
                "queue": QUEUE_NEXUS,
            },
        },
        "push-nexus-results": {
            "task": "tasks.push_ready_recipients_to_nexus",
            "schedule": 45.0,  # Every 45 seconds - check for ready_to_sync recipients
            "options": {
                "expires": 40,  # Prevent overlap
                "queue": QUEUE_NEXUS,
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
    from backend.app.models.call_record import CallRecord
    from backend.app.models.call_queue import CallQueue
    from backend.app.models.recipient import Recipient
    from backend.app.models.recording_dlq import RecordingDLQ

    _worker_event_loop.run_until_complete(db.connect(
        document_models=[User, Geography, CallRecord, CallQueue, Recipient, RecordingDLQ]
    ))

    logger.info("Celery worker initialized with event loop and Beanie models")
