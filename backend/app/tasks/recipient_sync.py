"""
Celery task for syncing call results from CallRecord to Recipient.

This task runs after a voice call completes to transfer conversation data
from CallRecord to Recipient, enabling bidirectional Clarity sync.
"""

import asyncio
import logging
from typing import Optional
from datetime import datetime, timezone

from bson import ObjectId

from backend.app.celery_app import celery_app, get_worker_event_loop
from backend.app.models.call_record import CallRecord, CallOutcome
from backend.app.models.recipient import (
    Recipient,
    RecipientStatus,
    SyncStatus,
    ConversationResult,
)
from backend.app.models.enums import FailureReason
from backend.app.services.recipient_service import recipient_service

logger = logging.getLogger(__name__)


@celery_app.task(
    name="tasks.sync_recipient_from_call",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=3,
)
def sync_recipient_from_call(
    self,
    call_record_id: str,
):
    """
    Transfer call results from CallRecord to Recipient.

    This task runs after a voice call completes to:
    1. Map conversation data from CallRecord to Recipient.conversation_result
    2. Set Recipient status to terminal state (COMPLETED/FAILED/NOT_REACHABLE)
    3. Populate Recipient.recording_url with presigned S3 URL
    4. Set Recipient.sync_status = PENDING (ready for Clarity push)

    Args:
        call_record_id: CallRecord document ID

    Returns:
        True if sync successful, False otherwise
    """

    async def _sync():
        # 1. Get CallRecord
        call_record = await CallRecord.get(ObjectId(call_record_id))
        if not call_record:
            logger.warning(f"CallRecord {call_record_id} not found")
            return False

        if not call_record.recipient_id:
            logger.debug(f"CallRecord {call_record_id} has no recipient_id - skipping sync")
            return False

        # 2. Get Recipient
        recipient = await Recipient.get(ObjectId(call_record.recipient_id))
        if not recipient:
            logger.warning(f"Recipient not found for CallRecord {call_record_id}")
            return False

        # 3. Map conversation results
        conversation_result = ConversationResult(
            is_visit_confirmed=call_record.conversation_data.is_visit_confirmed,
            is_service_confirmed=call_record.conversation_data.is_service_confirmed,
            satisfaction_rating=call_record.conversation_data.overall_satisfaction,
            side_effects_reported=call_record.conversation_data.side_effects_reported,
            has_side_effects=call_record.conversation_data.has_side_effects,
            specific_concerns=call_record.conversation_data.specific_concerns,
            additional_notes=None,
            extracted_data={
                "urgency_flagged": call_record.urgency_flagged,
                "completed_stages": call_record.conversation_state.completed_stages if call_record.conversation_state else [],
                "current_stage": call_record.conversation_state.current_stage if call_record.conversation_state else None,
                **call_record.conversation_data.extracted_data  # Include all extracted data from conversation
            }
        )

        # 4. Get presigned recording URL (if recording exists)
        recording_url = None
        if call_record.recording and call_record.recording.s3_object_key:
            try:
                from backend.app.infrastructure.storage.s3_storage import S3Storage
                storage = S3Storage()
                recording_url = await storage.get_presigned_url(
                    call_record.recording.s3_object_key,
                    expiration=86400,  # 24 hours
                )
            except Exception as e:
                logger.warning(f"Failed to get presigned URL for recording: {e}")
                # Continue without recording URL

        # 5. Handle call completion and determine next status via retry logic
        outcome = call_record.call_tracking.outcome if call_record.call_tracking else None
        
        # Map outcome to failure_reason
        failure_reason = None
        if outcome == CallOutcome.NO_ANSWER:
            failure_reason = FailureReason.NO_ANSWER
        elif outcome == CallOutcome.BUSY:
            failure_reason = FailureReason.BUSY
        elif outcome == CallOutcome.TECHNICAL_ERROR:
            failure_reason = FailureReason.FAILED
        # For successful outcomes or unknown, failure_reason remains None
        
        # Get additional call details
        duration_seconds = call_record.call_tracking.duration_seconds if call_record.call_tracking else None
        error_details = getattr(call_record.call_tracking, 'error_message', None) if call_record.call_tracking else None
        
        # Call handle_call_completion to manage retries and status
        recipient = await recipient_service.handle_call_completion(
            recipient_id=str(recipient.id),
            call_record_id=call_record_id,
            outcome=outcome,
            failure_reason=failure_reason,
            duration_seconds=duration_seconds,
            conversation_result=conversation_result.model_dump() if conversation_result else None,
            error_details=error_details,
        )

        # 6. Update additional Recipient fields
        recipient.recording_url = recording_url
        recipient.sync_status = SyncStatus.PENDING  # Ready for Clarity sync
        recipient.completed_at = call_record.call_tracking.ended_at if call_record.call_tracking else None
        recipient.urgency_flagged = call_record.urgency_flagged
        recipient.updated_at = datetime.now(timezone.utc)

        await recipient.save()

        logger.info(
            f"Synced Recipient {recipient.id} from CallRecord {call_record_id}: "
            f"status={recipient.status.value}, has_conversation_data={bool(conversation_result.is_visit_confirmed)}, "
            f"has_recording={bool(recording_url)}"
        )

        # 7. Optionally trigger immediate Clarity sync
        # (if queue has auto_push_results enabled)
        try:
            from backend.app.models.call_queue import CallQueue
            from backend.app.models.geography import Geography

            queue = await CallQueue.get(recipient.queue_id)
            geography = await Geography.get(queue.geography_id) if queue else None

            if geography and geography.clarity_config and geography.clarity_config.auto_push_results:
                logger.info(f"Auto-triggering Clarity sync for geography {geography.id}")
                from backend.app.tasks.clarity_sync import sync_results_to_clarity
                sync_results_to_clarity.delay(str(geography.id))
        except Exception as e:
            logger.warning(f"Failed to trigger auto Clarity sync: {e}")
            # Not critical - sync will happen on next scheduled run

        return True

    # Run async function using worker's event loop
    loop = get_worker_event_loop()
    return loop.run_until_complete(_sync())
