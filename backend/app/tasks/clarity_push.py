"""
Celery task for pushing completed call results to Clarity.

This task runs separately from call execution to avoid race conditions.
It only processes recipients that are READY_TO_SYNC, meaning:
- Call is completed
- Metrics are saved to CallRecord and Recipient
- Recording is uploaded to S3
- Recording URL is saved to Recipient

After successful sync, recipient status transitions to terminal state.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId

from backend.app.celery_app import celery_app, get_worker_event_loop
from backend.app.models.enums import (
    RecipientStatus,
    SyncStatus,
    CallOutcome,
)

logger = logging.getLogger(__name__)


def _determine_terminal_status(recipient) -> RecipientStatus:
    """
    Determine the terminal status for a recipient based on call outcome.

    Args:
        recipient: Recipient document

    Returns:
        Terminal RecipientStatus (COMPLETED, FAILED, or NOT_REACHABLE)
    """
    # Check conversation result for successful outcome
    if recipient.conversation_result:
        # If we have any confirmation data, consider it completed
        if (
            recipient.conversation_result.is_visit_confirmed is not None
            or recipient.conversation_result.satisfaction_rating is not None
        ):
            return RecipientStatus.COMPLETED

    # Check call attempts for failure patterns
    if recipient.call_attempts:
        last_attempt = recipient.call_attempts[-1]
        if last_attempt.outcome in {
            CallOutcome.COMPLETED_FULL,
            CallOutcome.COMPLETED_PARTIAL,
        }:
            return RecipientStatus.COMPLETED

        # Check if max retries reached
        from backend.app.models.enums import NON_RETRIABLE_FAILURES
        if last_attempt.failure_reason in NON_RETRIABLE_FAILURES:
            return RecipientStatus.FAILED

    # Check retry count
    if recipient.retry_count >= 3:  # Default max retries
        return RecipientStatus.NOT_REACHABLE

    # Default to COMPLETED if we got this far (recording saved means call happened)
    return RecipientStatus.COMPLETED


@celery_app.task(
    name="tasks.push_ready_recipients_to_clarity",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=3,
)
def push_ready_recipients_to_clarity(
    self,
    geography_id: Optional[str] = None,
    max_count: int = 50,
):
    """
    Push recipients with READY_TO_SYNC status to Clarity.

    This task is the ONLY place where Clarity push happens, ensuring:
    - No race conditions with call execution
    - Recording URL is always available
    - Metrics are fully populated

    Flow:
    1. Find recipients with status=READY_TO_SYNC and sync_status=PENDING
    2. For each recipient:
       a. Verify recording_url exists (if required by geography)
       b. Push to Clarity API
       c. Set sync_status=SYNCED
       d. Transition to terminal status (COMPLETED/FAILED/NOT_REACHABLE)

    Args:
        geography_id: Optional filter by geography
        max_count: Maximum recipients to process per run

    Returns:
        Number of recipients successfully synced
    """

    async def _push():
        from backend.app.models.geography import Geography
        from backend.app.models.recipient import Recipient
        from backend.app.models.call_queue import CallQueue
        from backend.app.models.call_record import CallRecord
        from backend.app.services.clarity_service import ClarityService
        from backend.app.infrastructure.storage.s3_storage import S3StorageClient

        # Build query for ready-to-sync recipients
        query = {
            "status": RecipientStatus.READY_TO_SYNC.value,
            "sync_status": SyncStatus.PENDING.value,
            "external_source": "clarity",  # Only sync Clarity-sourced recipients
        }

        # Find recipients to sync
        recipients = await Recipient.find(query).limit(max_count).to_list()

        if not recipients:
            logger.debug("No recipients ready to sync to Clarity")
            return 0

        logger.info(f"Found {len(recipients)} recipients ready to sync to Clarity")

        # Group by geography for efficient service creation
        by_geography = {}
        for recipient in recipients:
            queue = await CallQueue.get(recipient.queue_id)
            if not queue:
                logger.warning(f"Queue not found for recipient {recipient.id}")
                continue

            geo_id = str(queue.geography_id)
            if geo_id not in by_geography:
                by_geography[geo_id] = []
            by_geography[geo_id].append(recipient)

        synced_count = 0
        storage_client = S3StorageClient()

        for geo_id, geo_recipients in by_geography.items():
            # Get geography and verify Clarity is configured
            geography = await Geography.get(ObjectId(geo_id))
            if not geography or not geography.clarity_config.enabled:
                logger.debug(f"Clarity not enabled for geography {geo_id}")
                continue

            if not geography.clarity_config.auto_push_results:
                logger.debug(f"Auto push not enabled for geography {geo_id}")
                continue

            clarity_service = ClarityService(geography.clarity_config)

            for recipient in geo_recipients:
                try:
                    # Get recording URL
                    recording_url = recipient.recording_url

                    # If recording URL is required but missing, try to generate it
                    if geography.clarity_config.include_recording_url and not recording_url:
                        if recipient.current_call_record_id:
                            call_record = await CallRecord.get(
                                ObjectId(recipient.current_call_record_id)
                            )
                            if call_record and call_record.recording and call_record.recording.s3_object_key:
                                try:
                                    recording_url = storage_client.get_presigned_url(
                                        call_record.recording.s3_object_key,
                                        expiration=86400,  # 24 hours
                                    )
                                    # Update recipient with recording URL for future use
                                    recipient.recording_url = recording_url
                                except Exception as url_error:
                                    logger.warning(
                                        f"Failed to generate recording URL for recipient {recipient.id}: {url_error}"
                                    )

                    # Log recipient details before push
                    logger.info(
                        f"Pushing recipient {recipient.id} to Clarity - "
                        f"External ID: {recipient.external_id}, "
                        f"Has Recording URL: {recording_url is not None}, "
                        f"Visit Confirmed: {recipient.conversation_result.is_visit_confirmed if recipient.conversation_result else None}"
                    )

                    # Push to Clarity
                    success = await clarity_service.push_verification_result(
                        recipient=recipient,
                        recording_url=recording_url,
                    )

                    if success:
                        # Update sync status
                        recipient.sync_status = SyncStatus.SYNCED
                        recipient.last_synced_at = datetime.now(timezone.utc)
                        recipient.sync_error = None

                        # Transition to terminal status
                        terminal_status = _determine_terminal_status(recipient)
                        recipient.status = terminal_status
                        recipient.completed_at = datetime.now(timezone.utc)
                        recipient.updated_at = datetime.now(timezone.utc)

                        await recipient.save()
                        synced_count += 1

                        logger.info(
                            f"Successfully synced recipient {recipient.id} to Clarity, "
                            f"terminal status: {terminal_status.value}"
                        )
                    else:
                        # Mark sync as failed but keep ready_to_sync status for retry
                        recipient.sync_status = SyncStatus.FAILED
                        recipient.sync_error = "Clarity API returned failure"
                        recipient.updated_at = datetime.now(timezone.utc)
                        await recipient.save()

                        logger.warning(f"Failed to sync recipient {recipient.id} to Clarity")

                except Exception as e:
                    logger.error(
                        f"Error pushing recipient {recipient.id} to Clarity: {e}",
                        exc_info=True
                    )

                    # Mark sync as failed
                    recipient.sync_status = SyncStatus.FAILED
                    recipient.sync_error = str(e)
                    recipient.updated_at = datetime.now(timezone.utc)
                    await recipient.save()

        logger.info(f"Synced {synced_count} recipients to Clarity")
        return synced_count

    # Run async function using worker's event loop
    loop = get_worker_event_loop()
    return loop.run_until_complete(_push())


@celery_app.task(
    name="tasks.retry_failed_clarity_sync",
    bind=True,
    max_retries=1,
)
def retry_failed_clarity_sync(self, recipient_id: str):
    """
    Retry Clarity sync for a specific recipient that failed.

    This can be called manually to retry a failed sync.

    Args:
        recipient_id: Recipient document ID to retry

    Returns:
        True if sync succeeded, False otherwise
    """

    async def _retry():
        from backend.app.models.recipient import Recipient

        recipient = await Recipient.get(ObjectId(recipient_id))
        if not recipient:
            logger.error(f"Recipient not found: {recipient_id}")
            return False

        # Reset sync status to pending for retry
        recipient.sync_status = SyncStatus.PENDING
        recipient.sync_error = None
        recipient.updated_at = datetime.now(timezone.utc)
        await recipient.save()

        logger.info(f"Reset recipient {recipient_id} for Clarity sync retry")
        return True

    loop = get_worker_event_loop()
    return loop.run_until_complete(_retry())
