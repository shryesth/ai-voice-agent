"""
CallQueue API endpoints.

Provides CRUD operations and state management for call queues.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from bson import ObjectId

from backend.app.models.enums import QueueState, QueueMode, UserRole
from backend.app.models.call_queue import CallQueue
from backend.app.models.recipient import Recipient
from backend.app.services.call_queue_service import call_queue_service
from backend.app.schemas.call_queue import (
    CallQueueCreate,
    CallQueueUpdate,
    CallQueueResponse,
    CallQueueListResponse,
    CallQueueStatusResponse,
    CallQueueStateChangeResponse,
    CallQueueSyncResponse,
    QueueStatsSchema,
    queue_to_response,
)
from backend.app.api.v1.auth import get_current_user, require_admin

logger = logging.getLogger(__name__)

router = APIRouter(tags=["queues"])


@router.post(
    "/geographies/{geography_id}/queues",
    response_model=CallQueueResponse,
    status_code=status.HTTP_201_CREATED,
    name="create_queue"
)
async def create_queue(
    geography_id: str,
    data: CallQueueCreate,
    current_user=Depends(require_admin),
):
    """
    Create a new call queue in a geography.

    Admin only.
    """
    try:
        queue = await call_queue_service.create_queue(
            geography_id=geography_id,
            name=data.name,
            description=data.description,
            mode=data.mode,
            call_type=data.call_type,
            default_flow_template_id=data.default_flow_template_id,
            default_language=data.default_language,
            max_concurrent_calls=data.max_concurrent_calls,
            time_windows=[tw.model_dump() for tw in data.time_windows],
            retry_strategy=data.retry_strategy.model_dump(),
            clarity_sync=data.clarity_sync.model_dump(),
        )
        return queue_to_response(queue)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/queues", response_model=CallQueueListResponse)
async def list_queues(
    geography_id: Optional[str] = Query(default=None),
    state: Optional[QueueState] = Query(default=None),
    mode: Optional[QueueMode] = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    current_user=Depends(get_current_user),
):
    """
    List call queues with optional filters.
    """
    queues = await call_queue_service.list_queues(
        geography_id=geography_id,
        state=state,
        mode=mode,
        skip=skip,
        limit=limit,
    )

    # Get total count
    total = len(queues)  # TODO: Add proper count query

    return CallQueueListResponse(
        items=[queue_to_response(q) for q in queues],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/queues/{queue_id}", response_model=CallQueueResponse)
async def get_queue(
    queue_id: str,
    current_user=Depends(get_current_user),
):
    """
    Get a call queue by ID.
    """
    queue = await call_queue_service.get_queue_by_id(queue_id)
    if not queue:
        raise HTTPException(status_code=404, detail="Queue not found")
    return queue_to_response(queue)


@router.patch("/{queue_id}", response_model=CallQueueResponse)
async def update_queue(
    queue_id: str,
    data: CallQueueUpdate,
    current_user=Depends(require_admin),
):
    """
    Update a call queue.

    Only allowed in DRAFT or PAUSED states.
    Admin only.
    """
    try:
        updates = data.model_dump(exclude_unset=True)
        queue = await call_queue_service.update_queue(queue_id, **updates)
        return queue_to_response(queue)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{queue_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_queue(
    queue_id: str,
    hard_delete: bool = Query(default=False),
    current_user=Depends(require_admin),
):
    """
    Delete a call queue (soft delete by default).

    Admin only.
    """
    try:
        await call_queue_service.delete_queue(queue_id, hard_delete=hard_delete)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# State transition endpoints
@router.post("/{queue_id}/start", response_model=CallQueueStateChangeResponse)
async def start_queue(
    queue_id: str,
    current_user=Depends(require_admin),
):
    """
    Start a queue (DRAFT -> ACTIVE).

    Admin only.
    """
    queue = await call_queue_service.get_queue_by_id(queue_id)
    if not queue:
        raise HTTPException(status_code=404, detail="Queue not found")

    previous_state = queue.state.value

    try:
        queue = await call_queue_service.start_queue(queue_id)
        return CallQueueStateChangeResponse(
            id=str(queue.id),
            name=queue.name,
            previous_state=previous_state,
            new_state=queue.state.value,
            changed_at=datetime.now(timezone.utc),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{queue_id}/pause", response_model=CallQueueStateChangeResponse)
async def pause_queue(
    queue_id: str,
    current_user=Depends(require_admin),
):
    """
    Pause a queue (ACTIVE -> PAUSED).

    Admin only.
    """
    queue = await call_queue_service.get_queue_by_id(queue_id)
    if not queue:
        raise HTTPException(status_code=404, detail="Queue not found")

    previous_state = queue.state.value

    try:
        queue = await call_queue_service.pause_queue(queue_id)
        return CallQueueStateChangeResponse(
            id=str(queue.id),
            name=queue.name,
            previous_state=previous_state,
            new_state=queue.state.value,
            changed_at=datetime.now(timezone.utc),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{queue_id}/resume", response_model=CallQueueStateChangeResponse)
async def resume_queue(
    queue_id: str,
    current_user=Depends(require_admin),
):
    """
    Resume a paused queue (PAUSED -> ACTIVE).

    Admin only.
    """
    queue = await call_queue_service.get_queue_by_id(queue_id)
    if not queue:
        raise HTTPException(status_code=404, detail="Queue not found")

    previous_state = queue.state.value

    try:
        queue = await call_queue_service.resume_queue(queue_id)
        return CallQueueStateChangeResponse(
            id=str(queue.id),
            name=queue.name,
            previous_state=previous_state,
            new_state=queue.state.value,
            changed_at=datetime.now(timezone.utc),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{queue_id}/cancel", response_model=CallQueueStateChangeResponse)
async def cancel_queue(
    queue_id: str,
    current_user=Depends(require_admin),
):
    """
    Cancel a queue (moves pending to DLQ).

    Admin only.
    """
    queue = await call_queue_service.get_queue_by_id(queue_id)
    if not queue:
        raise HTTPException(status_code=404, detail="Queue not found")

    previous_state = queue.state.value

    try:
        queue = await call_queue_service.cancel_queue(queue_id)
        return CallQueueStateChangeResponse(
            id=str(queue.id),
            name=queue.name,
            previous_state=previous_state,
            new_state=queue.state.value,
            changed_at=datetime.now(timezone.utc),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{queue_id}/status", response_model=CallQueueStatusResponse)
async def get_queue_status(
    queue_id: str,
    current_user=Depends(get_current_user),
):
    """
    Get detailed queue status with statistics.
    """
    try:
        status_data = await call_queue_service.get_queue_status(queue_id)
        return CallQueueStatusResponse(**status_data)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{queue_id}/refresh-stats", response_model=CallQueueResponse)
async def refresh_queue_stats(
    queue_id: str,
    current_user=Depends(require_admin),
):
    """
    Refresh queue statistics from recipient data.

    Admin only.
    """
    try:
        queue = await call_queue_service.refresh_queue_stats(queue_id)
        return queue_to_response(queue)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{queue_id}/sync-clarity", response_model=CallQueueSyncResponse)
async def sync_queue_from_clarity(
    queue_id: str,
    max_count: Optional[int] = Query(
        default=None,
        ge=1,
        le=1000,
        description="Override max recipients to sync",
    ),
    current_user=Depends(require_admin),
):
    """
    Manually trigger Clarity sync for a queue.

    This endpoint allows immediate sync regardless of sync_interval_minutes.
    Useful for testing or when urgent sync is needed.

    Admin only.
    """
    queue = await call_queue_service.get_queue_by_id(queue_id)
    if not queue:
        raise HTTPException(status_code=404, detail="Queue not found")

    # Verify queue is configured for Clarity sync
    if not queue.clarity_sync.enabled:
        raise HTTPException(
            status_code=400,
            detail="Clarity sync is not enabled for this queue"
        )

    # Verify queue is ACTIVE or PAUSED
    if queue.state not in (QueueState.ACTIVE, QueueState.PAUSED):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot sync queue in {queue.state} state"
        )

    # Trigger sync task
    from backend.app.tasks.clarity_sync import sync_clarity_subjects
    task = sync_clarity_subjects.delay(queue_id, max_count)

    # Wait for result (with timeout)
    try:
        result_count = task.get(timeout=30)  # 30 second timeout

        # Refresh queue to get updated sync metadata
        queue = await call_queue_service.get_queue_by_id(queue_id)

        return CallQueueSyncResponse(
            queue_id=str(queue.id),
            queue_name=queue.name,
            synced_count=result_count,
            last_sync_at=queue.clarity_sync.last_sync_at,
            last_sync_count=queue.clarity_sync.last_sync_count,
            task_id=task.id,
        )
    except Exception as e:
        logger.error(f"Clarity sync failed for queue {queue_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Sync failed: {str(e)}"
        )
