"""
Clarity Integration Router

API endpoints for managing Clarity-synced queues.
"""

import logging
import uuid
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.app.models.queue_models import (
    QueueConfig,
    QueueState,
    TimeWindow,
    RetryStrategy,
)
from backend.app.infrastructure.database.queue_repository import (
    get_queue_repository,
    get_call_entry_repository,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/clarity",
    tags=["Clarity Integration"],
)


# Request/Response Models


class ClarityQueueCreate(BaseModel):
    """Request to create a Clarity-synced queue"""

    name: str = Field(..., description="Queue name (e.g., 'Haiti Vaccinations')")
    description: Optional[str] = None

    # Clarity API Configuration
    clarity_api_url: str = Field(..., description="Clarity API base URL")
    clarity_api_key: str = Field(..., description="Clarity API key/token")
    clarity_environment: str = Field(
        ..., description="Environment name: staging, haiti, honduras"
    )

    # Sync Configuration
    sync_interval_seconds: int = Field(
        default=300, description="Sync interval (default 5 min)"
    )
    date_from: Optional[str] = Field(
        None, description="Filter: start date (YYYY-MM-DD)"
    )
    date_to: Optional[str] = Field(None, description="Filter: end date (YYYY-MM-DD)")
    default_language: str = Field(default="en", description="Default language for calls")

    # Storage Configuration
    storage_prefix: Optional[str] = Field(
        None, description="Custom S3 prefix (defaults to queue_id)"
    )

    # Queue Settings
    time_window: Optional[TimeWindow] = None
    retry_strategy: Optional[RetryStrategy] = None
    max_concurrent_calls: int = Field(default=5, ge=1, le=50)
    start_immediately: bool = Field(default=False)

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "Haiti Vaccination Verifications",
                "description": "Automated vaccination verification calls for Haiti",
                "clarity_api_url": "https://clarity.hti.shifo.org/api/v1",
                "clarity_api_key": "secret-api-key-here",
                "clarity_environment": "haiti",
                "sync_interval_seconds": 300,
                "date_from": "2025-01-01",
                "date_to": None,
                "default_language": "ht",
                "time_window": {
                    "start_time_utc": "13:00",
                    "end_time_utc": "21:00",
                    "days_of_week": [0, 1, 2, 3, 4],
                },
                "max_concurrent_calls": 5,
                "start_immediately": True,
            }
        }
    }


class ClarityQueueUpdate(BaseModel):
    """Request to update a Clarity queue"""

    name: Optional[str] = None
    description: Optional[str] = None
    sync_interval_seconds: Optional[int] = Field(None, ge=60)
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    default_language: Optional[str] = None
    storage_prefix: Optional[str] = None
    time_window: Optional[TimeWindow] = None
    max_concurrent_calls: Optional[int] = Field(None, ge=1, le=50)


class ClarityQueueResponse(BaseModel):
    """Response for Clarity queue operations"""

    queue_id: str
    name: str
    state: str
    clarity_environment: str
    total_synced_items: int
    last_sync_at: Optional[str]
    last_sync_status: Optional[str]
    message: str


class SyncTriggerResponse(BaseModel):
    """Response for manual sync trigger"""

    success: bool
    queue_id: str
    created: int
    updated: int
    skipped: int
    errors: int
    message: str


class SyncStatusResponse(BaseModel):
    """Response for sync status"""

    queue_id: str
    clarity_environment: str
    last_sync_at: Optional[str]
    last_sync_status: Optional[str]
    last_sync_error: Optional[str]
    total_synced_items: int
    sync_interval_seconds: int


# Endpoints


@router.post("/queues", response_model=ClarityQueueResponse, status_code=201)
async def create_clarity_queue(request: ClarityQueueCreate):
    """
    Create a new Clarity-synced queue.

    This creates a managed queue that automatically syncs pending
    verifications from the specified Clarity environment.
    """
    repo = get_queue_repository()

    # Generate queue ID
    queue_id = f"clarity_{request.clarity_environment}_{uuid.uuid4().hex[:8]}"

    # Build Clarity metadata
    clarity_metadata = {
        "queue_type": "clarity",
        "clarity_api_url": request.clarity_api_url,
        "clarity_api_key": request.clarity_api_key,
        "clarity_environment": request.clarity_environment,
        "sync_interval_seconds": request.sync_interval_seconds,
        "date_from": request.date_from,
        "date_to": request.date_to,
        "default_language": request.default_language,
        "storage_prefix": request.storage_prefix or queue_id,
        "last_sync_at": None,
        "last_sync_status": None,
        "last_sync_error": None,
        "total_synced_items": 0,
    }

    # Create queue config
    initial_state = QueueState.ACTIVE if request.start_immediately else QueueState.PAUSED

    queue = QueueConfig(
        queue_id=queue_id,
        name=request.name,
        domain="vaccination",
        description=request.description,
        time_window=request.time_window,
        retry_strategy=request.retry_strategy or RetryStrategy(),
        max_concurrent_calls=request.max_concurrent_calls,
        state=initial_state,
        metadata=clarity_metadata,
    )

    success = await repo.create_queue(queue)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to create queue")

    logger.info(
        f"Created Clarity queue: {queue_id} for environment {request.clarity_environment}"
    )

    return ClarityQueueResponse(
        queue_id=queue_id,
        name=request.name,
        state=initial_state.value,
        clarity_environment=request.clarity_environment,
        total_synced_items=0,
        last_sync_at=None,
        last_sync_status=None,
        message=f"Clarity queue created for {request.clarity_environment}. "
        + (
            "Sync will begin automatically."
            if request.start_immediately
            else "Queue is paused. Start it to begin syncing."
        ),
    )


@router.get("/queues", response_model=List[ClarityQueueResponse])
async def list_clarity_queues(
    environment: Optional[str] = Query(None, description="Filter by environment"),
    state: Optional[str] = Query(None, description="Filter by state"),
):
    """List all Clarity-synced queues"""
    repo = get_queue_repository()

    # Parse state if provided
    queue_state = None
    if state:
        try:
            queue_state = QueueState(state)
        except ValueError:
            raise HTTPException(
                status_code=400, detail=f"Invalid state: {state}"
            )

    queues = await repo.list_queues(state=queue_state)

    # Filter to Clarity queues
    clarity_queues = [q for q in queues if q.metadata.get("queue_type") == "clarity"]

    # Filter by environment if specified
    if environment:
        clarity_queues = [
            q
            for q in clarity_queues
            if q.metadata.get("clarity_environment") == environment
        ]

    return [
        ClarityQueueResponse(
            queue_id=q.queue_id,
            name=q.name,
            state=q.state if isinstance(q.state, str) else q.state.value,
            clarity_environment=q.metadata.get("clarity_environment", "unknown"),
            total_synced_items=q.metadata.get("total_synced_items", 0),
            last_sync_at=q.metadata.get("last_sync_at"),
            last_sync_status=q.metadata.get("last_sync_status"),
            message="",
        )
        for q in clarity_queues
    ]


@router.get("/queues/{queue_id}", response_model=ClarityQueueResponse)
async def get_clarity_queue(queue_id: str):
    """Get a Clarity queue by ID"""
    repo = get_queue_repository()

    queue = await repo.get_queue(queue_id)
    if not queue:
        raise HTTPException(status_code=404, detail=f"Queue {queue_id} not found")

    if queue.metadata.get("queue_type") != "clarity":
        raise HTTPException(status_code=400, detail="Queue is not a Clarity queue")

    return ClarityQueueResponse(
        queue_id=queue.queue_id,
        name=queue.name,
        state=queue.state if isinstance(queue.state, str) else queue.state.value,
        clarity_environment=queue.metadata.get("clarity_environment", "unknown"),
        total_synced_items=queue.metadata.get("total_synced_items", 0),
        last_sync_at=queue.metadata.get("last_sync_at"),
        last_sync_status=queue.metadata.get("last_sync_status"),
        message="",
    )


@router.post("/queues/{queue_id}/sync", response_model=SyncTriggerResponse)
async def trigger_sync(queue_id: str):
    """
    Manually trigger a sync for a Clarity queue.

    Fetches pending verifications from Clarity and creates call entries.
    """
    repo = get_queue_repository()
    call_entry_repo = get_call_entry_repository()

    queue = await repo.get_queue(queue_id)
    if not queue:
        raise HTTPException(status_code=404, detail=f"Queue {queue_id} not found")

    if queue.metadata.get("queue_type") != "clarity":
        raise HTTPException(status_code=400, detail="Queue is not a Clarity queue")

    # Import sync service here to avoid circular imports
    from backend.app.integrations.clarity.sync_service import ClaritySyncService

    sync_service = ClaritySyncService(repo, call_entry_repo)

    try:
        stats = await sync_service.sync_queue_from_clarity(queue)

        return SyncTriggerResponse(
            success=True,
            queue_id=queue_id,
            created=stats["created"],
            updated=stats["updated"],
            skipped=stats["skipped"],
            errors=stats["errors"],
            message=f"Sync complete: {stats['created']} new entries created",
        )

    except Exception as e:
        logger.error(f"Sync failed for queue {queue_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")


@router.get("/queues/{queue_id}/sync-status", response_model=SyncStatusResponse)
async def get_sync_status(queue_id: str):
    """Get sync status for a Clarity queue"""
    repo = get_queue_repository()

    queue = await repo.get_queue(queue_id)
    if not queue:
        raise HTTPException(status_code=404, detail=f"Queue {queue_id} not found")

    if queue.metadata.get("queue_type") != "clarity":
        raise HTTPException(status_code=400, detail="Queue is not a Clarity queue")

    return SyncStatusResponse(
        queue_id=queue_id,
        clarity_environment=queue.metadata.get("clarity_environment", "unknown"),
        last_sync_at=queue.metadata.get("last_sync_at"),
        last_sync_status=queue.metadata.get("last_sync_status"),
        last_sync_error=queue.metadata.get("last_sync_error"),
        total_synced_items=queue.metadata.get("total_synced_items", 0),
        sync_interval_seconds=queue.metadata.get("sync_interval_seconds", 300),
    )


@router.patch("/queues/{queue_id}")
async def update_clarity_queue(queue_id: str, updates: ClarityQueueUpdate):
    """
    Update Clarity queue configuration.

    Allows updating sync settings, time windows, etc.
    Note: API key changes require queue recreation for security.
    """
    repo = get_queue_repository()

    queue = await repo.get_queue(queue_id)
    if not queue:
        raise HTTPException(status_code=404, detail=f"Queue {queue_id} not found")

    if queue.metadata.get("queue_type") != "clarity":
        raise HTTPException(status_code=400, detail="Queue is not a Clarity queue")

    # Build update dict
    update_dict = {}

    # Direct queue fields
    if updates.name is not None:
        update_dict["name"] = updates.name
    if updates.description is not None:
        update_dict["description"] = updates.description
    if updates.time_window is not None:
        update_dict["time_window"] = updates.time_window.model_dump()
    if updates.max_concurrent_calls is not None:
        update_dict["max_concurrent_calls"] = updates.max_concurrent_calls

    # Metadata fields
    if updates.sync_interval_seconds is not None:
        update_dict["metadata.sync_interval_seconds"] = updates.sync_interval_seconds
    if updates.date_from is not None:
        update_dict["metadata.date_from"] = updates.date_from
    if updates.date_to is not None:
        update_dict["metadata.date_to"] = updates.date_to
    if updates.default_language is not None:
        update_dict["metadata.default_language"] = updates.default_language
    if updates.storage_prefix is not None:
        update_dict["metadata.storage_prefix"] = updates.storage_prefix

    if update_dict:
        success = await repo.update_queue(queue_id, update_dict)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to update queue")

    return {"success": True, "message": "Queue updated", "queue_id": queue_id}


@router.post("/queues/{queue_id}/start")
async def start_clarity_queue(queue_id: str):
    """Start a Clarity queue (set to ACTIVE state)"""
    repo = get_queue_repository()

    queue = await repo.get_queue(queue_id)
    if not queue:
        raise HTTPException(status_code=404, detail=f"Queue {queue_id} not found")

    if queue.metadata.get("queue_type") != "clarity":
        raise HTTPException(status_code=400, detail="Queue is not a Clarity queue")

    success = await repo.update_queue_state(queue_id, QueueState.ACTIVE)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to start queue")

    return {"success": True, "message": "Queue started", "queue_id": queue_id}


@router.post("/queues/{queue_id}/pause")
async def pause_clarity_queue(queue_id: str):
    """Pause a Clarity queue (set to PAUSED state)"""
    repo = get_queue_repository()

    queue = await repo.get_queue(queue_id)
    if not queue:
        raise HTTPException(status_code=404, detail=f"Queue {queue_id} not found")

    if queue.metadata.get("queue_type") != "clarity":
        raise HTTPException(status_code=400, detail="Queue is not a Clarity queue")

    success = await repo.update_queue_state(queue_id, QueueState.PAUSED)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to pause queue")

    return {"success": True, "message": "Queue paused", "queue_id": queue_id}


@router.delete("/queues/{queue_id}")
async def delete_clarity_queue(queue_id: str, delete_entries: bool = Query(False)):
    """
    Delete a Clarity queue.

    Args:
        queue_id: Queue ID to delete
        delete_entries: If True, also delete all call entries for this queue
    """
    repo = get_queue_repository()
    call_entry_repo = get_call_entry_repository()

    queue = await repo.get_queue(queue_id)
    if not queue:
        raise HTTPException(status_code=404, detail=f"Queue {queue_id} not found")

    if queue.metadata.get("queue_type") != "clarity":
        raise HTTPException(status_code=400, detail="Queue is not a Clarity queue")

    # Check for active calls
    active_count = await call_entry_repo.count_calling_now(queue_id)
    if active_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete queue with {active_count} active calls. Pause first.",
        )

    # Delete entries if requested
    entries_deleted = 0
    if delete_entries:
        # Delete all entries for this queue
        result = await call_entry_repo.collection.delete_many({"queue_id": queue_id})
        entries_deleted = result.deleted_count

    # Delete queue
    success = await repo.delete_queue(queue_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete queue")

    return {
        "success": True,
        "message": "Queue deleted",
        "queue_id": queue_id,
        "entries_deleted": entries_deleted,
    }
