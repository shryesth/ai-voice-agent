"""
Celery tasks for Clarity API synchronization.

Tasks:
- sync_clarity_subjects: Pull verification subjects from Clarity (FOREVER mode queues)
- sync_results_to_clarity: Push completed call results to Clarity
"""

import logging
from datetime import datetime
from typing import Optional

from celery import shared_task
from bson import ObjectId

from backend.app.celery_app import celery_app, get_worker_event_loop
from backend.app.models.enums import (
    QueueState,
    QueueMode,
    RecipientStatus,
    SyncStatus,
)

logger = logging.getLogger(__name__)


@celery_app.task(
    name="tasks.sync_clarity_subjects",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=3,
)
def sync_clarity_subjects(
    self,
    queue_id: str,
    max_count: Optional[int] = None,
):
    """
    Pull verification subjects from Clarity and create Recipients.

    This task is scheduled to run periodically for FOREVER mode queues
    that have Clarity sync enabled.

    Args:
        queue_id: CallQueue document ID
        max_count: Optional override for max subjects to pull
    """
    import asyncio

    async def _sync():
        from backend.app.models.call_queue import CallQueue
        from backend.app.models.geography import Geography
        from backend.app.services.clarity_service import ClarityService

        # Get queue
        queue = await CallQueue.get(ObjectId(queue_id))
        if not queue:
            logger.warning(f"Queue not found: {queue_id}")
            return 0

        # Check if queue is active and has Clarity sync enabled
        if queue.state != QueueState.ACTIVE:
            logger.debug(f"Queue {queue_id} is not active, skipping sync")
            return 0

        if not queue.clarity_sync.enabled:
            logger.debug(f"Queue {queue_id} does not have Clarity sync enabled")
            return 0

        # Get geography and verify Clarity is configured
        geography = await Geography.get(queue.geography_id.id)
        if not geography or not geography.clarity_config.enabled:
            logger.warning(f"Clarity not configured for geography of queue {queue_id}")
            return 0

        # Create Clarity service
        clarity_service = ClarityService(geography.clarity_config)

        # Pull subjects
        pull_count = max_count or queue.clarity_sync.max_per_sync
        try:
            recipients = await clarity_service.pull_verification_subjects(
                queue=queue,
                max_count=pull_count,
                event_type_filter=queue.clarity_sync.event_type_filter,
            )

            # Update sync metadata
            queue.clarity_sync.last_sync_at = datetime.utcnow()
            queue.clarity_sync.last_sync_count = len(recipients)
            queue.updated_at = datetime.utcnow()
            await queue.save()

            logger.info(
                f"Pulled {len(recipients)} subjects from Clarity for queue {queue_id}"
            )
            return len(recipients)

        except Exception as e:
            logger.error(f"Failed to pull from Clarity for queue {queue_id}: {e}")
            raise

    # Run async function using worker's event loop
    loop = get_worker_event_loop()
    return loop.run_until_complete(_sync())


@celery_app.task(
    name="tasks.sync_results_to_clarity",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=3,
)
def sync_results_to_clarity(
    self,
    geography_id: Optional[str] = None,
    max_count: int = 100,
):
    """
    Push completed call results to Clarity.

    This task finds Recipients with terminal status that haven't been
    synced to Clarity yet and pushes their results.

    Args:
        geography_id: Optional filter by geography
        max_count: Maximum recipients to push per run
    """
    import asyncio

    async def _sync():
        from backend.app.models.geography import Geography
        from backend.app.models.recipient import Recipient
        from backend.app.services.clarity_service import ClarityService
        from backend.app.infrastructure.storage.s3_storage import S3StorageClient
        from backend.app.models.call_record import CallRecord
        from backend.app.core.config import get_settings

        settings = get_settings()

        # Build query for unsyncedrecipients
        query = {
            "status": {"$in": [
                RecipientStatus.COMPLETED.value,
                RecipientStatus.FAILED.value,
                RecipientStatus.NOT_REACHABLE.value,
            ]},
            "sync_status": SyncStatus.PENDING.value,
            "external_source": "clarity",
        }

        # Find recipients to sync
        recipients = await Recipient.find(query).limit(max_count).to_list()

        if not recipients:
            logger.debug("No recipients to sync to Clarity")
            return 0

        # Group by geography for efficient service creation
        by_geography = {}
        for recipient in recipients:
            # Get queue to find geography
            from backend.app.models.call_queue import CallQueue
            queue = await CallQueue.get(recipient.queue_id.id)
            if not queue:
                continue

            geo_id = str(queue.geography_id.id)
            if geo_id not in by_geography:
                by_geography[geo_id] = []
            by_geography[geo_id].append(recipient)

        synced_count = 0

        for geo_id, geo_recipients in by_geography.items():
            # Get geography and create Clarity service
            geography = await Geography.get(ObjectId(geo_id))
            if not geography or not geography.clarity_config.enabled:
                continue

            if not geography.clarity_config.auto_push_results:
                continue

            clarity_service = ClarityService(geography.clarity_config)

            # Initialize storage client for recording URLs
            storage_client = S3StorageClient()

            for recipient in geo_recipients:
                try:
                    # Get recording URL if available
                    recording_url = None
                    if geography.clarity_config.include_recording_url and recipient.current_call_record_id:
                        call_record = await CallRecord.get(ObjectId(recipient.current_call_record_id))
                        if call_record and call_record.recording and call_record.recording.s3_object_key:
                            recording_url = storage_client.get_presigned_url(
                                call_record.recording.s3_object_key,
                                expiration=86400,  # 24 hours
                            )

                    # Push to Clarity
                    success = await clarity_service.push_verification_result(
                        recipient=recipient,
                        recording_url=recording_url,
                    )

                    if success:
                        synced_count += 1

                except Exception as e:
                    logger.error(f"Failed to push recipient {recipient.id} to Clarity: {e}")
                    recipient.sync_status = SyncStatus.FAILED
                    recipient.sync_error = str(e)
                    await recipient.save()

        logger.info(f"Synced {synced_count} recipients to Clarity")
        return synced_count

    # Run async function using worker's event loop
    loop = get_worker_event_loop()
    return loop.run_until_complete(_sync())


@celery_app.task(
    name="tasks.sync_all_queues_from_clarity",
    bind=True,
)
def sync_all_queues_from_clarity(self):
    """
    Scheduled task to sync all FOREVER mode queues from Clarity.

    This task should be scheduled via Celery Beat to run periodically
    (e.g., every 5 minutes).
    """
    import asyncio

    async def _sync_all():
        from backend.app.models.call_queue import CallQueue

        # Find all active FOREVER mode queues with Clarity sync enabled
        queues = await CallQueue.find(
            CallQueue.state == QueueState.ACTIVE,
            CallQueue.mode == QueueMode.FOREVER,
            CallQueue.clarity_sync.enabled == True,
            CallQueue.deleted_at == None,
        ).to_list()

        logger.info(f"Found {len(queues)} queues to sync from Clarity")

        for queue in queues:
            # Check if it's time to sync based on interval
            if queue.clarity_sync.last_sync_at:
                from datetime import timedelta
                next_sync = queue.clarity_sync.last_sync_at + timedelta(
                    minutes=queue.clarity_sync.sync_interval_minutes
                )
                if datetime.utcnow() < next_sync:
                    continue

            # Queue the sync task
            sync_clarity_subjects.delay(str(queue.id))

        return len(queues)

    # Run async function using worker's event loop
    loop = get_worker_event_loop()
    return loop.run_until_complete(_sync_all())
