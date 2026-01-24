"""
Queue Repository

MongoDB repository for managed queue configuration and call entry management.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from backend.app.models.queue_models import (
    QueueConfig,
    CallEntry,
    QueueState,
    CallEntryStatus,
    FailureReason,
    StateHistoryEntry,
    QueueStatistics,
)
from backend.app.services.database import get_database_safe

logger = logging.getLogger(__name__)


class QueueRepository:
    """Repository for managing queue configurations"""

    COLLECTION_NAME = "managed_queues"

    def __init__(self, db: Optional[AsyncIOMotorDatabase] = None):
        """Initialize queue repository"""
        self._db = db
        self._collection = None

    @property
    def db(self):
        if self._db is None:
            self._db = get_database_safe()
        return self._db

    @property
    def collection(self):
        if self._collection is None:
            self._collection = self.db[self.COLLECTION_NAME]
        return self._collection

    async def create_indexes(self):
        """Create database indexes for performance"""
        try:
            await self.collection.create_index("queue_id", unique=True)
            await self.collection.create_index("domain")
            await self.collection.create_index("state")
            await self.collection.create_index("created_at")
            logger.info(f"Created indexes for {self.COLLECTION_NAME} collection")
        except Exception as e:
            logger.error(f"Failed to create indexes: {str(e)}")

    async def create_queue(self, queue: QueueConfig) -> bool:
        """Create a new queue configuration"""
        try:
            document = queue.model_dump()
            await self.collection.insert_one(document)
            logger.info(f"Created queue: {queue.queue_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to create queue {queue.queue_id}: {str(e)}")
            return False

    async def get_queue(self, queue_id: str) -> Optional[QueueConfig]:
        """Get queue configuration by ID"""
        try:
            document = await self.collection.find_one({"queue_id": queue_id})
            if document:
                document.pop("_id", None)
                return QueueConfig(**document)
            return None
        except Exception as e:
            logger.error(f"Failed to get queue {queue_id}: {str(e)}")
            return None

    async def update_queue(self, queue_id: str, updates: Dict[str, Any]) -> bool:
        """Update queue configuration"""
        try:
            updates["updated_at"] = datetime.utcnow()
            result = await self.collection.update_one(
                {"queue_id": queue_id},
                {"$set": updates}
            )
            if result.modified_count > 0:
                logger.info(f"Updated queue: {queue_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to update queue {queue_id}: {str(e)}")
            return False

    async def delete_queue(self, queue_id: str) -> bool:
        """Delete queue configuration"""
        try:
            result = await self.collection.delete_one({"queue_id": queue_id})
            if result.deleted_count > 0:
                logger.info(f"Deleted queue: {queue_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to delete queue {queue_id}: {str(e)}")
            return False

    async def list_queues(
        self,
        domain: Optional[str] = None,
        state: Optional[QueueState] = None,
        limit: int = 100,
        skip: int = 0
    ) -> List[QueueConfig]:
        """List queues with optional filtering"""
        try:
            filter_query: Dict[str, Any] = {}
            if domain:
                filter_query["domain"] = domain
            if state:
                filter_query["state"] = state.value

            cursor = self.collection.find(filter_query).skip(skip).limit(limit).sort("created_at", -1)
            documents = await cursor.to_list(length=limit)

            queues = []
            for doc in documents:
                doc.pop("_id", None)
                queues.append(QueueConfig(**doc))

            return queues
        except Exception as e:
            logger.error(f"Failed to list queues: {str(e)}")
            return []

    async def update_queue_state(self, queue_id: str, new_state: QueueState) -> bool:
        """Update queue state with appropriate timestamps"""
        updates: Dict[str, Any] = {
            "state": new_state.value,
            "updated_at": datetime.utcnow()
        }

        if new_state == QueueState.ACTIVE:
            updates["started_at"] = datetime.utcnow()
        elif new_state in [QueueState.COMPLETED, QueueState.CANCELLED]:
            updates["completed_at"] = datetime.utcnow()

        return await self.update_queue(queue_id, updates)

    async def get_active_queues(self) -> List[QueueConfig]:
        """Get all active queues"""
        return await self.list_queues(state=QueueState.ACTIVE)


class CallEntryRepository:
    """Repository for managing call entries"""

    COLLECTION_NAME = "managed_call_entries"

    def __init__(self, db: Optional[AsyncIOMotorDatabase] = None):
        """Initialize call entry repository"""
        self._db = db
        self._collection = None

    @property
    def db(self):
        if self._db is None:
            self._db = get_database_safe()
        return self._db

    @property
    def collection(self):
        if self._collection is None:
            self._collection = self.db[self.COLLECTION_NAME]
        return self._collection

    async def create_indexes(self):
        """Create database indexes for performance"""
        try:
            await self.collection.create_index("entry_id", unique=True)
            await self.collection.create_index("queue_id")
            await self.collection.create_index("status")
            await self.collection.create_index("call_sid")
            await self.collection.create_index("phone_number")
            await self.collection.create_index("scheduled_for")
            await self.collection.create_index("retry_scheduled_at")
            await self.collection.create_index([("queue_id", 1), ("status", 1)])
            # Index for Clarity verification ID lookups (sparse to only index docs with this field)
            await self.collection.create_index(
                [("queue_id", 1), ("metadata.clarity_verification_id", 1)],
                sparse=True,
            )
            logger.info(f"Created indexes for {self.COLLECTION_NAME} collection")
        except Exception as e:
            logger.error(f"Failed to create indexes: {str(e)}")

    async def create_entry(self, entry: CallEntry) -> bool:
        """Create a new call entry"""
        try:
            document = entry.model_dump()
            await self.collection.insert_one(document)
            logger.info(f"Created call entry: {entry.entry_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to create call entry {entry.entry_id}: {str(e)}")
            return False

    async def bulk_create_entries(self, entries: List[CallEntry]) -> int:
        """Bulk create call entries"""
        try:
            documents = [entry.model_dump() for entry in entries]
            result = await self.collection.insert_many(documents)
            count = len(result.inserted_ids)
            logger.info(f"Bulk created {count} call entries")
            return count
        except Exception as e:
            logger.error(f"Failed to bulk create call entries: {str(e)}")
            return 0

    async def get_entry(self, entry_id: str) -> Optional[CallEntry]:
        """Get call entry by ID"""
        try:
            document = await self.collection.find_one({"entry_id": entry_id})
            if document:
                document.pop("_id", None)
                return CallEntry(**document)
            return None
        except Exception as e:
            logger.error(f"Failed to get call entry {entry_id}: {str(e)}")
            return None

    async def get_entry_by_call_sid(self, call_sid: str) -> Optional[CallEntry]:
        """Get call entry by Twilio call SID"""
        try:
            document = await self.collection.find_one({"call_sid": call_sid})
            if document:
                document.pop("_id", None)
                return CallEntry(**document)
            return None
        except Exception as e:
            logger.error(f"Failed to get call entry by call_sid {call_sid}: {str(e)}")
            return None

    async def find_by_external_id(
        self,
        queue_id: str,
        external_id_field: str,
        external_id_value: Any,
    ) -> Optional[CallEntry]:
        """
        Find a call entry by external ID (e.g., Clarity verification ID).

        Args:
            queue_id: Queue ID to search within
            external_id_field: Dot-notation field path (e.g., "metadata.clarity_verification_id")
            external_id_value: Value to match

        Returns:
            CallEntry if found, None otherwise
        """
        try:
            document = await self.collection.find_one({
                "queue_id": queue_id,
                external_id_field: external_id_value,
            })
            if document:
                document.pop("_id", None)
                return CallEntry(**document)
            return None
        except Exception as e:
            logger.error(f"Failed to find entry by external ID: {str(e)}")
            return None

    async def update_entry(self, entry_id: str, updates: Dict[str, Any]) -> bool:
        """Update call entry"""
        try:
            updates["updated_at"] = datetime.utcnow()
            result = await self.collection.update_one(
                {"entry_id": entry_id},
                {"$set": updates}
            )
            if result.modified_count > 0:
                logger.debug(f"Updated call entry: {entry_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to update call entry {entry_id}: {str(e)}")
            return False

    async def add_state_history(
        self,
        entry_id: str,
        from_state: Optional[CallEntryStatus],
        to_state: CallEntryStatus,
        reason: str,
        failure_reason: Optional[FailureReason] = None,
        call_sid: Optional[str] = None
    ) -> bool:
        """Add state history entry to audit trail"""
        try:
            history_entry = StateHistoryEntry(
                from_state=from_state,
                to_state=to_state,
                reason=reason,
                failure_reason=failure_reason,
                timestamp=datetime.utcnow(),
                call_sid=call_sid
            )

            result = await self.collection.update_one(
                {"entry_id": entry_id},
                {
                    "$push": {"state_history": history_entry.model_dump()},
                    "$set": {"updated_at": datetime.utcnow()}
                }
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Failed to add state history for {entry_id}: {str(e)}")
            return False

    async def update_entry_status(
        self,
        entry_id: str,
        new_status: CallEntryStatus,
        reason: str,
        failure_reason: Optional[FailureReason] = None,
        failure_details: Optional[str] = None,
        call_sid: Optional[str] = None,
        call_duration: Optional[int] = None
    ) -> bool:
        """Update entry status with audit trail"""
        try:
            entry = await self.get_entry(entry_id)
            if not entry:
                return False

            updates: Dict[str, Any] = {
                "status": new_status.value,
                "updated_at": datetime.utcnow()
            }

            if failure_reason:
                updates["failure_reason"] = failure_reason.value
            if failure_details:
                updates["failure_details"] = failure_details
            if call_sid:
                updates["call_sid"] = call_sid
            if call_duration is not None:
                updates["call_duration"] = call_duration

            if new_status == CallEntryStatus.CALLING:
                updates["started_at"] = datetime.utcnow()
            elif new_status in [CallEntryStatus.SUCCESS, CallEntryStatus.FAILED, CallEntryStatus.CANCELLED, CallEntryStatus.DEAD_LETTER]:
                updates["completed_at"] = datetime.utcnow()

            await self.update_entry(entry_id, updates)

            await self.add_state_history(
                entry_id=entry_id,
                from_state=CallEntryStatus(entry.status) if entry.status else None,
                to_state=new_status,
                reason=reason,
                failure_reason=failure_reason,
                call_sid=call_sid
            )

            return True
        except Exception as e:
            logger.error(f"Failed to update entry status for {entry_id}: {str(e)}")
            return False

    async def list_entries(
        self,
        queue_id: str,
        status: Optional[CallEntryStatus] = None,
        limit: int = 100,
        skip: int = 0
    ) -> List[CallEntry]:
        """List call entries with optional filtering"""
        try:
            filter_query: Dict[str, Any] = {"queue_id": queue_id}
            if status:
                filter_query["status"] = status.value

            cursor = self.collection.find(filter_query).skip(skip).limit(limit).sort("created_at", -1)
            documents = await cursor.to_list(length=limit)

            entries = []
            for doc in documents:
                doc.pop("_id", None)
                entries.append(CallEntry(**doc))

            return entries
        except Exception as e:
            logger.error(f"Failed to list entries for queue {queue_id}: {str(e)}")
            return []

    async def get_pending_calls(self, queue_id: str, limit: int = 1) -> List[CallEntry]:
        """Get pending calls ready to be executed"""
        try:
            now = datetime.utcnow()
            filter_query = {
                "queue_id": queue_id,
                "status": CallEntryStatus.PENDING.value,
                "$or": [
                    {"scheduled_for": None},
                    {"scheduled_for": {"$lte": now}}
                ]
            }

            cursor = self.collection.find(filter_query).sort("created_at", 1).limit(limit)
            documents = await cursor.to_list(length=limit)

            entries = []
            for doc in documents:
                doc.pop("_id", None)
                entries.append(CallEntry(**doc))

            return entries
        except Exception as e:
            logger.error(f"Failed to get pending calls for queue {queue_id}: {str(e)}")
            return []

    async def get_retry_scheduled_calls(self, queue_id: Optional[str] = None) -> List[CallEntry]:
        """Get calls scheduled for retry that are ready to execute"""
        try:
            now = datetime.utcnow()
            filter_query: Dict[str, Any] = {
                "status": CallEntryStatus.RETRY_SCHEDULED.value,
                "retry_scheduled_at": {"$lte": now}
            }

            if queue_id:
                filter_query["queue_id"] = queue_id

            cursor = self.collection.find(filter_query)
            documents = await cursor.to_list(length=None)

            entries = []
            for doc in documents:
                doc.pop("_id", None)
                entries.append(CallEntry(**doc))

            return entries
        except Exception as e:
            logger.error(f"Failed to get retry scheduled calls: {str(e)}")
            return []

    async def schedule_retry(
        self,
        entry_id: str,
        retry_at: datetime,
        retry_count: int
    ) -> bool:
        """Schedule call for retry"""
        try:
            entry = await self.get_entry(entry_id)
            if not entry:
                return False

            updates = {
                "status": CallEntryStatus.RETRY_SCHEDULED.value,
                "retry_scheduled_at": retry_at,
                "retry_count": retry_count,
                "updated_at": datetime.utcnow()
            }

            await self.update_entry(entry_id, updates)

            await self.add_state_history(
                entry_id=entry_id,
                from_state=CallEntryStatus(entry.status) if entry.status else None,
                to_state=CallEntryStatus.RETRY_SCHEDULED,
                reason=f"Scheduled retry #{retry_count} at {retry_at.isoformat()}",
                call_sid=entry.call_sid
            )

            logger.info(f"Scheduled retry for {entry_id} at {retry_at}")
            return True
        except Exception as e:
            logger.error(f"Failed to schedule retry for {entry_id}: {str(e)}")
            return False

    async def move_to_dead_letter(self, entry_id: str, reason: str) -> bool:
        """Move call entry to dead letter queue"""
        return await self.update_entry_status(
            entry_id=entry_id,
            new_status=CallEntryStatus.DEAD_LETTER,
            reason=reason
        )

    async def get_failed_entries(
        self,
        queue_id: str,
        failure_reason: Optional[FailureReason] = None,
        limit: int = 100,
        skip: int = 0
    ) -> List[CallEntry]:
        """Get failed call entries"""
        try:
            filter_query: Dict[str, Any] = {
                "queue_id": queue_id,
                "status": CallEntryStatus.FAILED.value
            }
            if failure_reason:
                filter_query["failure_reason"] = failure_reason.value

            cursor = self.collection.find(filter_query).skip(skip).limit(limit)
            documents = await cursor.to_list(length=limit)

            entries = []
            for doc in documents:
                doc.pop("_id", None)
                entries.append(CallEntry(**doc))

            return entries
        except Exception as e:
            logger.error(f"Failed to get failed entries: {str(e)}")
            return []

    async def get_dead_letter_entries(self, queue_id: str, limit: int = 100, skip: int = 0) -> List[CallEntry]:
        """Get dead letter queue entries"""
        return await self.list_entries(queue_id, CallEntryStatus.DEAD_LETTER, limit, skip)

    async def get_queue_statistics(self, queue_id: str, queue_name: str = "") -> Optional[QueueStatistics]:
        """Get queue statistics using aggregation"""
        try:
            pipeline = [
                {"$match": {"queue_id": queue_id}},
                {"$group": {
                    "_id": "$status",
                    "count": {"$sum": 1},
                    "avg_duration": {"$avg": "$call_duration"}
                }}
            ]

            cursor = self.collection.aggregate(pipeline)
            results = await cursor.to_list(length=None)

            total_calls = 0
            status_counts = {status.value: 0 for status in CallEntryStatus}
            avg_duration = None

            for result in results:
                status = result["_id"]
                count = result["count"]
                status_counts[status] = count
                total_calls += count

                if status == CallEntryStatus.SUCCESS.value and result["avg_duration"]:
                    avg_duration = result["avg_duration"]

            # Failure breakdown
            failure_pipeline = [
                {"$match": {"queue_id": queue_id, "failure_reason": {"$ne": None}}},
                {"$group": {"_id": "$failure_reason", "count": {"$sum": 1}}}
            ]

            failure_cursor = self.collection.aggregate(failure_pipeline)
            failure_results = await failure_cursor.to_list(length=None)
            failure_breakdown = {result["_id"]: result["count"] for result in failure_results}

            # Storage statistics
            storage_pipeline = [
                {"$match": {"queue_id": queue_id}},
                {"$group": {
                    "_id": None,
                    "with_recordings": {"$sum": {"$cond": [{"$ne": ["$storage.recording_s3_key", None]}, 1, 0]}},
                    "with_transcripts": {"$sum": {"$cond": ["$storage.transcript_saved", 1, 0]}},
                    "total_duration": {"$sum": {"$ifNull": ["$storage.recording_duration_seconds", 0]}}
                }}
            ]

            storage_cursor = self.collection.aggregate(storage_pipeline)
            storage_results = await storage_cursor.to_list(length=1)
            storage_stats = storage_results[0] if storage_results else {}

            # Calculate success rate
            successful = status_counts.get(CallEntryStatus.SUCCESS.value, 0)
            completed = successful + status_counts.get(CallEntryStatus.FAILED.value, 0) + status_counts.get(CallEntryStatus.DEAD_LETTER.value, 0)
            success_rate = (successful / completed * 100) if completed > 0 else 0.0

            # Estimate completion
            pending = status_counts.get(CallEntryStatus.PENDING.value, 0) + status_counts.get(CallEntryStatus.RETRY_SCHEDULED.value, 0)
            estimated_completion = None
            if pending > 0 and avg_duration:
                estimated_minutes = (pending * (avg_duration + 30)) / 60
                estimated_completion = datetime.utcnow() + timedelta(minutes=estimated_minutes)

            return QueueStatistics(
                queue_id=queue_id,
                queue_name=queue_name,
                state=QueueState.ACTIVE,  # Will be updated by caller
                total_calls=total_calls,
                pending_calls=status_counts.get(CallEntryStatus.PENDING.value, 0),
                calling_now=status_counts.get(CallEntryStatus.CALLING.value, 0),
                successful_calls=status_counts.get(CallEntryStatus.SUCCESS.value, 0),
                failed_calls=status_counts.get(CallEntryStatus.FAILED.value, 0),
                retry_scheduled_calls=status_counts.get(CallEntryStatus.RETRY_SCHEDULED.value, 0),
                dead_letter_calls=status_counts.get(CallEntryStatus.DEAD_LETTER.value, 0),
                cancelled_calls=status_counts.get(CallEntryStatus.CANCELLED.value, 0),
                failure_breakdown=failure_breakdown,
                average_call_duration=avg_duration,
                success_rate=success_rate,
                estimated_completion=estimated_completion,
                storage_stats={
                    "calls_with_recordings": storage_stats.get("with_recordings", 0),
                    "calls_with_transcripts": storage_stats.get("with_transcripts", 0),
                    "total_recording_duration_seconds": storage_stats.get("total_duration", 0)
                },
                last_updated=datetime.utcnow()
            )
        except Exception as e:
            logger.error(f"Failed to get queue statistics for {queue_id}: {str(e)}")
            return None

    async def cancel_entry(self, entry_id: str) -> bool:
        """Cancel call entry"""
        return await self.update_entry_status(
            entry_id=entry_id,
            new_status=CallEntryStatus.CANCELLED,
            reason="Cancelled by admin"
        )

    async def update_storage(
        self,
        entry_id: str,
        recording_s3_key: Optional[str] = None,
        transcript_saved: Optional[bool] = None,
        recording_metadata_saved: Optional[bool] = None,
        recording_url: Optional[str] = None,
        recording_duration_seconds: Optional[int] = None
    ) -> bool:
        """Update storage tracking fields"""
        try:
            updates: Dict[str, Any] = {}
            if recording_s3_key is not None:
                updates["storage.recording_s3_key"] = recording_s3_key
            if transcript_saved is not None:
                updates["storage.transcript_saved"] = transcript_saved
            if recording_metadata_saved is not None:
                updates["storage.recording_metadata_saved"] = recording_metadata_saved
            if recording_url is not None:
                updates["storage.recording_url"] = recording_url
            if recording_duration_seconds is not None:
                updates["storage.recording_duration_seconds"] = recording_duration_seconds

            if updates:
                return await self.update_entry(entry_id, updates)
            return False
        except Exception as e:
            logger.error(f"Failed to update storage for {entry_id}: {str(e)}")
            return False

    async def count_calling_now(self, queue_id: str) -> int:
        """Count calls currently in progress"""
        try:
            count = await self.collection.count_documents({
                "queue_id": queue_id,
                "status": CallEntryStatus.CALLING.value
            })
            return count
        except Exception as e:
            logger.error(f"Failed to count calling now for {queue_id}: {str(e)}")
            return 0

    async def promote_retry_to_pending(self, entry_id: str) -> bool:
        """Promote a retry-scheduled entry back to pending for execution"""
        return await self.update_entry_status(
            entry_id=entry_id,
            new_status=CallEntryStatus.PENDING,
            reason="Retry time reached, promoted to pending"
        )


# Singleton instances
_queue_repository: Optional[QueueRepository] = None
_call_entry_repository: Optional[CallEntryRepository] = None


def get_queue_repository() -> QueueRepository:
    """Get queue repository singleton"""
    global _queue_repository
    if _queue_repository is None:
        _queue_repository = QueueRepository()
    return _queue_repository


def get_call_entry_repository() -> CallEntryRepository:
    """Get call entry repository singleton"""
    global _call_entry_repository
    if _call_entry_repository is None:
        _call_entry_repository = CallEntryRepository()
    return _call_entry_repository
