"""
Queue Admin Router

API endpoints for managed queue administration.
"""
import logging
import uuid
from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.app.models.queue_models import (
    QueueConfig,
    QueueConfigCreate,
    QueueConfigUpdate,
    CallEntry,
    CallEntryCreate,
    CallEntryBulkCreate,
    QueueState,
    CallEntryStatus,
    FailureReason,
    QueueStatistics,
    QueueResponse,
    CallEntryResponse,
    RetryStrategy,
)
from backend.app.infrastructure.database.queue_repository import (
    get_queue_repository,
    get_call_entry_repository,
)
from backend.app.services.queue.scheduler import get_queue_scheduler

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/queue-admin", tags=["Queue Admin"])


# Response models
class SuccessResponse(BaseModel):
    """Generic success response"""
    success: bool
    message: str
    data: Optional[dict] = None


class QueueListResponse(BaseModel):
    """Queue list response"""
    queues: List[QueueResponse]
    total: int


class CallEntryListResponse(BaseModel):
    """Call entry list response"""
    entries: List[CallEntryResponse]
    total: int


class BulkCreateResponse(BaseModel):
    """Bulk create response"""
    success: bool
    created_count: int
    total_requested: int
    message: str


# ==================== Queue Configuration Management ====================

@router.post("/queues", response_model=QueueResponse, status_code=201)
async def create_queue(queue_data: QueueConfigCreate):
    """Create a new managed queue"""
    try:
        repo = get_queue_repository()

        existing = await repo.get_queue(queue_data.queue_id)
        if existing:
            raise HTTPException(status_code=409, detail=f"Queue {queue_data.queue_id} already exists")

        queue = QueueConfig(
            queue_id=queue_data.queue_id,
            name=queue_data.name,
            domain=queue_data.domain,
            description=queue_data.description,
            time_window=queue_data.time_window,
            retry_strategy=queue_data.retry_strategy or RetryStrategy(),
            max_concurrent_calls=queue_data.max_concurrent_calls,
            state=QueueState.PAUSED,
            metadata=queue_data.metadata,
        )

        success = await repo.create_queue(queue)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to create queue")

        logger.info(f"Created queue: {queue.queue_id}")
        return QueueResponse(
            queue_id=queue.queue_id,
            name=queue.name,
            domain=queue.domain,
            state=queue.state,
            description=queue.description,
            time_window=queue.time_window,
            retry_strategy=queue.retry_strategy,
            max_concurrent_calls=queue.max_concurrent_calls,
            created_at=queue.created_at,
            updated_at=queue.updated_at,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create queue: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/queues/{queue_id}", response_model=QueueResponse)
async def get_queue(queue_id: str):
    """Get queue by ID"""
    repo = get_queue_repository()
    queue = await repo.get_queue(queue_id)

    if not queue:
        raise HTTPException(status_code=404, detail=f"Queue {queue_id} not found")

    return QueueResponse(
        queue_id=queue.queue_id,
        name=queue.name,
        domain=queue.domain,
        state=queue.state,
        description=queue.description,
        time_window=queue.time_window,
        retry_strategy=queue.retry_strategy,
        max_concurrent_calls=queue.max_concurrent_calls,
        created_at=queue.created_at,
        updated_at=queue.updated_at,
        started_at=queue.started_at,
        completed_at=queue.completed_at,
    )


@router.get("/queues", response_model=QueueListResponse)
async def list_queues(
    domain: Optional[str] = Query(None, description="Filter by domain"),
    state: Optional[QueueState] = Query(None, description="Filter by state"),
    limit: int = Query(100, ge=1, le=1000),
    skip: int = Query(0, ge=0),
):
    """List all queues with optional filtering"""
    repo = get_queue_repository()
    queues = await repo.list_queues(domain=domain, state=state, limit=limit, skip=skip)

    responses = [
        QueueResponse(
            queue_id=q.queue_id,
            name=q.name,
            domain=q.domain,
            state=q.state,
            description=q.description,
            time_window=q.time_window,
            retry_strategy=q.retry_strategy,
            max_concurrent_calls=q.max_concurrent_calls,
            created_at=q.created_at,
            updated_at=q.updated_at,
            started_at=q.started_at,
            completed_at=q.completed_at,
        )
        for q in queues
    ]

    return QueueListResponse(queues=responses, total=len(responses))


@router.patch("/queues/{queue_id}", response_model=QueueResponse)
async def update_queue(queue_id: str, updates: QueueConfigUpdate):
    """Update queue configuration"""
    repo = get_queue_repository()

    queue = await repo.get_queue(queue_id)
    if not queue:
        raise HTTPException(status_code=404, detail=f"Queue {queue_id} not found")

    update_dict = updates.model_dump(exclude_unset=True)
    if not update_dict:
        return await get_queue(queue_id)

    success = await repo.update_queue(queue_id, update_dict)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update queue")

    logger.info(f"Updated queue: {queue_id}")
    return await get_queue(queue_id)


@router.delete("/queues/{queue_id}", response_model=SuccessResponse)
async def delete_queue(queue_id: str):
    """Delete queue (only if no active calls)"""
    repo = get_queue_repository()
    call_repo = get_call_entry_repository()

    queue = await repo.get_queue(queue_id)
    if not queue:
        raise HTTPException(status_code=404, detail=f"Queue {queue_id} not found")

    stats = await call_repo.get_queue_statistics(queue_id, queue.name)
    if stats and (stats.pending_calls > 0 or stats.calling_now > 0 or stats.retry_scheduled_calls > 0):
        raise HTTPException(status_code=400, detail="Cannot delete queue with pending or active calls")

    success = await repo.delete_queue(queue_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete queue")

    logger.info(f"Deleted queue: {queue_id}")
    return SuccessResponse(success=True, message=f"Queue {queue_id} deleted successfully")


# ==================== Queue Control ====================

@router.post("/queues/{queue_id}/start", response_model=SuccessResponse)
async def start_queue(queue_id: str):
    """Start/activate queue"""
    repo = get_queue_repository()
    scheduler = get_queue_scheduler()

    queue = await repo.get_queue(queue_id)
    if not queue:
        raise HTTPException(status_code=404, detail=f"Queue {queue_id} not found")

    should_be_active, reason = await scheduler.should_queue_be_active(queue_id)
    if not should_be_active and "No pending calls" not in reason:
        raise HTTPException(status_code=400, detail=f"Cannot start queue: {reason}")

    success = await repo.update_queue_state(queue_id, QueueState.ACTIVE)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to start queue")

    logger.info(f"Started queue: {queue_id}")
    return SuccessResponse(success=True, message=f"Queue {queue_id} started successfully")


@router.post("/queues/{queue_id}/pause", response_model=SuccessResponse)
async def pause_queue(queue_id: str):
    """Pause queue"""
    repo = get_queue_repository()

    queue = await repo.get_queue(queue_id)
    if not queue:
        raise HTTPException(status_code=404, detail=f"Queue {queue_id} not found")

    success = await repo.update_queue_state(queue_id, QueueState.PAUSED)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to pause queue")

    logger.info(f"Paused queue: {queue_id}")
    return SuccessResponse(success=True, message=f"Queue {queue_id} paused successfully")


@router.post("/queues/{queue_id}/cancel", response_model=SuccessResponse)
async def cancel_queue(queue_id: str):
    """Cancel queue (stop all pending calls)"""
    repo = get_queue_repository()
    call_repo = get_call_entry_repository()

    queue = await repo.get_queue(queue_id)
    if not queue:
        raise HTTPException(status_code=404, detail=f"Queue {queue_id} not found")

    success = await repo.update_queue_state(queue_id, QueueState.CANCELLED)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to cancel queue")

    pending_calls = await call_repo.list_entries(queue_id=queue_id, status=CallEntryStatus.PENDING)
    retry_calls = await call_repo.list_entries(queue_id=queue_id, status=CallEntryStatus.RETRY_SCHEDULED)

    cancelled_count = 0
    for call in pending_calls + retry_calls:
        await call_repo.cancel_entry(call.entry_id)
        cancelled_count += 1

    logger.info(f"Cancelled queue {queue_id} and {cancelled_count} calls")
    return SuccessResponse(success=True, message=f"Queue {queue_id} cancelled, {cancelled_count} calls cancelled")


# ==================== Call Entry Management ====================

@router.post("/queues/{queue_id}/calls", response_model=CallEntryResponse, status_code=201)
async def add_call_to_queue(queue_id: str, call_data: CallEntryCreate):
    """Add a single call to queue"""
    repo = get_queue_repository()
    call_repo = get_call_entry_repository()

    queue = await repo.get_queue(queue_id)
    if not queue:
        raise HTTPException(status_code=404, detail=f"Queue {queue_id} not found")

    entry = CallEntry(
        entry_id=f"entry_{uuid.uuid4().hex[:12]}",
        queue_id=queue_id,
        phone_number=call_data.phone_number,
        call_type=call_data.call_type,
        call_data=call_data.call_data,
        scheduled_for=call_data.scheduled_for,
        metadata=call_data.metadata,
    )

    success = await call_repo.create_entry(entry)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to create call entry")

    await call_repo.add_state_history(
        entry_id=entry.entry_id,
        from_state=None,
        to_state=CallEntryStatus.PENDING,
        reason="Created"
    )

    logger.info(f"Added call to queue {queue_id}: {entry.entry_id}")
    return CallEntryResponse(
        entry_id=entry.entry_id,
        queue_id=entry.queue_id,
        phone_number=entry.phone_number,
        call_type=entry.call_type,
        status=entry.status,
        retry_count=entry.retry_count,
        created_at=entry.created_at,
    )


@router.post("/queues/{queue_id}/calls/bulk", response_model=BulkCreateResponse)
async def bulk_add_calls_to_queue(queue_id: str, bulk_data: CallEntryBulkCreate):
    """Bulk add calls to queue"""
    repo = get_queue_repository()
    call_repo = get_call_entry_repository()

    queue = await repo.get_queue(queue_id)
    if not queue:
        raise HTTPException(status_code=404, detail=f"Queue {queue_id} not found")

    entries = []
    for call_data in bulk_data.calls:
        entry = CallEntry(
            entry_id=f"entry_{uuid.uuid4().hex[:12]}",
            queue_id=queue_id,
            phone_number=call_data.phone_number,
            call_type=call_data.call_type,
            call_data=call_data.call_data,
            scheduled_for=call_data.scheduled_for,
            metadata=call_data.metadata,
        )
        entries.append(entry)

    created_count = await call_repo.bulk_create_entries(entries)

    logger.info(f"Bulk added {created_count}/{len(bulk_data.calls)} calls to queue {queue_id}")
    return BulkCreateResponse(
        success=True,
        created_count=created_count,
        total_requested=len(bulk_data.calls),
        message=f"Created {created_count} out of {len(bulk_data.calls)} calls"
    )


@router.get("/queues/{queue_id}/calls", response_model=CallEntryListResponse)
async def list_queue_calls(
    queue_id: str,
    status: Optional[CallEntryStatus] = Query(None, description="Filter by status"),
    limit: int = Query(100, ge=1, le=1000),
    skip: int = Query(0, ge=0),
):
    """List all calls in queue"""
    repo = get_queue_repository()
    call_repo = get_call_entry_repository()

    queue = await repo.get_queue(queue_id)
    if not queue:
        raise HTTPException(status_code=404, detail=f"Queue {queue_id} not found")

    entries = await call_repo.list_entries(queue_id=queue_id, status=status, limit=limit, skip=skip)

    responses = [
        CallEntryResponse(
            entry_id=e.entry_id,
            queue_id=e.queue_id,
            phone_number=e.phone_number,
            call_type=e.call_type,
            status=e.status,
            retry_count=e.retry_count,
            failure_reason=e.failure_reason,
            failure_details=e.failure_details,
            call_sid=e.call_sid,
            call_duration=e.call_duration,
            scheduled_for=e.scheduled_for,
            retry_scheduled_at=e.retry_scheduled_at,
            started_at=e.started_at,
            completed_at=e.completed_at,
            created_at=e.created_at,
        )
        for e in entries
    ]

    return CallEntryListResponse(entries=responses, total=len(responses))


@router.get("/queues/{queue_id}/calls/{entry_id}", response_model=CallEntryResponse)
async def get_call_entry(queue_id: str, entry_id: str):
    """Get specific call entry"""
    call_repo = get_call_entry_repository()

    entry = await call_repo.get_entry(entry_id)
    if not entry or entry.queue_id != queue_id:
        raise HTTPException(status_code=404, detail=f"Call entry {entry_id} not found in queue {queue_id}")

    return CallEntryResponse(
        entry_id=entry.entry_id,
        queue_id=entry.queue_id,
        phone_number=entry.phone_number,
        call_type=entry.call_type,
        status=entry.status,
        retry_count=entry.retry_count,
        failure_reason=entry.failure_reason,
        failure_details=entry.failure_details,
        call_sid=entry.call_sid,
        call_duration=entry.call_duration,
        scheduled_for=entry.scheduled_for,
        retry_scheduled_at=entry.retry_scheduled_at,
        started_at=entry.started_at,
        completed_at=entry.completed_at,
        created_at=entry.created_at,
    )


@router.post("/queues/{queue_id}/calls/{entry_id}/retry", response_model=SuccessResponse)
async def manual_retry_call(queue_id: str, entry_id: str):
    """Manually retry a failed call"""
    call_repo = get_call_entry_repository()

    entry = await call_repo.get_entry(entry_id)
    if not entry or entry.queue_id != queue_id:
        raise HTTPException(status_code=404, detail=f"Call entry {entry_id} not found in queue {queue_id}")

    if entry.status not in [CallEntryStatus.FAILED, CallEntryStatus.DEAD_LETTER]:
        raise HTTPException(status_code=400, detail=f"Can only retry failed or dead letter calls")

    success = await call_repo.update_entry_status(
        entry_id=entry_id,
        new_status=CallEntryStatus.PENDING,
        reason="Manual retry requested"
    )

    if not success:
        raise HTTPException(status_code=500, detail="Failed to retry call")

    logger.info(f"Manual retry requested for call {entry_id}")
    return SuccessResponse(success=True, message=f"Call {entry_id} scheduled for retry")


@router.delete("/queues/{queue_id}/calls/{entry_id}", response_model=SuccessResponse)
async def cancel_call(queue_id: str, entry_id: str):
    """Cancel specific call"""
    call_repo = get_call_entry_repository()

    entry = await call_repo.get_entry(entry_id)
    if not entry or entry.queue_id != queue_id:
        raise HTTPException(status_code=404, detail=f"Call entry {entry_id} not found in queue {queue_id}")

    if entry.status not in [CallEntryStatus.PENDING, CallEntryStatus.RETRY_SCHEDULED]:
        raise HTTPException(status_code=400, detail=f"Can only cancel pending or retry-scheduled calls")

    success = await call_repo.cancel_entry(entry_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to cancel call")

    logger.info(f"Cancelled call {entry_id}")
    return SuccessResponse(success=True, message=f"Call {entry_id} cancelled")


# ==================== Statistics & Monitoring ====================

@router.get("/queues/{queue_id}/stats", response_model=QueueStatistics)
async def get_queue_statistics(queue_id: str):
    """Get queue statistics"""
    repo = get_queue_repository()
    call_repo = get_call_entry_repository()

    queue = await repo.get_queue(queue_id)
    if not queue:
        raise HTTPException(status_code=404, detail=f"Queue {queue_id} not found")

    stats = await call_repo.get_queue_statistics(queue_id, queue.name)
    if not stats:
        raise HTTPException(status_code=500, detail="Failed to get statistics")

    stats.state = queue.state
    return stats


@router.get("/queues/{queue_id}/calls/failed", response_model=CallEntryListResponse)
async def get_failed_calls(
    queue_id: str,
    failure_reason: Optional[FailureReason] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
):
    """Get all failed calls"""
    call_repo = get_call_entry_repository()

    entries = await call_repo.get_failed_entries(queue_id, failure_reason, limit)

    responses = [
        CallEntryResponse(
            entry_id=e.entry_id,
            queue_id=e.queue_id,
            phone_number=e.phone_number,
            call_type=e.call_type,
            status=e.status,
            retry_count=e.retry_count,
            failure_reason=e.failure_reason,
            failure_details=e.failure_details,
            call_sid=e.call_sid,
            call_duration=e.call_duration,
            scheduled_for=e.scheduled_for,
            retry_scheduled_at=e.retry_scheduled_at,
            started_at=e.started_at,
            completed_at=e.completed_at,
            created_at=e.created_at,
        )
        for e in entries
    ]

    return CallEntryListResponse(entries=responses, total=len(responses))


@router.get("/queues/{queue_id}/calls/dead-letter", response_model=CallEntryListResponse)
async def get_dead_letter_calls(queue_id: str, limit: int = Query(100, ge=1, le=1000)):
    """Get all calls in dead letter queue"""
    call_repo = get_call_entry_repository()

    entries = await call_repo.get_dead_letter_entries(queue_id, limit)

    responses = [
        CallEntryResponse(
            entry_id=e.entry_id,
            queue_id=e.queue_id,
            phone_number=e.phone_number,
            call_type=e.call_type,
            status=e.status,
            retry_count=e.retry_count,
            failure_reason=e.failure_reason,
            failure_details=e.failure_details,
            call_sid=e.call_sid,
            call_duration=e.call_duration,
            scheduled_for=e.scheduled_for,
            retry_scheduled_at=e.retry_scheduled_at,
            started_at=e.started_at,
            completed_at=e.completed_at,
            created_at=e.created_at,
        )
        for e in entries
    ]

    return CallEntryListResponse(entries=responses, total=len(responses))


# ==================== Bulk Operations ====================

@router.post("/queues/{queue_id}/retry-all-failed", response_model=SuccessResponse)
async def retry_all_failed_calls(queue_id: str):
    """Retry all failed calls in queue"""
    call_repo = get_call_entry_repository()

    failed_calls = await call_repo.get_failed_entries(queue_id, limit=1000)

    retried_count = 0
    for entry in failed_calls:
        success = await call_repo.update_entry_status(
            entry_id=entry.entry_id,
            new_status=CallEntryStatus.PENDING,
            reason="Bulk retry all failed calls"
        )
        if success:
            retried_count += 1

    logger.info(f"Bulk retried {retried_count}/{len(failed_calls)} failed calls in queue {queue_id}")
    return SuccessResponse(
        success=True,
        message=f"Retried {retried_count} failed calls",
        data={"retried_count": retried_count, "total_failed": len(failed_calls)}
    )


@router.post("/queues/{queue_id}/move-all-to-dlq", response_model=SuccessResponse)
async def move_all_failed_to_dlq(queue_id: str):
    """Move all failed calls to dead letter queue"""
    call_repo = get_call_entry_repository()

    failed_calls = await call_repo.get_failed_entries(queue_id, limit=1000)

    moved_count = 0
    for entry in failed_calls:
        success = await call_repo.move_to_dead_letter(entry.entry_id, "Bulk move to DLQ by admin")
        if success:
            moved_count += 1

    logger.info(f"Bulk moved {moved_count}/{len(failed_calls)} failed calls to DLQ in queue {queue_id}")
    return SuccessResponse(
        success=True,
        message=f"Moved {moved_count} failed calls to dead letter queue",
        data={"moved_count": moved_count, "total_failed": len(failed_calls)}
    )
