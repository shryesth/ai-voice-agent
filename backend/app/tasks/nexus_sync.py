"""
Celery tasks for Nexus API synchronization - PULL operations only.

Tasks:
- sync_nexus_subjects: Pull verification subjects from Nexus (FOREVER mode queues)
- sync_all_queues_from_nexus: Scheduled task to sync all queues

NOTE: Push operations (syncing results TO Nexus) are handled by nexus_push.py
to avoid race conditions with recording uploads.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId

from backend.app.celery_app import celery_app, get_worker_event_loop
from backend.app.models.enums import (
    QueueState,
    QueueMode,
)

logger = logging.getLogger(__name__)


@celery_app.task(
    name="tasks.sync_nexus_subjects",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=3,
)
def sync_nexus_subjects(
    self,
    queue_id: str,
    max_count: Optional[int] = None,
):
    """
    Pull verification subjects from Nexus and create Recipients.

    This task is scheduled to run periodically for FOREVER mode queues
    that have Nexus sync enabled.

    Args:
        queue_id: CallQueue document ID
        max_count: Optional override for max subjects to pull
    """
    import asyncio

    async def _sync():
        from backend.app.models.call_queue import CallQueue
        from backend.app.models.geography import Geography
        from backend.app.services.nexus_service import NexusService

        # Get queue
        queue = await CallQueue.get(ObjectId(queue_id))
        if not queue:
            logger.warning(f"Queue not found: {queue_id}")
            return 0

        # Check if queue is active and has Nexus sync enabled
        if queue.state != QueueState.ACTIVE:
            logger.debug(f"Queue {queue_id} is not active, skipping sync")
            return 0

        if not queue.nexus_sync.enabled:
            logger.debug(f"Queue {queue_id} does not have Nexus sync enabled")
            return 0

        # Get geography and verify Nexus is configured
        geography = await Geography.get(queue.geography_id)
        if not geography or not geography.nexus_config.enabled:
            logger.warning(f"Nexus not configured for geography of queue {queue_id}")
            return 0

        # Create Nexus service
        nexus_service = NexusService(geography.nexus_config)

        # Pull subjects
        pull_count = max_count or queue.nexus_sync.max_per_sync
        try:
            recipients = await nexus_service.pull_verification_subjects(
                queue=queue,
                max_count=pull_count,
                event_type_filter=queue.nexus_sync.event_type_filter,
            )

            # Update sync metadata
            queue.nexus_sync.last_sync_at = datetime.now(timezone.utc)
            queue.nexus_sync.last_sync_count = len(recipients)
            queue.updated_at = datetime.now(timezone.utc)
            await queue.save()

            logger.info(
                f"Pulled {len(recipients)} subjects from Nexus for queue {queue_id}"
            )
            return len(recipients)

        except Exception as e:
            logger.error(f"Failed to pull from Nexus for queue {queue_id}: {e}")
            raise

    # Run async function using worker's event loop
    loop = get_worker_event_loop()
    return loop.run_until_complete(_sync())


# NOTE: sync_results_to_nexus has been REMOVED
# Push operations are now handled by nexus_push.py -> push_ready_recipients_to_nexus
# This prevents race conditions with recording uploads


@celery_app.task(
    name="tasks.sync_all_queues_from_nexus",
    bind=True,
)
def sync_all_queues_from_nexus(self):
    """
    Scheduled task to sync all FOREVER mode queues from Nexus.

    This task should be scheduled via Celery Beat to run periodically
    (e.g., every 5 minutes).
    """
    import asyncio

    async def _sync_all():
        from backend.app.models.call_queue import CallQueue

        # Find all active FOREVER mode queues with Nexus sync enabled
        queues = await CallQueue.find(
            CallQueue.state == QueueState.ACTIVE,
            CallQueue.mode == QueueMode.FOREVER,
            CallQueue.nexus_sync.enabled == True,
            CallQueue.deleted_at == None,
        ).to_list()

        logger.info(f"Found {len(queues)} queues to sync from Nexus")

        for queue in queues:
            # Check if it's time to sync based on interval
            if queue.nexus_sync.last_sync_at:
                from datetime import timedelta
                # Ensure last_sync_at is timezone-aware for comparison
                last_sync = queue.nexus_sync.last_sync_at
                if last_sync.tzinfo is None:
                    last_sync = last_sync.replace(tzinfo=timezone.utc)
                next_sync = last_sync + timedelta(
                    minutes=queue.nexus_sync.sync_interval_minutes
                )
                if datetime.now(timezone.utc) < next_sync:
                    continue

            # Queue the sync task
            sync_nexus_subjects.delay(str(queue.id))

        return len(queues)

    # Run async function using worker's event loop
    loop = get_worker_event_loop()
    return loop.run_until_complete(_sync_all())
