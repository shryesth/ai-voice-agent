"""
CallQueue Service for managing call queues.

This service handles:
- CRUD operations for call queues
- State transitions (DRAFT -> ACTIVE -> PAUSED -> COMPLETED)
- Queue statistics and status
"""

import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

from bson import ObjectId
from beanie import PydanticObjectId

from backend.app.models.enums import (
    QueueState,
    QueueMode,
    RecipientStatus,
)
from backend.app.models.geography import Geography
from backend.app.models.call_queue import (
    CallQueue,
    QueueStats,
    can_transition_to,
)
from backend.app.models.recipient import Recipient

logger = logging.getLogger(__name__)


class CallQueueService:
    """Service for managing call queues."""

    async def create_queue(
        self,
        geography_id: str,
        name: str,
        description: Optional[str] = None,
        **kwargs,
    ) -> CallQueue:
        """
        Create a new call queue.

        Args:
            geography_id: Geography document ID
            name: Queue name
            description: Optional description
            **kwargs: Additional queue configuration

        Returns:
            Created CallQueue document

        Raises:
            ValueError: If geography not found or name already exists
        """
        # Verify geography exists
        geography = await Geography.get(ObjectId(geography_id))
        if not geography:
            raise ValueError(f"Geography not found: {geography_id}")
        if geography.deleted_at:
            raise ValueError(f"Geography is deleted: {geography_id}")

        # Check for duplicate name within geography
        existing = await CallQueue.find_one(
            CallQueue.geography_id.id == ObjectId(geography_id),
            CallQueue.name == name,
            CallQueue.deleted_at == None,
        )
        if existing:
            raise ValueError(f"Queue with name '{name}' already exists in this geography")

        # Create queue
        queue = CallQueue(
            name=name,
            description=description,
            geography_id=geography.id,
            state=QueueState.DRAFT,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            **kwargs,
        )

        await queue.insert()
        logger.info(f"Created queue: {queue.id} ({queue.name})")
        return queue

    async def get_queue_by_id(
        self,
        queue_id: str,
        include_deleted: bool = False,
    ) -> Optional[CallQueue]:
        """
        Get a queue by ID.

        Args:
            queue_id: Queue document ID
            include_deleted: Whether to include soft-deleted queues

        Returns:
            CallQueue document or None
        """
        queue = await CallQueue.get(ObjectId(queue_id))
        if queue and not include_deleted and queue.deleted_at:
            return None
        return queue

    async def list_queues(
        self,
        geography_id: Optional[str] = None,
        state: Optional[QueueState] = None,
        mode: Optional[QueueMode] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> List[CallQueue]:
        """
        List queues with optional filters.

        Args:
            geography_id: Filter by geography
            state: Filter by state
            mode: Filter by mode
            skip: Number to skip (pagination)
            limit: Maximum to return

        Returns:
            List of CallQueue documents
        """
        query = {"deleted_at": None}

        if geography_id:
            query["geography_id"] = ObjectId(geography_id)
        if state:
            query["state"] = state.value
        if mode:
            query["mode"] = mode.value

        queues = await CallQueue.find(query).skip(skip).limit(limit).sort("-created_at").to_list()
        return queues

    async def update_queue(
        self,
        queue_id: str,
        **updates,
    ) -> CallQueue:
        """
        Update a queue.

        Only allowed in DRAFT or PAUSED states (except for stats updates).

        Args:
            queue_id: Queue document ID
            **updates: Fields to update

        Returns:
            Updated CallQueue document

        Raises:
            ValueError: If queue not found or update not allowed
        """
        queue = await self.get_queue_by_id(queue_id)
        if not queue:
            raise ValueError(f"Queue not found: {queue_id}")

        # Certain fields can only be updated in DRAFT/PAUSED states
        restricted_fields = {
            "name", "mode", "call_type", "max_concurrent_calls",
            "time_windows", "retry_strategy", "clarity_sync",
        }

        if queue.state not in (QueueState.DRAFT, QueueState.PAUSED):
            restricted_updates = set(updates.keys()) & restricted_fields
            if restricted_updates:
                raise ValueError(
                    f"Cannot update {restricted_updates} while queue is {queue.state}"
                )

        # Apply updates
        for key, value in updates.items():
            if hasattr(queue, key):
                setattr(queue, key, value)

        queue.updated_at = datetime.utcnow()
        await queue.save()

        logger.info(f"Updated queue: {queue_id}")
        return queue

    async def start_queue(self, queue_id: str) -> CallQueue:
        """
        Start a queue (transition DRAFT -> ACTIVE).

        Args:
            queue_id: Queue document ID

        Returns:
            Updated CallQueue document

        Raises:
            ValueError: If transition not allowed
        """
        queue = await self.get_queue_by_id(queue_id)
        if not queue:
            raise ValueError(f"Queue not found: {queue_id}")

        if not can_transition_to(queue.state, QueueState.ACTIVE):
            raise ValueError(f"Cannot start queue in state: {queue.state}")

        queue.state = QueueState.ACTIVE
        queue.started_at = queue.started_at or datetime.utcnow()
        queue.updated_at = datetime.utcnow()
        await queue.save()

        logger.info(f"Started queue: {queue_id}")
        return queue

    async def pause_queue(self, queue_id: str) -> CallQueue:
        """
        Pause a queue (transition ACTIVE -> PAUSED).

        Args:
            queue_id: Queue document ID

        Returns:
            Updated CallQueue document

        Raises:
            ValueError: If transition not allowed
        """
        queue = await self.get_queue_by_id(queue_id)
        if not queue:
            raise ValueError(f"Queue not found: {queue_id}")

        if not can_transition_to(queue.state, QueueState.PAUSED):
            raise ValueError(f"Cannot pause queue in state: {queue.state}")

        queue.state = QueueState.PAUSED
        queue.updated_at = datetime.utcnow()
        await queue.save()

        logger.info(f"Paused queue: {queue_id}")
        return queue

    async def resume_queue(self, queue_id: str) -> CallQueue:
        """
        Resume a paused queue (transition PAUSED -> ACTIVE).

        Args:
            queue_id: Queue document ID

        Returns:
            Updated CallQueue document

        Raises:
            ValueError: If transition not allowed
        """
        queue = await self.get_queue_by_id(queue_id)
        if not queue:
            raise ValueError(f"Queue not found: {queue_id}")

        if not can_transition_to(queue.state, QueueState.ACTIVE):
            raise ValueError(f"Cannot resume queue in state: {queue.state}")

        queue.state = QueueState.ACTIVE
        queue.updated_at = datetime.utcnow()
        await queue.save()

        logger.info(f"Resumed queue: {queue_id}")
        return queue

    async def complete_queue(self, queue_id: str) -> CallQueue:
        """
        Complete a queue (transition ACTIVE -> COMPLETED).

        Only valid for BATCH mode queues.

        Args:
            queue_id: Queue document ID

        Returns:
            Updated CallQueue document

        Raises:
            ValueError: If transition not allowed
        """
        queue = await self.get_queue_by_id(queue_id)
        if not queue:
            raise ValueError(f"Queue not found: {queue_id}")

        if queue.mode == QueueMode.FOREVER:
            raise ValueError("Cannot complete a FOREVER mode queue")

        if not can_transition_to(queue.state, QueueState.COMPLETED):
            raise ValueError(f"Cannot complete queue in state: {queue.state}")

        queue.state = QueueState.COMPLETED
        queue.completed_at = datetime.utcnow()
        queue.updated_at = datetime.utcnow()
        await queue.save()

        logger.info(f"Completed queue: {queue_id}")
        return queue

    async def cancel_queue(self, queue_id: str) -> CallQueue:
        """
        Cancel a queue (transition to CANCELLED).

        Moves all pending recipients to DLQ.

        Args:
            queue_id: Queue document ID

        Returns:
            Updated CallQueue document

        Raises:
            ValueError: If transition not allowed
        """
        queue = await self.get_queue_by_id(queue_id)
        if not queue:
            raise ValueError(f"Queue not found: {queue_id}")

        if not can_transition_to(queue.state, QueueState.CANCELLED):
            raise ValueError(f"Cannot cancel queue in state: {queue.state}")

        # Move pending recipients to DLQ
        pending_recipients = await Recipient.find(
            Recipient.queue_id.id == ObjectId(queue_id),
            Recipient.status.in_([
                RecipientStatus.PENDING,
                RecipientStatus.RETRYING,
            ]),
        ).to_list()

        for recipient in pending_recipients:
            recipient.status = RecipientStatus.DLQ
            recipient.moved_to_dlq = True
            recipient.dlq_reason = "Queue cancelled"
            recipient.dlq_moved_at = datetime.utcnow()
            recipient.updated_at = datetime.utcnow()
            await recipient.save()

        queue.state = QueueState.CANCELLED
        queue.updated_at = datetime.utcnow()
        await queue.save()

        logger.info(f"Cancelled queue: {queue_id}, moved {len(pending_recipients)} to DLQ")
        return queue

    async def delete_queue(self, queue_id: str, hard_delete: bool = False) -> bool:
        """
        Delete a queue (soft delete by default).

        Args:
            queue_id: Queue document ID
            hard_delete: If True, permanently delete

        Returns:
            True if deleted

        Raises:
            ValueError: If queue not found or has active calls
        """
        queue = await self.get_queue_by_id(queue_id, include_deleted=True)
        if not queue:
            raise ValueError(f"Queue not found: {queue_id}")

        # Check for active calls
        active_count = await Recipient.find(
            Recipient.queue_id.id == ObjectId(queue_id),
            Recipient.status == RecipientStatus.CALLING,
        ).count()

        if active_count > 0:
            raise ValueError(f"Cannot delete queue with {active_count} active calls")

        if hard_delete:
            await queue.delete()
            logger.info(f"Hard deleted queue: {queue_id}")
        else:
            queue.deleted_at = datetime.utcnow()
            queue.updated_at = datetime.utcnow()
            await queue.save()
            logger.info(f"Soft deleted queue: {queue_id}")

        return True

    async def get_queue_status(self, queue_id: str) -> Dict[str, Any]:
        """
        Get detailed queue status with statistics.

        Args:
            queue_id: Queue document ID

        Returns:
            Dict with queue status and statistics
        """
        queue = await self.get_queue_by_id(queue_id)
        if not queue:
            raise ValueError(f"Queue not found: {queue_id}")

        # Get recipient counts by status
        status_counts = {}
        for status in RecipientStatus:
            count = await Recipient.find(
                Recipient.queue_id.id == ObjectId(queue_id),
                Recipient.status == status,
            ).count()
            status_counts[status.value] = count

        # Calculate progress
        total = sum(status_counts.values())
        completed = status_counts.get(RecipientStatus.COMPLETED.value, 0)
        failed = status_counts.get(RecipientStatus.FAILED.value, 0)
        not_reachable = status_counts.get(RecipientStatus.NOT_REACHABLE.value, 0)
        dlq = status_counts.get(RecipientStatus.DLQ.value, 0)

        processed = completed + failed + not_reachable + dlq
        progress_percent = (processed / total * 100) if total > 0 else 0

        return {
            "queue_id": str(queue.id),
            "name": queue.name,
            "state": queue.state.value,
            "mode": queue.mode.value,
            "total_recipients": total,
            "status_counts": status_counts,
            "progress_percent": round(progress_percent, 2),
            "stats": queue.stats.model_dump() if queue.stats else {},
            "started_at": queue.started_at.isoformat() if queue.started_at else None,
            "completed_at": queue.completed_at.isoformat() if queue.completed_at else None,
        }

    async def refresh_queue_stats(self, queue_id: str) -> CallQueue:
        """
        Refresh queue statistics from recipient data.

        Args:
            queue_id: Queue document ID

        Returns:
            Updated CallQueue with fresh stats
        """
        queue = await self.get_queue_by_id(queue_id)
        if not queue:
            raise ValueError(f"Queue not found: {queue_id}")

        # Count recipients by status
        stats = QueueStats()

        for status in RecipientStatus:
            count = await Recipient.find(
                Recipient.queue_id.id == ObjectId(queue_id),
                Recipient.status == status,
            ).count()

            if status == RecipientStatus.PENDING:
                stats.pending_count = count
            elif status == RecipientStatus.CALLING:
                stats.calling_count = count
            elif status == RecipientStatus.RETRYING:
                stats.retrying_count = count
            elif status == RecipientStatus.COMPLETED:
                stats.completed_count = count
            elif status == RecipientStatus.FAILED:
                stats.failed_count = count
            elif status == RecipientStatus.NOT_REACHABLE:
                stats.not_reachable_count = count
            elif status == RecipientStatus.SKIPPED:
                stats.skipped_count = count
            elif status == RecipientStatus.DLQ:
                stats.dlq_count = count

        stats.total_recipients = (
            stats.pending_count + stats.calling_count + stats.retrying_count +
            stats.completed_count + stats.failed_count + stats.not_reachable_count +
            stats.skipped_count + stats.dlq_count
        )

        # Count urgent flagged
        stats.urgent_flagged_count = await Recipient.find(
            Recipient.queue_id.id == ObjectId(queue_id),
            Recipient.urgency_flagged == True,
        ).count()

        # Get successful verifications
        stats.successful_verifications = await Recipient.find(
            Recipient.queue_id.id == ObjectId(queue_id),
            Recipient.conversation_result.is_visit_confirmed == True,
        ).count()

        queue.stats = stats
        queue.updated_at = datetime.utcnow()
        await queue.save()

        return queue

    async def check_queue_completion(self, queue_id: str) -> bool:
        """
        Check if a BATCH mode queue should be marked as completed.

        Args:
            queue_id: Queue document ID

        Returns:
            True if queue was marked as completed
        """
        queue = await self.get_queue_by_id(queue_id)
        if not queue:
            return False

        # Only BATCH mode queues auto-complete
        if queue.mode != QueueMode.BATCH:
            return False

        # Must be ACTIVE to complete
        if queue.state != QueueState.ACTIVE:
            return False

        # Check if any recipients still pending processing
        pending = await Recipient.find(
            Recipient.queue_id.id == ObjectId(queue_id),
            Recipient.status.in_([
                RecipientStatus.PENDING,
                RecipientStatus.CALLING,
                RecipientStatus.RETRYING,
            ]),
        ).count()

        if pending == 0:
            await self.complete_queue(queue_id)
            return True

        return False


# Singleton instance
call_queue_service = CallQueueService()
