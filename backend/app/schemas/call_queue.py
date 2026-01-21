"""
Pydantic schemas for CallQueue API endpoints.
"""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List, Dict, Any

from backend.app.models.enums import (
    CallType,
    QueueMode,
    QueueState,
)


class TimeWindowSchema(BaseModel):
    """Time window for queue processing."""

    start_time_utc: str = Field(
        ...,
        pattern=r"^([01]\d|2[0-3]):([0-5]\d)$",
        description="Start time in UTC (HH:MM format)",
    )
    end_time_utc: str = Field(
        ...,
        pattern=r"^([01]\d|2[0-3]):([0-5]\d)$",
        description="End time in UTC (HH:MM format)",
    )
    days_of_week: List[int] = Field(
        default=[0, 1, 2, 3, 4],
        description="Days of week (0=Monday, 6=Sunday)",
    )


class RetryStrategySchema(BaseModel):
    """Retry configuration for failed calls."""

    max_retries: int = Field(default=3, ge=0, le=10)
    exponential_backoff: bool = Field(default=True)
    no_answer_delay: int = Field(default=1800, description="30 min")
    busy_delay: int = Field(default=3600, description="1 hour")
    voicemail_delay: int = Field(default=7200, description="2 hours")
    timeout_delay: int = Field(default=1800, description="30 min")
    person_not_available_delay: int = Field(default=7200, description="2 hours")
    short_duration_delay: int = Field(default=3600, description="1 hour")
    failed_delay: int = Field(default=900, description="15 min")


class ClaritySyncConfigSchema(BaseModel):
    """Configuration for Clarity sync."""

    enabled: bool = Field(default=False)
    sync_interval_minutes: int = Field(default=15, ge=1, le=60)
    max_per_sync: int = Field(default=100, ge=1, le=1000)
    event_type_filter: List[str] = Field(default_factory=list)


class QueueStatsSchema(BaseModel):
    """Queue statistics."""

    total_recipients: int = 0
    pending_count: int = 0
    calling_count: int = 0
    retrying_count: int = 0
    completed_count: int = 0
    failed_count: int = 0
    not_reachable_count: int = 0
    skipped_count: int = 0
    dlq_count: int = 0
    total_calls_made: int = 0
    successful_verifications: int = 0
    urgent_flagged_count: int = 0
    avg_call_duration_seconds: Optional[float] = None
    last_call_at: Optional[datetime] = None


# Request schemas
class CallQueueCreate(BaseModel):
    """Request schema for creating a call queue."""

    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=1000)
    mode: QueueMode = Field(default=QueueMode.BATCH)
    call_type: CallType = Field(default=CallType.PATIENT_FEEDBACK)
    default_flow_template_id: Optional[str] = None
    default_language: str = Field(default="en")
    max_concurrent_calls: int = Field(default=10, ge=1, le=100)
    time_windows: List[TimeWindowSchema] = Field(default_factory=list)
    retry_strategy: RetryStrategySchema = Field(default_factory=RetryStrategySchema)
    clarity_sync: ClaritySyncConfigSchema = Field(default_factory=ClaritySyncConfigSchema)


class CallQueueUpdate(BaseModel):
    """Request schema for updating a call queue."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=1000)
    default_language: Optional[str] = None
    max_concurrent_calls: Optional[int] = Field(default=None, ge=1, le=100)
    time_windows: Optional[List[TimeWindowSchema]] = None
    retry_strategy: Optional[RetryStrategySchema] = None
    clarity_sync: Optional[ClaritySyncConfigSchema] = None


# Response schemas
class CallQueueResponse(BaseModel):
    """Response schema for a call queue."""

    id: str
    name: str
    description: Optional[str]
    geography_id: str
    mode: str
    state: str
    call_type: str
    default_flow_template_id: Optional[str]
    default_language: str
    max_concurrent_calls: int
    time_windows: List[TimeWindowSchema]
    retry_strategy: RetryStrategySchema
    clarity_sync: ClaritySyncConfigSchema
    stats: QueueStatsSchema
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True


class CallQueueListResponse(BaseModel):
    """Response schema for listing call queues."""

    items: List[CallQueueResponse]
    total: int
    skip: int
    limit: int


class CallQueueStatusResponse(BaseModel):
    """Response schema for queue status."""

    queue_id: str
    name: str
    state: str
    mode: str
    total_recipients: int
    status_counts: Dict[str, int]
    progress_percent: float
    stats: QueueStatsSchema
    started_at: Optional[str]
    completed_at: Optional[str]


class CallQueueStateChangeResponse(BaseModel):
    """Response schema for state change operations."""

    id: str
    name: str
    previous_state: str
    new_state: str
    changed_at: datetime


class CallQueueSyncResponse(BaseModel):
    """Response schema for manual Clarity sync."""

    queue_id: str
    queue_name: str
    synced_count: int = Field(
        ...,
        description="Number of new recipients synced from Clarity"
    )
    last_sync_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp of this sync"
    )
    last_sync_count: int = Field(
        default=0,
        description="Total count from last sync"
    )
    task_id: str = Field(
        ...,
        description="Celery task ID for tracking"
    )


def queue_to_response(queue, include_stats: bool = True) -> CallQueueResponse:
    """Convert CallQueue model to response schema."""
    return CallQueueResponse(
        id=str(queue.id),
        name=queue.name,
        description=queue.description,
        geography_id=str(queue.geography_id.id) if hasattr(queue.geography_id, 'id') else str(queue.geography_id),
        mode=queue.mode.value,
        state=queue.state.value,
        call_type=queue.call_type.value,
        default_flow_template_id=queue.default_flow_template_id,
        default_language=queue.default_language,
        max_concurrent_calls=queue.max_concurrent_calls,
        time_windows=[
            TimeWindowSchema(**tw.model_dump()) for tw in queue.time_windows
        ],
        retry_strategy=RetryStrategySchema(**queue.retry_strategy.model_dump()),
        clarity_sync=ClaritySyncConfigSchema(**queue.clarity_sync.model_dump()),
        stats=QueueStatsSchema(**queue.stats.model_dump()) if include_stats else QueueStatsSchema(),
        created_at=queue.created_at,
        updated_at=queue.updated_at,
        started_at=queue.started_at,
        completed_at=queue.completed_at,
    )
