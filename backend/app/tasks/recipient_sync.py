"""
Celery task for syncing call results from CallRecord to Recipient.

This task runs after a voice call completes to transfer conversation data
from CallRecord to Recipient. It does NOT trigger Clarity sync - that happens
separately via the clarity_push task after recording is uploaded.

Flow:
1. Call completes -> sync_recipient_from_call runs
2. Maps conversation data from CallRecord to Recipient
3. Handles retry logic (RETRYING status) or marks as awaiting recording
4. Recording upload completes -> recording_download sets READY_TO_SYNC
5. Clarity push task picks up READY_TO_SYNC recipients
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
)
from backend.app.models.call_record import ConversationData
from backend.app.models.enums import FailureReason
from backend.app.services.recipient_service import recipient_service

logger = logging.getLogger(__name__)


def _map_outcome_to_failure_reason(outcome: Optional[CallOutcome]) -> Optional[FailureReason]:
    """
    Map CallOutcome to FailureReason for retry logic.

    Args:
        outcome: The call outcome from CallRecord

    Returns:
        FailureReason if outcome represents a failure, None for successful outcomes
    """
    if outcome is None:
        return None

    mapping = {
        # Connection issues
        CallOutcome.NO_ANSWER: FailureReason.NO_ANSWER,
        CallOutcome.BUSY: FailureReason.BUSY,
        CallOutcome.INVALID_NUMBER: FailureReason.INVALID_NUMBER,
        CallOutcome.REJECTED: FailureReason.REJECTED,
        CallOutcome.TIMEOUT: FailureReason.TIMEOUT,
        CallOutcome.SHORT_DURATION: FailureReason.SHORT_DURATION,
        CallOutcome.NETWORK_FAILURE: FailureReason.FAILED,  # Network issues treated as generic failure

        # Needs follow-up
        CallOutcome.VOICEMAIL: FailureReason.VOICEMAIL,
        CallOutcome.REQUEST_HUMAN_CALLBACK: FailureReason.REQUEST_HUMAN_CALLBACK,
        CallOutcome.WRONG_PERSON: FailureReason.WRONG_PERSON,
        CallOutcome.NEEDS_VERIFICATION: FailureReason.NEEDS_VERIFICATION,

        # Technical
        CallOutcome.TECHNICAL_ERROR: FailureReason.FAILED,

        # Successful outcomes return None (no failure reason)
        # COMPLETED_FULL, COMPLETED_PARTIAL not in mapping -> returns None
    }

    return mapping.get(outcome)


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
    2. Handle retry logic for failed calls
    3. Copy transcript to Recipient for reference
    4. Set sync_status = PENDING (ready for Clarity push when recording arrives)

    NOTE: This task does NOT:
    - Set terminal status (COMPLETED/FAILED) - that happens after Clarity sync
    - Trigger Clarity sync - that happens via separate clarity_push task
    - Generate recording URL - that happens in recording_download task

    The flow is:
    1. Call ends -> this task syncs data
    2. Recording uploads -> recording_download sets READY_TO_SYNC
    3. Clarity push task picks up READY_TO_SYNC recipients

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

        # 3. Map conversation results - direct copy since both use ConversationData now
        conversation_result = call_record.conversation_data.model_copy(deep=True)

        # Log conversation data fields for debugging null values
        logger.info(
            f"CallRecord {call_record_id} conversation_data: "
            f"is_visit_confirmed={call_record.conversation_data.is_visit_confirmed}, "
            f"is_service_confirmed={call_record.conversation_data.is_service_confirmed}, "
            f"satisfaction_rating={call_record.conversation_data.satisfaction_rating}, "
            f"has_side_effects={call_record.conversation_data.has_side_effects}"
        )

        # Merge additional context into extracted_data
        conversation_result.extracted_data.update({
            "urgency_flagged": call_record.urgency_flagged,
            "completed_stages": call_record.conversation_state.completed_stages if call_record.conversation_state else [],
            "current_stage": call_record.conversation_state.current_stage if call_record.conversation_state else None,
        })

        # 4. Get call outcome and handle retry logic
        outcome = call_record.call_tracking.outcome if call_record.call_tracking else None
        failure_reason = _map_outcome_to_failure_reason(outcome)
        duration_seconds = call_record.call_tracking.duration_seconds if call_record.call_tracking else None
        error_details = getattr(call_record.call_tracking, 'error_message', None) if call_record.call_tracking else None

        # Call handle_call_completion to manage retries
        # This will set status to RETRYING if retry is needed, or keep as CALLING
        # NOTE: We override terminal statuses below to use READY_TO_SYNC instead
        recipient = await recipient_service.handle_call_completion(
            recipient_id=str(recipient.id),
            call_record_id=call_record_id,
            outcome=outcome,
            failure_reason=failure_reason,
            duration_seconds=duration_seconds,
            conversation_result=conversation_result.model_dump() if conversation_result else None,
            error_details=error_details,
        )

        # 5. Override terminal statuses - don't go to terminal until Clarity sync
        # If call was successful (COMPLETED) or max retries reached (NOT_REACHABLE/FAILED),
        # we need to wait for recording before syncing to Clarity
        if recipient.status in {
            RecipientStatus.COMPLETED,
            RecipientStatus.FAILED,
            RecipientStatus.NOT_REACHABLE,
        }:
            # Check if recording is already available
            if call_record.recording and call_record.recording.s3_object_key:
                # Recording already uploaded, set READY_TO_SYNC
                recipient.status = RecipientStatus.READY_TO_SYNC
                logger.info(f"Recording available, setting recipient {recipient.id} to READY_TO_SYNC")
            else:
                # Recording not yet uploaded, keep intermediate status
                # recording_download will set READY_TO_SYNC when done
                # Use a marker status to indicate waiting for recording
                # For now, keep the status but the recording_download will update it
                logger.info(
                    f"Recording not yet uploaded for recipient {recipient.id}, "
                    f"status={recipient.status.value}. Will be updated by recording_download."
                )

        # 6. Update additional Recipient fields
        recipient.sync_status = SyncStatus.PENDING  # Ready for Clarity sync when READY_TO_SYNC
        recipient.urgency_flagged = call_record.urgency_flagged
        recipient.updated_at = datetime.now(timezone.utc)

        # Copy transcript reference for quick access
        if call_record.transcript:
            # Store transcript length for reference
            conversation_result.extracted_data["transcript_turn_count"] = len(call_record.transcript)

        await recipient.save()

        logger.info(
            f"Synced Recipient {recipient.id} from CallRecord {call_record_id}: "
            f"status={recipient.status.value}, "
            f"is_visit_confirmed={conversation_result.is_visit_confirmed}, "
            f"satisfaction_rating={conversation_result.satisfaction_rating}"
        )

        # NOTE: We do NOT trigger Clarity sync here anymore
        # The clarity_push task will pick up READY_TO_SYNC recipients on its schedule
        # This prevents race conditions with recording upload

        return True

    # Run async function using worker's event loop
    loop = get_worker_event_loop()
    return loop.run_until_complete(_sync())
