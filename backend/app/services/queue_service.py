"""
QueueService for managing campaign queue entries with retry logic and DLQ.

Handles:
- Queue entry creation and updates
- Retry logic with per-failure-reason delays
- DLQ routing for terminal failures
- Queue statistics and summaries
"""

from typing import List, Optional, Tuple, Dict
from datetime import datetime, timezone, timedelta
from beanie import PydanticObjectId
import logging

from backend.app.models.queue_entry import (
    QueueEntry,
    QueueState,
    FailureReason,
    RetryHistory
)
from backend.app.models.call_record import CallOutcome

logger = logging.getLogger(__name__)


# Retry delay mappings (in minutes)
RETRY_DELAYS = {
    FailureReason.NO_ANSWER: 30,
    FailureReason.BUSY: 60,
    FailureReason.FAILED: 15,
    FailureReason.PERSON_NOT_AVAILABLE: 120,
    FailureReason.SHORT_DURATION: 60,
    FailureReason.NETWORK_FAILURE: 15,
    FailureReason.TIMEOUT: 60,
}

# Non-retriable failure reasons (go to DLQ immediately)
NON_RETRIABLE_FAILURES = {
    FailureReason.INVALID_NUMBER,
    FailureReason.REJECTED,
}


class QueueService:
    """Service layer for queue entry operations"""

    @staticmethod
    async def create_queue_entry(
        campaign_id: str,
        patient_phone: str,
        language: str = "en"
    ) -> QueueEntry:
        """
        Create new queue entry for a patient in a campaign.

        Args:
            campaign_id: Campaign ID
            patient_phone: Patient phone number (E.164 format)
            language: Language preference

        Returns:
            Created QueueEntry
        """
        queue_entry = QueueEntry(
            campaign_id=campaign_id,
            patient_phone=patient_phone,
            language=language
        )
        await queue_entry.save()
        logger.info(f"Created queue entry {queue_entry.id} for campaign {campaign_id}")
        return queue_entry

    @staticmethod
    async def get_queue_entry_by_id(entry_id: str) -> Optional[QueueEntry]:
        """
        Get queue entry by ID.

        Args:
            entry_id: Queue entry ID

        Returns:
            QueueEntry or None if not found
        """
        return await QueueEntry.get(PydanticObjectId(entry_id))

    @staticmethod
    async def list_campaign_queue(
        campaign_id: str,
        skip: int = 0,
        limit: int = 50,
        state: Optional[QueueState] = None
    ) -> Tuple[List[QueueEntry], int]:
        """
        List queue entries for a campaign with filtering.

        Args:
            campaign_id: Campaign ID
            skip: Pagination offset
            limit: Max results
            state: Filter by queue state

        Returns:
            Tuple of (entries list, total count)
        """
        query = QueueEntry.find(QueueEntry.campaign_id == campaign_id)

        if state:
            query = query.find(QueueEntry.state == state)

        total = await query.count()
        entries = await query.sort("-created_at").skip(skip).limit(limit).to_list()

        return entries, total

    @staticmethod
    async def get_campaign_queue_summary(campaign_id: str) -> Dict:
        """
        Get queue summary statistics for a campaign.

        Args:
            campaign_id: Campaign ID

        Returns:
            Dict with queue counts by state
        """
        all_entries = await QueueEntry.find(
            QueueEntry.campaign_id == campaign_id
        ).to_list()

        summary = {
            "campaign_id": campaign_id,
            "total_entries": len(all_entries),
            "pending_count": sum(1 for e in all_entries if e.state == QueueState.PENDING),
            "calling_count": sum(1 for e in all_entries if e.state == QueueState.CALLING),
            "success_count": sum(1 for e in all_entries if e.state == QueueState.SUCCESS),
            "failed_count": sum(1 for e in all_entries if e.state == QueueState.FAILED),
            "retrying_count": sum(1 for e in all_entries if e.state == QueueState.RETRYING),
            "dlq_count": sum(1 for e in all_entries if e.moved_to_dlq),
        }

        return summary

    @staticmethod
    async def list_dlq_entries(
        skip: int = 0,
        limit: int = 50,
        campaign_id: Optional[str] = None
    ) -> Tuple[List[QueueEntry], int]:
        """
        List Dead Letter Queue entries.

        Args:
            skip: Pagination offset
            limit: Max results
            campaign_id: Filter by campaign (optional)

        Returns:
            Tuple of (DLQ entries, total count)
        """
        query = QueueEntry.find(QueueEntry.moved_to_dlq == True)

        if campaign_id:
            query = query.find(QueueEntry.campaign_id == campaign_id)

        total = await query.count()
        entries = await query.sort("-updated_at").skip(skip).limit(limit).to_list()

        return entries, total

    @staticmethod
    async def get_global_queue_stats() -> Dict:
        """
        Get global queue statistics across all campaigns.

        Returns:
            Dict with global queue metrics
        """
        all_entries = await QueueEntry.find().to_list()

        total_entries = len(all_entries)
        dlq_entries = [e for e in all_entries if e.moved_to_dlq]

        # Count active campaigns (campaigns with at least one non-terminal entry)
        active_campaign_ids = set()
        for entry in all_entries:
            if entry.state in [QueueState.PENDING, QueueState.CALLING, QueueState.RETRYING]:
                active_campaign_ids.add(entry.campaign_id)

        # Calculate average retry count
        avg_retry_count = (
            sum(e.retry_count for e in all_entries) / total_entries
            if total_entries > 0 else 0.0
        )

        # Calculate DLQ rate
        dlq_rate = (
            (len(dlq_entries) / total_entries * 100)
            if total_entries > 0 else 0.0
        )

        stats = {
            "total_campaigns_active": len(active_campaign_ids),
            "total_queue_entries": total_entries,
            "total_pending": sum(1 for e in all_entries if e.state == QueueState.PENDING),
            "total_calling": sum(1 for e in all_entries if e.state == QueueState.CALLING),
            "total_success": sum(1 for e in all_entries if e.state == QueueState.SUCCESS),
            "total_failed": sum(1 for e in all_entries if e.state == QueueState.FAILED),
            "total_retrying": sum(1 for e in all_entries if e.state == QueueState.RETRYING),
            "total_dlq": len(dlq_entries),
            "average_retry_count": round(avg_retry_count, 2),
            "dlq_rate_percent": round(dlq_rate, 2),
        }

        return stats

    @staticmethod
    def map_call_outcome_to_failure_reason(outcome: CallOutcome) -> Optional[FailureReason]:
        """
        Map CallOutcome to FailureReason for retry logic.

        Args:
            outcome: CallOutcome from CallRecord

        Returns:
            FailureReason or None if outcome is success
        """
        mapping = {
            CallOutcome.NO_ANSWER: FailureReason.NO_ANSWER,
            CallOutcome.BUSY: FailureReason.BUSY,
            CallOutcome.FAILED: FailureReason.FAILED,
            CallOutcome.INVALID_NUMBER: FailureReason.INVALID_NUMBER,
            CallOutcome.REJECTED: FailureReason.REJECTED,
            CallOutcome.WRONG_PERSON: FailureReason.PERSON_NOT_AVAILABLE,
            CallOutcome.TIMEOUT: FailureReason.TIMEOUT,
            CallOutcome.NETWORK_FAILURE: FailureReason.NETWORK_FAILURE,
        }

        return mapping.get(outcome)

    @staticmethod
    async def handle_call_failure(
        queue_entry: QueueEntry,
        failure_reason: FailureReason,
        error_details: Optional[str] = None
    ) -> QueueEntry:
        """
        Handle call failure with retry logic or DLQ routing.

        Logic:
        - If non-retriable → Move to DLQ immediately
        - If retry_count >= 3 → Move to DLQ
        - Otherwise → Schedule retry with appropriate delay

        Args:
            queue_entry: The queue entry that failed
            failure_reason: Reason for failure
            error_details: Additional error context

        Returns:
            Updated QueueEntry
        """
        # Record retry attempt
        queue_entry.retry_count += 1
        queue_entry.last_failure_reason = failure_reason
        queue_entry.retry_history.append(
            RetryHistory(
                attempt_number=queue_entry.retry_count,
                failure_reason=failure_reason,
                error_details=error_details
            )
        )

        # Set first_attempted_at if not already set
        if not queue_entry.first_attempted_at:
            queue_entry.first_attempted_at = datetime.now(timezone.utc)

        # Check if non-retriable failure
        if failure_reason in NON_RETRIABLE_FAILURES:
            queue_entry.state = QueueState.FAILED
            queue_entry.moved_to_dlq = True
            queue_entry.dlq_reason = f"Non-retriable failure: {failure_reason.value}"
            queue_entry.completed_at = datetime.now(timezone.utc)
            logger.warning(
                f"Queue entry {queue_entry.id} moved to DLQ: {queue_entry.dlq_reason}"
            )

        # Check if max retries exceeded
        elif queue_entry.retry_count >= 3:
            queue_entry.state = QueueState.FAILED
            queue_entry.moved_to_dlq = True
            queue_entry.dlq_reason = f"Max retry attempts (3) exceeded for {failure_reason.value}"
            queue_entry.completed_at = datetime.now(timezone.utc)
            logger.warning(
                f"Queue entry {queue_entry.id} moved to DLQ: {queue_entry.dlq_reason}"
            )

        # Schedule retry
        else:
            queue_entry.state = QueueState.RETRYING
            retry_delay_minutes = RETRY_DELAYS.get(failure_reason, 30)
            queue_entry.next_retry_at = datetime.now(timezone.utc) + timedelta(minutes=retry_delay_minutes)
            logger.info(
                f"Queue entry {queue_entry.id} scheduled for retry {queue_entry.retry_count}/3 "
                f"at {queue_entry.next_retry_at} (delay: {retry_delay_minutes}min)"
            )

        queue_entry.updated_at = datetime.now(timezone.utc)
        await queue_entry.save()

        return queue_entry

    @staticmethod
    async def handle_call_success(queue_entry: QueueEntry) -> QueueEntry:
        """
        Mark queue entry as successfully completed.

        Args:
            queue_entry: The queue entry that succeeded

        Returns:
            Updated QueueEntry
        """
        queue_entry.state = QueueState.SUCCESS
        queue_entry.completed_at = datetime.now(timezone.utc)
        queue_entry.updated_at = datetime.now(timezone.utc)

        if not queue_entry.first_attempted_at:
            queue_entry.first_attempted_at = datetime.now(timezone.utc)

        await queue_entry.save()

        logger.info(f"Queue entry {queue_entry.id} completed successfully")

        return queue_entry

    @staticmethod
    async def retry_dlq_entry(
        entry_id: str,
        reset_retry_count: bool = True
    ) -> QueueEntry:
        """
        Manually retry a DLQ entry (Admin action).

        Args:
            entry_id: Queue entry ID
            reset_retry_count: Whether to reset retry count to 0

        Returns:
            Updated QueueEntry

        Raises:
            ValueError: If entry not found or not in DLQ
        """
        entry = await QueueService.get_queue_entry_by_id(entry_id)

        if not entry:
            raise ValueError(f"Queue entry {entry_id} not found")

        if not entry.moved_to_dlq:
            raise ValueError(f"Queue entry {entry_id} is not in DLQ")

        # Reset DLQ flags
        entry.moved_to_dlq = False
        entry.dlq_reason = None
        entry.state = QueueState.PENDING
        entry.next_retry_at = None
        entry.completed_at = None

        # Optionally reset retry count
        if reset_retry_count:
            entry.retry_count = 0
            entry.retry_history = []
            entry.last_failure_reason = None

        entry.updated_at = datetime.now(timezone.utc)
        await entry.save()

        logger.info(f"DLQ entry {entry_id} manually retried (reset_count={reset_retry_count})")

        return entry

    @staticmethod
    async def delete_dlq_entry(entry_id: str) -> bool:
        """
        Permanently delete a DLQ entry (Admin action).

        Args:
            entry_id: Queue entry ID

        Returns:
            True if deleted successfully

        Raises:
            ValueError: If entry not found or not in DLQ
        """
        entry = await QueueService.get_queue_entry_by_id(entry_id)

        if not entry:
            raise ValueError(f"Queue entry {entry_id} not found")

        if not entry.moved_to_dlq:
            raise ValueError(f"Queue entry {entry_id} is not in DLQ")

        await entry.delete()

        logger.info(f"DLQ entry {entry_id} permanently deleted")

        return True

    @staticmethod
    async def get_ready_to_process_entries(
        campaign_id: str,
        max_concurrent: int = 10
    ) -> List[QueueEntry]:
        """
        Get queue entries ready for processing (for queue processor).

        Criteria:
        - State is PENDING or (RETRYING and next_retry_at <= now)
        - Not in DLQ
        - Limit by max_concurrent

        Args:
            campaign_id: Campaign ID
            max_concurrent: Maximum entries to return

        Returns:
            List of QueueEntry ready for processing
        """
        now = datetime.now(timezone.utc)

        # Get pending entries
        pending_entries = await QueueEntry.find(
            QueueEntry.campaign_id == campaign_id,
            QueueEntry.state == QueueState.PENDING,
            QueueEntry.moved_to_dlq == False
        ).limit(max_concurrent).to_list()

        # Get retrying entries that are ready
        retrying_entries = await QueueEntry.find(
            QueueEntry.campaign_id == campaign_id,
            QueueEntry.state == QueueState.RETRYING,
            QueueEntry.next_retry_at <= now,
            QueueEntry.moved_to_dlq == False
        ).limit(max_concurrent - len(pending_entries)).to_list()

        entries = pending_entries + retrying_entries

        return entries[:max_concurrent]
