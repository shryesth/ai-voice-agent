"""
Recipient Service for managing call queue recipients.

This service handles:
- CRUD operations for recipients
- Call attempt tracking and timeline
- Retry logic and DLQ management
- Status transitions
"""

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any

from bson import ObjectId
from beanie.operators import In

from backend.app.models.enums import (
    RecipientStatus,
    CallOutcome,
    FailureReason,
    ExternalSource,
    ContactType,
    RETRY_DELAYS_SECONDS,
    NON_RETRIABLE_FAILURES,
    DEFAULT_MAX_RETRIES,
)
from backend.app.models.call_queue import CallQueue
from backend.app.models.recipient import (
    Recipient,
    CallAttempt,
    ConversationResult,
)
from backend.app.models.call_record import CallRecord

logger = logging.getLogger(__name__)


class RecipientService:
    """Service for managing call queue recipients."""

    def _validate_phone_number(self, phone: str) -> bool:
        """
        Validate phone number is in E.164 format.

        E.164 format: +[1-9][0-9]{6,14}

        Args:
            phone: Phone number to validate

        Returns:
            True if valid, False otherwise
        """
        return bool(re.match(r"^\+[1-9]\d{6,14}$", phone))

    async def create_recipient(
        self,
        queue_id: str,
        contact_phone: str,
        contact_name: Optional[str] = None,
        contact_type: ContactType = ContactType.UNKNOWN,
        language: str = "en",
        **kwargs,
    ) -> Recipient:
        """
        Create a new recipient in a queue.

        Args:
            queue_id: CallQueue document ID
            contact_phone: Phone number in E.164 format
            contact_name: Contact's name
            contact_type: Type of contact
            language: Language code
            **kwargs: Additional recipient fields

        Returns:
            Created Recipient document

        Raises:
            ValueError: If queue not found, duplicate phone, or invalid phone format
        """
        # Validate phone format
        if not self._validate_phone_number(contact_phone):
            raise ValueError(f"Phone must be in E.164 format (+[country][number]): {contact_phone}")

        # Verify queue exists
        queue = await CallQueue.get(ObjectId(queue_id))
        if not queue:
            raise ValueError(f"Queue not found: {queue_id}")
        if queue.deleted_at:
            raise ValueError(f"Queue is deleted: {queue_id}")

        # Check for duplicate phone in same queue (pending/retrying only)
        existing = await Recipient.find_one(
            Recipient.queue_id == ObjectId(queue_id),
            Recipient.contact_phone == contact_phone,
            In(Recipient.status, [
                RecipientStatus.PENDING,
                RecipientStatus.CALLING,
                RecipientStatus.RETRYING,
            ]),
        )
        if existing:
            raise ValueError(f"Recipient with phone {contact_phone} already pending in queue")

        # Create recipient
        recipient = Recipient(
            queue_id=queue.id,
            contact_phone=contact_phone,
            contact_name=contact_name,
            contact_type=contact_type,
            language=language,
            external_source=ExternalSource.MANUAL,
            status=RecipientStatus.PENDING,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            **kwargs,
        )

        await recipient.insert()
        logger.info(f"Created recipient: {recipient.id} for queue {queue_id}")
        return recipient

    async def get_recipient_by_id(self, recipient_id: str) -> Optional[Recipient]:
        """
        Get a recipient by ID.

        Args:
            recipient_id: Recipient document ID

        Returns:
            Recipient document or None
        """
        return await Recipient.get(ObjectId(recipient_id))

    async def list_recipients(
        self,
        queue_id: str,
        status: Optional[RecipientStatus] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> List[Recipient]:
        """
        List recipients in a queue.

        Args:
            queue_id: CallQueue document ID
            status: Filter by status
            skip: Number to skip (pagination)
            limit: Maximum to return

        Returns:
            List of Recipient documents
        """
        from beanie import PydanticObjectId
        from backend.app.models.call_queue import CallQueue

        queue_obj_id = PydanticObjectId(queue_id)

        query = {"queue_id": queue_obj_id}
        if status:
            query["status"] = status.value

        recipients = await (
            Recipient.find(query)
            .skip(skip)
            .limit(limit)
            .sort([("priority", -1), ("created_at", 1)])
            .to_list()
        )
        return recipients

    async def get_ready_recipients(
        self,
        queue_id: str,
        max_count: int = 10,
    ) -> List[Recipient]:
        """
        Get recipients ready for processing.

        Returns recipients that are:
        - PENDING status
        - RETRYING status with next_retry_at <= now

        Args:
            queue_id: CallQueue document ID
            max_count: Maximum recipients to return

        Returns:
            List of ready Recipient documents
        """
        now = datetime.now(timezone.utc)

        # Get pending recipients
        from beanie import PydanticObjectId
        queue_obj_id = PydanticObjectId(queue_id)
        
        pending = await (
            Recipient.find(
                {"queue_id": queue_obj_id},
                Recipient.status == RecipientStatus.PENDING,
            )
            .sort([("-priority", -1), ("created_at", 1)])
            .limit(max_count)
            .to_list()
        )

        # Get retrying recipients that are due
        remaining = max_count - len(pending)
        if remaining > 0:
            retrying = await (
                Recipient.find(
                    {"queue_id": queue_obj_id},
                    Recipient.status == RecipientStatus.RETRYING,
                    Recipient.next_retry_at <= now,
                )
                .sort([("-priority", -1), ("next_retry_at", 1)])
                .limit(remaining)
                .to_list()
            )
            pending.extend(retrying)

        return pending

    async def mark_calling(
        self,
        recipient_id: str,
        call_record_id: str,
    ) -> Recipient:
        """
        Mark recipient as currently being called.

        Args:
            recipient_id: Recipient document ID
            call_record_id: CallRecord document ID

        Returns:
            Updated Recipient document
        """
        recipient = await self.get_recipient_by_id(recipient_id)
        if not recipient:
            raise ValueError(f"Recipient not found: {recipient_id}")

        recipient.status = RecipientStatus.CALLING
        recipient.current_call_record_id = call_record_id
        recipient.first_attempted_at = recipient.first_attempted_at or datetime.now(timezone.utc)
        recipient.updated_at = datetime.now(timezone.utc)

        await recipient.save()
        return recipient

    async def handle_call_completion(
        self,
        recipient_id: str,
        call_record_id: str,
        outcome: CallOutcome,
        failure_reason: Optional[FailureReason] = None,
        duration_seconds: Optional[int] = None,
        conversation_result: Optional[Dict[str, Any]] = None,
        error_details: Optional[str] = None,
    ) -> Recipient:
        """
        Handle call completion and determine next action.

        Args:
            recipient_id: Recipient document ID
            call_record_id: CallRecord document ID
            outcome: Call outcome
            failure_reason: Reason for failure (if applicable)
            duration_seconds: Call duration
            conversation_result: Extracted conversation data
            error_details: Error message (if applicable)

        Returns:
            Updated Recipient document

        Note:
            Multiple database updates are performed (call attempts, status, timestamps).
            Beanie does not support transactions for single-document updates with nested arrays.
            If atomicity becomes critical, consider using MongoDB transactions with a
            higher-level coordinator or retrying at the task level.
        """
        recipient = await self.get_recipient_by_id(recipient_id)
        if not recipient:
            raise ValueError(f"Recipient not found: {recipient_id}")

        # Get queue for retry strategy
        queue = await CallQueue.get(recipient.queue_id)
        max_retries = queue.retry_strategy.max_retries if queue else DEFAULT_MAX_RETRIES

        # Create call attempt record
        attempt = CallAttempt(
            attempt_number=len(recipient.call_attempts) + 1,
            call_record_id=call_record_id,
            outcome=outcome,
            failure_reason=failure_reason,
            duration_seconds=duration_seconds,
            started_at=recipient.first_attempted_at or datetime.now(timezone.utc),
            ended_at=datetime.now(timezone.utc),
            notes=error_details,
        )
        recipient.call_attempts.append(attempt)

        # Update conversation result if provided
        if conversation_result:
            recipient.conversation_result = ConversationResult(**conversation_result)

        # Determine next status based on outcome
        if self._is_successful_outcome(outcome):
            recipient.status = RecipientStatus.COMPLETED
            recipient.completed_at = datetime.now(timezone.utc)
            logger.info(f"Recipient {recipient_id} completed successfully")

        elif self._is_terminal_failure(failure_reason):
            # Non-retriable failure
            recipient.status = RecipientStatus.FAILED
            recipient.completed_at = datetime.now(timezone.utc)
            recipient.last_failure_reason = failure_reason
            logger.info(f"Recipient {recipient_id} failed with terminal reason: {failure_reason}")

        elif recipient.retry_count >= max_retries:
            # Max retries exceeded
            recipient.status = RecipientStatus.NOT_REACHABLE
            recipient.completed_at = datetime.now(timezone.utc)
            recipient.last_failure_reason = failure_reason
            logger.info(f"Recipient {recipient_id} not reachable after {max_retries} retries")

        else:
            # Schedule retry
            recipient.status = RecipientStatus.RETRYING
            recipient.retry_count += 1
            recipient.last_failure_reason = failure_reason

            # Calculate retry delay
            delay = self._get_retry_delay(failure_reason, queue, recipient.retry_count)
            recipient.next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
            logger.info(
                f"Recipient {recipient_id} scheduled for retry #{recipient.retry_count} "
                f"in {delay} seconds"
            )

        recipient.current_call_record_id = None
        recipient.updated_at = datetime.now(timezone.utc)
        await recipient.save()

        return recipient

    def _is_successful_outcome(self, outcome: CallOutcome) -> bool:
        """Check if outcome indicates success."""
        return outcome in {
            CallOutcome.COMPLETED_FULL,
            CallOutcome.COMPLETED_PARTIAL,
        }

    def _is_terminal_failure(self, failure_reason: Optional[FailureReason]) -> bool:
        """Check if failure reason is terminal (no retry)."""
        return failure_reason in NON_RETRIABLE_FAILURES

    def _get_retry_delay(
        self,
        failure_reason: Optional[FailureReason],
        queue: Optional[CallQueue],
        retry_count: int,
    ) -> int:
        """
        Calculate retry delay in seconds.

        Args:
            failure_reason: Reason for failure
            queue: CallQueue with retry strategy
            retry_count: Current retry count

        Returns:
            Delay in seconds
        """
        # Get base delay from queue config or defaults
        if queue and queue.retry_strategy:
            strategy = queue.retry_strategy
            delay_map = {
                FailureReason.NO_ANSWER: strategy.no_answer_delay,
                FailureReason.BUSY: strategy.busy_delay,
                FailureReason.VOICEMAIL: strategy.voicemail_delay,
                FailureReason.TIMEOUT: strategy.timeout_delay,
                FailureReason.PERSON_NOT_AVAILABLE: strategy.person_not_available_delay,
                FailureReason.SHORT_DURATION: strategy.short_duration_delay,
                FailureReason.FAILED: strategy.failed_delay,
            }
            base_delay = delay_map.get(failure_reason, strategy.failed_delay)

            # Apply exponential backoff if enabled
            if strategy.exponential_backoff:
                base_delay = base_delay * retry_count
        else:
            # Use defaults
            base_delay = RETRY_DELAYS_SECONDS.get(failure_reason, 900)

        return base_delay

    async def move_to_dlq(
        self,
        recipient_id: str,
        reason: str,
    ) -> Recipient:
        """
        Move recipient to Dead Letter Queue.

        Args:
            recipient_id: Recipient document ID
            reason: Reason for DLQ

        Returns:
            Updated Recipient document
        """
        recipient = await self.get_recipient_by_id(recipient_id)
        if not recipient:
            raise ValueError(f"Recipient not found: {recipient_id}")

        recipient.status = RecipientStatus.DLQ
        recipient.moved_to_dlq = True
        recipient.dlq_reason = reason
        recipient.dlq_moved_at = datetime.now(timezone.utc)
        recipient.completed_at = datetime.now(timezone.utc)
        recipient.updated_at = datetime.now(timezone.utc)

        await recipient.save()
        logger.info(f"Moved recipient {recipient_id} to DLQ: {reason}")
        return recipient

    async def retry_from_dlq(
        self,
        recipient_id: str,
        reset_retry_count: bool = False,
    ) -> Recipient:
        """
        Retry a recipient from DLQ.

        Args:
            recipient_id: Recipient document ID
            reset_retry_count: Whether to reset retry count

        Returns:
            Updated Recipient document
        """
        recipient = await self.get_recipient_by_id(recipient_id)
        if not recipient:
            raise ValueError(f"Recipient not found: {recipient_id}")

        if recipient.status != RecipientStatus.DLQ:
            raise ValueError(f"Recipient is not in DLQ: {recipient.status}")

        recipient.status = RecipientStatus.PENDING
        recipient.moved_to_dlq = False
        recipient.dlq_reason = None
        recipient.dlq_moved_at = None
        recipient.completed_at = None
        recipient.next_retry_at = None
        recipient.last_failure_reason = None

        if reset_retry_count:
            recipient.retry_count = 0
            recipient.call_attempts = []

        recipient.updated_at = datetime.now(timezone.utc)
        await recipient.save()

        logger.info(f"Retrying recipient {recipient_id} from DLQ")
        return recipient

    async def skip_recipient(
        self,
        recipient_id: str,
        reason: Optional[str] = None,
    ) -> Recipient:
        """
        Skip a recipient (mark as SKIPPED).

        Args:
            recipient_id: Recipient document ID
            reason: Optional skip reason

        Returns:
            Updated Recipient document
        """
        recipient = await self.get_recipient_by_id(recipient_id)
        if not recipient:
            raise ValueError(f"Recipient not found: {recipient_id}")

        recipient.status = RecipientStatus.SKIPPED
        recipient.completed_at = datetime.now(timezone.utc)
        recipient.updated_at = datetime.now(timezone.utc)

        if reason:
            recipient.dlq_reason = f"Skipped: {reason}"

        await recipient.save()
        logger.info(f"Skipped recipient {recipient_id}")
        return recipient

    async def get_timeline(self, recipient_id: str) -> List[Dict[str, Any]]:
        """
        Get the call attempt timeline for a recipient.

        Args:
            recipient_id: Recipient document ID

        Returns:
            List of timeline events
        """
        recipient = await self.get_recipient_by_id(recipient_id)
        if not recipient:
            raise ValueError(f"Recipient not found: {recipient_id}")

        timeline = []
        for attempt in recipient.call_attempts:
            event = {
                "attempt_number": attempt.attempt_number,
                "call_record_id": attempt.call_record_id,
                "outcome": attempt.outcome.value,
                "failure_reason": attempt.failure_reason.value if attempt.failure_reason else None,
                "duration_seconds": attempt.duration_seconds,
                "started_at": attempt.started_at.isoformat(),
                "ended_at": attempt.ended_at.isoformat() if attempt.ended_at else None,
                "notes": attempt.notes,
            }
            timeline.append(event)

        return timeline

    async def list_dlq(
        self,
        queue_id: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> List[Recipient]:
        """
        List recipients in DLQ.

        Args:
            queue_id: Optional filter by queue
            skip: Number to skip
            limit: Maximum to return

        Returns:
            List of DLQ recipients
        """
        query = {"status": RecipientStatus.DLQ.value}
        if queue_id:
            query["queue_id"] = ObjectId(queue_id)

        recipients = await (
            Recipient.find(query)
            .skip(skip)
            .limit(limit)
            .sort("-dlq_moved_at")
            .to_list()
        )
        return recipients

    async def update_urgency(
        self,
        recipient_id: str,
        urgency_flagged: bool,
        keywords: List[str] = None,
    ) -> Recipient:
        """
        Update urgency flag for recipient.

        Args:
            recipient_id: Recipient document ID
            urgency_flagged: Whether urgency was detected
            keywords: Detected urgency keywords

        Returns:
            Updated Recipient document
        """
        recipient = await self.get_recipient_by_id(recipient_id)
        if not recipient:
            raise ValueError(f"Recipient not found: {recipient_id}")

        recipient.urgency_flagged = urgency_flagged
        recipient.urgency_keywords_detected = keywords or []
        recipient.updated_at = datetime.now(timezone.utc)

        await recipient.save()
        return recipient

    async def request_human_callback(
        self,
        recipient_id: str,
        reason: Optional[str] = None,
    ) -> Recipient:
        """
        Mark recipient as requesting human callback.

        Args:
            recipient_id: Recipient document ID
            reason: Reason for callback request

        Returns:
            Updated Recipient document
        """
        recipient = await self.get_recipient_by_id(recipient_id)
        if not recipient:
            raise ValueError(f"Recipient not found: {recipient_id}")

        recipient.human_callback_requested = True
        recipient.human_callback_reason = reason
        recipient.updated_at = datetime.now(timezone.utc)

        await recipient.save()
        logger.info(f"Human callback requested for recipient {recipient_id}")
        return recipient


# Singleton instance
recipient_service = RecipientService()
