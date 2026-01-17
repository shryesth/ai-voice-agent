"""
Retry handler Celery task.

Handles call completion and determines retry logic based on call outcome.
Calls are automatically retried with delays based on failure reason, or moved to DLQ.
"""

from celery import Task
from backend.app.celery_app import celery_app
from backend.app.models.call_record import CallOutcome
from backend.app.services.queue_service import QueueService
from backend.app.models.queue_entry import FailureReason
import logging
import asyncio

logger = logging.getLogger(__name__)


class RetryHandlerTask(Task):
    """Base task for retry handling with error handling"""

    autoretry_for = (Exception,)
    retry_backoff = True
    retry_backoff_max = 600  # 10 minutes
    retry_jitter = True
    max_retries = 3


@celery_app.task(base=RetryHandlerTask, bind=True, name="handle_call_completion")
def handle_call_completion(
    self,
    queue_entry_id: str,
    call_record_id: str,
    call_outcome: str,
    error_details: str = None
):
    """
    Handle call completion and update queue entry with retry logic.

    Called after a call completes (success or failure).
    Determines if call should be retried, and if so, calculates retry delay.
    If max retries exceeded or non-retriable failure, moves to DLQ.

    Args:
        queue_entry_id: QueueEntry ID
        call_record_id: CallRecord ID
        call_outcome: CallOutcome value (string)
        error_details: Additional error context

    Returns:
        Dict with queue entry status and next action
    """
    logger.info(
        f"Handling call completion for queue entry {queue_entry_id}: {call_outcome}"
    )

    try:
        loop = asyncio.get_event_loop()

        # Get queue entry
        queue_entry = loop.run_until_complete(
            QueueService.get_queue_entry_by_id(queue_entry_id)
        )

        if not queue_entry:
            logger.error(f"Queue entry {queue_entry_id} not found")
            raise ValueError(f"Queue entry {queue_entry_id} not found")

        # Update call_record_id if not already set
        if not queue_entry.call_record_id:
            queue_entry.call_record_id = call_record_id
            loop.run_until_complete(queue_entry.save())

        # Convert string outcome to CallOutcome enum
        try:
            outcome = CallOutcome(call_outcome)
        except ValueError:
            logger.error(f"Invalid call outcome: {call_outcome}")
            outcome = CallOutcome.FAILED

        # Handle success
        if outcome in [CallOutcome.SUCCESS, CallOutcome.PARTIAL_SUCCESS]:
            queue_entry = loop.run_until_complete(
                QueueService.handle_call_success(queue_entry)
            )
            logger.info(f"Queue entry {queue_entry_id} marked as successful")
            return {
                "queue_entry_id": queue_entry_id,
                "status": "success",
                "next_action": "none"
            }

        # Handle failure - map outcome to failure reason
        failure_reason = QueueService.map_call_outcome_to_failure_reason(outcome)

        if not failure_reason:
            # Unknown outcome, treat as generic failure
            failure_reason = FailureReason.FAILED
            logger.warning(
                f"Unknown call outcome {call_outcome}, treating as FAILED"
            )

        # Handle call failure with retry logic
        queue_entry = loop.run_until_complete(
            QueueService.handle_call_failure(
                queue_entry=queue_entry,
                failure_reason=failure_reason,
                error_details=error_details
            )
        )

        # Determine next action
        if queue_entry.moved_to_dlq:
            next_action = "moved_to_dlq"
            logger.warning(
                f"Queue entry {queue_entry_id} moved to DLQ: {queue_entry.dlq_reason}"
            )
        else:
            next_action = f"retry_scheduled_at_{queue_entry.next_retry_at}"
            logger.info(
                f"Queue entry {queue_entry_id} scheduled for retry "
                f"{queue_entry.retry_count}/3 at {queue_entry.next_retry_at}"
            )

        return {
            "queue_entry_id": queue_entry_id,
            "status": "failure",
            "failure_reason": failure_reason.value,
            "retry_count": queue_entry.retry_count,
            "next_action": next_action,
            "next_retry_at": (
                queue_entry.next_retry_at.isoformat()
                if queue_entry.next_retry_at else None
            )
        }

    except Exception as e:
        logger.error(
            f"Failed to handle call completion for entry {queue_entry_id}: {e}",
            exc_info=True
        )
        raise


@celery_app.task(name="update_queue_from_call")
def update_queue_from_call(call_record_id: str):
    """
    Update queue entry based on call record outcome.

    This is called from the voice pipeline after a call completes.

    Args:
        call_record_id: CallRecord ID

    Returns:
        Dict with queue entry status
    """
    logger.info(f"Updating queue entry from call record {call_record_id}")

    try:
        loop = asyncio.get_event_loop()

        # Find call record
        from backend.app.services.call_service import CallService
        from beanie import PydanticObjectId

        call_record = loop.run_until_complete(
            CallService.get_call_by_id(call_record_id)
        )

        if not call_record:
            logger.error(f"Call record {call_record_id} not found")
            return {"status": "error", "message": "Call record not found"}

        # Find queue entry by call_record_id
        from backend.app.models.queue_entry import QueueEntry

        queue_entry = loop.run_until_complete(
            QueueEntry.find_one(QueueEntry.call_record_id == call_record_id)
        )

        if not queue_entry:
            logger.warning(
                f"No queue entry found for call record {call_record_id}. "
                f"This might be a test call."
            )
            return {"status": "no_queue_entry", "message": "Test call or manual call"}

        # Delegate to handle_call_completion
        outcome = call_record.call_tracking.outcome
        if outcome:
            result = handle_call_completion.delay(
                queue_entry_id=str(queue_entry.id),
                call_record_id=call_record_id,
                call_outcome=outcome.value,
                error_details=call_record.error_message
            )
            return {
                "status": "queued",
                "task_id": result.id,
                "queue_entry_id": str(queue_entry.id)
            }
        else:
            logger.warning(
                f"Call record {call_record_id} has no outcome yet, skipping queue update"
            )
            return {"status": "no_outcome", "message": "Call outcome not set"}

    except Exception as e:
        logger.error(
            f"Failed to update queue from call {call_record_id}: {e}",
            exc_info=True
        )
        raise
