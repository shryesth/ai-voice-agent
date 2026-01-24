"""
Queue Scheduler Service

Manages queue scheduling, time window validation, and retry logic.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple

from backend.app.models.queue_models import (
    QueueConfig,
    CallEntry,
    QueueState,
    CallEntryStatus,
    FailureReason,
)
from backend.app.infrastructure.database.queue_repository import (
    QueueRepository,
    CallEntryRepository,
    get_queue_repository,
    get_call_entry_repository,
)

logger = logging.getLogger(__name__)


class QueueScheduler:
    """Queue scheduler service for time windows and retry management"""

    def __init__(
        self,
        queue_repo: Optional[QueueRepository] = None,
        call_entry_repo: Optional[CallEntryRepository] = None
    ):
        """Initialize queue scheduler"""
        self.queue_repo = queue_repo or get_queue_repository()
        self.call_entry_repo = call_entry_repo or get_call_entry_repository()

    def is_within_time_window(self, queue: QueueConfig, check_time: Optional[datetime] = None) -> bool:
        """
        Check if current time is within queue's time window

        Args:
            queue: Queue configuration
            check_time: Time to check (defaults to now)

        Returns:
            True if within time window, False otherwise
        """
        if not queue.time_window:
            return True  # No time window = always active

        check_time = check_time or datetime.utcnow()

        # Check day of week (0=Monday, 6=Sunday)
        if check_time.weekday() not in queue.time_window.days_of_week:
            logger.debug(f"Queue {queue.queue_id} not active on {check_time.strftime('%A')}")
            return False

        # Parse time window
        start_hour, start_min = map(int, queue.time_window.start_time_utc.split(":"))
        end_hour, end_min = map(int, queue.time_window.end_time_utc.split(":"))

        current_time = check_time.time()
        start_time = datetime.strptime(f"{start_hour:02d}:{start_min:02d}", "%H:%M").time()
        end_time = datetime.strptime(f"{end_hour:02d}:{end_min:02d}", "%H:%M").time()

        # Handle time window that crosses midnight
        if start_time <= end_time:
            # Normal case: 09:00 - 17:00
            within_window = start_time <= current_time <= end_time
        else:
            # Crosses midnight: 22:00 - 02:00
            within_window = current_time >= start_time or current_time <= end_time

        if not within_window:
            logger.debug(
                f"Queue {queue.queue_id} not within time window "
                f"({queue.time_window.start_time_utc} - {queue.time_window.end_time_utc})"
            )

        return within_window

    def get_next_window_start(self, queue: QueueConfig) -> Optional[datetime]:
        """
        Get the next time the queue's time window will open

        Args:
            queue: Queue configuration

        Returns:
            Next window start time, or None if no time window
        """
        if not queue.time_window:
            return None

        now = datetime.utcnow()
        start_hour, start_min = map(int, queue.time_window.start_time_utc.split(":"))

        # Try today first
        today_start = now.replace(hour=start_hour, minute=start_min, second=0, microsecond=0)
        if today_start > now and now.weekday() in queue.time_window.days_of_week:
            return today_start

        # Try next 7 days
        for days_ahead in range(1, 8):
            check_date = now + timedelta(days=days_ahead)
            if check_date.weekday() in queue.time_window.days_of_week:
                return check_date.replace(hour=start_hour, minute=start_min, second=0, microsecond=0)

        return None

    async def should_queue_be_active(self, queue_id: str) -> Tuple[bool, str]:
        """
        Determine if queue should be active based on time window and pending calls

        Args:
            queue_id: Queue identifier

        Returns:
            Tuple of (should_be_active, reason)
        """
        queue = await self.queue_repo.get_queue(queue_id)
        if not queue:
            return False, "Queue not found"

        # Check if queue is completed or cancelled
        if queue.state in [QueueState.COMPLETED, QueueState.CANCELLED]:
            return False, f"Queue is {queue.state.value}"

        # Check time window
        if not self.is_within_time_window(queue):
            next_start = self.get_next_window_start(queue)
            reason = f"Outside time window. Next start: {next_start.isoformat() if next_start else 'N/A'}"
            return False, reason

        # Check if there are any pending calls
        stats = await self.call_entry_repo.get_queue_statistics(queue_id, queue.name)
        if stats and stats.pending_calls == 0 and stats.retry_scheduled_calls == 0 and stats.calling_now == 0:
            return False, "No pending calls"

        return True, "Queue should be active"

    async def auto_pause_if_needed(self, queue_id: str) -> bool:
        """
        Auto-pause queue if outside time window

        Args:
            queue_id: Queue identifier

        Returns:
            True if queue was paused, False otherwise
        """
        should_be_active, reason = await self.should_queue_be_active(queue_id)

        if not should_be_active:
            queue = await self.queue_repo.get_queue(queue_id)
            if queue and queue.state == QueueState.ACTIVE:
                success = await self.queue_repo.update_queue_state(queue_id, QueueState.PAUSED)
                if success:
                    logger.info(f"Auto-paused queue {queue_id}: {reason}")
                return success

        return False

    async def auto_resume_if_needed(self, queue_id: str) -> bool:
        """
        Auto-resume queue if within time window

        Args:
            queue_id: Queue identifier

        Returns:
            True if queue was resumed, False otherwise
        """
        should_be_active, reason = await self.should_queue_be_active(queue_id)

        if should_be_active:
            queue = await self.queue_repo.get_queue(queue_id)
            if queue and queue.state == QueueState.PAUSED:
                success = await self.queue_repo.update_queue_state(queue_id, QueueState.ACTIVE)
                if success:
                    logger.info(f"Auto-resumed queue {queue_id}")
                return success

        return False

    def should_retry(
        self,
        queue: QueueConfig,
        entry: CallEntry,
        failure_reason: FailureReason
    ) -> bool:
        """
        Determine if a failed call should be retried

        Args:
            queue: Queue configuration
            entry: Call entry
            failure_reason: Reason for failure

        Returns:
            True if should retry, False otherwise
        """
        return queue.retry_strategy.should_retry(failure_reason, entry.retry_count)

    def calculate_retry_time(
        self,
        queue: QueueConfig,
        entry: CallEntry,
        failure_reason: FailureReason
    ) -> datetime:
        """
        Calculate when to retry a failed call

        Args:
            queue: Queue configuration
            entry: Call entry
            failure_reason: Reason for failure

        Returns:
            Datetime when to retry
        """
        delay_seconds = queue.retry_strategy.get_delay_for_reason(
            reason=failure_reason,
            retry_count=entry.retry_count
        )

        retry_time = datetime.utcnow() + timedelta(seconds=delay_seconds)

        # If time window is configured, ensure retry time is within window
        if queue.time_window:
            if not self.is_within_time_window(queue, retry_time):
                next_start = self.get_next_window_start(queue)
                if next_start:
                    retry_time = next_start
                    logger.info(
                        f"Adjusted retry time for {entry.entry_id} to next window start: "
                        f"{retry_time.isoformat()}"
                    )

        return retry_time

    async def handle_call_failure(
        self,
        entry_id: str,
        failure_reason: FailureReason,
        failure_details: Optional[str] = None,
        call_duration: Optional[int] = None
    ) -> bool:
        """
        Handle call failure - either schedule retry or move to DLQ

        Args:
            entry_id: Entry identifier
            failure_reason: Reason for failure
            failure_details: Optional failure details
            call_duration: Optional call duration in seconds

        Returns:
            True if handled successfully, False otherwise
        """
        try:
            entry = await self.call_entry_repo.get_entry(entry_id)
            if not entry:
                logger.error(f"Entry {entry_id} not found")
                return False

            queue = await self.queue_repo.get_queue(entry.queue_id)
            if not queue:
                logger.error(f"Queue {entry.queue_id} not found")
                return False

            # Update entry status to FAILED
            await self.call_entry_repo.update_entry_status(
                entry_id=entry_id,
                new_status=CallEntryStatus.FAILED,
                reason=f"Call failed: {failure_reason.value}",
                failure_reason=failure_reason,
                failure_details=failure_details,
                call_duration=call_duration
            )

            # Check if should retry
            if self.should_retry(queue, entry, failure_reason):
                retry_time = self.calculate_retry_time(queue, entry, failure_reason)
                new_retry_count = entry.retry_count + 1

                success = await self.call_entry_repo.schedule_retry(
                    entry_id=entry_id,
                    retry_at=retry_time,
                    retry_count=new_retry_count
                )

                if success:
                    logger.info(
                        f"Scheduled retry #{new_retry_count} for {entry_id} at {retry_time.isoformat()}"
                    )
                return success
            else:
                # Move to dead letter queue
                success = await self.call_entry_repo.move_to_dead_letter(
                    entry_id=entry_id,
                    reason=f"Max retries exceeded or non-retriable failure: {failure_reason.value}"
                )

                if success:
                    logger.info(f"Moved {entry_id} to dead letter queue")
                return success

        except Exception as e:
            logger.error(f"Failed to handle call failure for {entry_id}: {str(e)}")
            return False

    async def handle_call_success(
        self,
        entry_id: str,
        call_sid: str,
        call_duration: Optional[int] = None
    ) -> bool:
        """
        Handle successful call completion

        Args:
            entry_id: Entry identifier
            call_sid: Twilio call SID
            call_duration: Call duration in seconds

        Returns:
            True if handled successfully, False otherwise
        """
        try:
            return await self.call_entry_repo.update_entry_status(
                entry_id=entry_id,
                new_status=CallEntryStatus.SUCCESS,
                reason="Call completed successfully",
                call_sid=call_sid,
                call_duration=call_duration
            )
        except Exception as e:
            logger.error(f"Failed to handle call success for {entry_id}: {str(e)}")
            return False

    async def process_ready_retries(self) -> int:
        """
        Process all retry-scheduled calls that are ready to execute

        Returns:
            Number of retries processed
        """
        try:
            ready_retries = await self.call_entry_repo.get_retry_scheduled_calls()

            processed = 0
            for entry in ready_retries:
                queue = await self.queue_repo.get_queue(entry.queue_id)
                if not queue or queue.state != QueueState.ACTIVE:
                    continue

                if not self.is_within_time_window(queue):
                    continue

                success = await self.call_entry_repo.promote_retry_to_pending(entry.entry_id)

                if success:
                    processed += 1
                    logger.info(f"Moved {entry.entry_id} from RETRY_SCHEDULED to PENDING")

            if processed > 0:
                logger.info(f"Processed {processed} ready retries")

            return processed

        except Exception as e:
            logger.error(f"Failed to process ready retries: {str(e)}")
            return 0

    async def can_start_new_call(self, queue_id: str) -> bool:
        """
        Check if queue can start a new call based on max_concurrent_calls limit

        Args:
            queue_id: Queue identifier

        Returns:
            True if can start new call, False if at limit
        """
        try:
            queue = await self.queue_repo.get_queue(queue_id)
            if not queue:
                return False

            calling_now = await self.call_entry_repo.count_calling_now(queue_id)

            if calling_now >= queue.max_concurrent_calls:
                logger.debug(
                    f"Queue {queue_id} at concurrent call limit "
                    f"({calling_now}/{queue.max_concurrent_calls})"
                )
                return False

            return True

        except Exception as e:
            logger.error(f"Failed to check concurrent calls for {queue_id}: {str(e)}")
            return False

    async def mark_queue_completed_if_done(self, queue_id: str) -> bool:
        """
        Mark queue as completed if all calls are processed

        Args:
            queue_id: Queue identifier

        Returns:
            True if queue was marked completed, False otherwise
        """
        try:
            queue = await self.queue_repo.get_queue(queue_id)
            if not queue or queue.state != QueueState.ACTIVE:
                return False

            stats = await self.call_entry_repo.get_queue_statistics(queue_id, queue.name)
            if not stats:
                return False

            # Check if all calls are processed
            if stats.pending_calls == 0 and stats.retry_scheduled_calls == 0 and stats.calling_now == 0:
                success = await self.queue_repo.update_queue_state(queue_id, QueueState.COMPLETED)
                if success:
                    logger.info(f"Queue {queue_id} marked as completed")
                return success

            return False

        except Exception as e:
            logger.error(f"Failed to check queue completion for {queue_id}: {str(e)}")
            return False


# Singleton instance
_scheduler: Optional[QueueScheduler] = None


def get_queue_scheduler() -> QueueScheduler:
    """Get queue scheduler singleton"""
    global _scheduler
    if _scheduler is None:
        _scheduler = QueueScheduler()
    return _scheduler
