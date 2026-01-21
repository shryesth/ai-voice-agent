"""
Celery task for syncing call results from CallRecord to Recipient.

This task runs after a voice call completes to transfer conversation data
from CallRecord to Recipient, enabling bidirectional Clarity sync.
"""

import asyncio
import logging
from typing import Optional
from datetime import datetime

from bson import ObjectId

from backend.app.celery_app import celery_app
from backend.app.models.call_record import CallRecord, CallOutcome
from backend.app.models.recipient import (
    Recipient,
    RecipientStatus,
    SyncStatus,
    ConversationResult,
)
from backend.app.models.enums import FailureReason

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
            is_visit_confirmed=call_record.feedback.visit_confirmed if call_record.feedback else None,
            is_service_confirmed=call_record.feedback.service_confirmed if call_record.feedback else None,
            satisfaction_rating=call_record.feedback.satisfaction_rating if call_record.feedback else None,
            side_effects_reported=call_record.feedback.side_effects_details if call_record.feedback else None,
            has_side_effects=call_record.feedback.has_side_effects if call_record.feedback else None,
            specific_concerns=call_record.feedback.specific_concerns if call_record.feedback else None,
            additional_notes=None,
            extracted_data={
                "urgency_flagged": call_record.urgency_flagged,
                "completed_stages": call_record.pipeline_state.get("completed_stages", []) if call_record.pipeline_state else [],
                "completion_reason": call_record.pipeline_state.get("completion_reason") if call_record.pipeline_state else None,
            }
        )

        # 4. Determine terminal status based on call outcome
        if call_record.outcome == CallOutcome.COMPLETED:
            new_status = RecipientStatus.COMPLETED
        elif call_record.outcome == CallOutcome.FAILED:
            new_status = RecipientStatus.FAILED
        elif call_record.outcome in (CallOutcome.NO_ANSWER, CallOutcome.BUSY):
            new_status = RecipientStatus.NOT_REACHABLE
        else:
            # Default to FAILED for unknown outcomes
            new_status = RecipientStatus.FAILED

        # 5. Get presigned recording URL (if recording exists)
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

        # 6. Update Recipient
        recipient.conversation_result = conversation_result
        recipient.recording_url = recording_url
        recipient.status = new_status
        recipient.sync_status = SyncStatus.PENDING  # Ready for Clarity sync
        recipient.completed_at = call_record.ended_at
        recipient.urgency_flagged = call_record.urgency_flagged

        await recipient.save()

        logger.info(
            f"Synced Recipient {recipient.id} from CallRecord {call_record_id}: "
            f"status={new_status}, has_conversation_data={bool(conversation_result.is_visit_confirmed)}, "
            f"has_recording={bool(recording_url)}"
        )

        # 7. Optionally trigger immediate Clarity sync
        # (if queue has auto_push_results enabled)
        try:
            queue = await recipient.queue_id.fetch()
            geography = await queue.geography_id.fetch()

            if geography.clarity_config and geography.clarity_config.auto_push_results:
                logger.info(f"Auto-triggering Clarity sync for geography {geography.id}")
                from backend.app.tasks.clarity_sync import sync_results_to_clarity
                sync_results_to_clarity.delay(str(geography.id))
        except Exception as e:
            logger.warning(f"Failed to trigger auto Clarity sync: {e}")
            # Not critical - sync will happen on next scheduled run

        return True

    # Run async function
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_sync())
    finally:
        loop.close()
