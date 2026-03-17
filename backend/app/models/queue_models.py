"""
Queue Management Models

Pydantic models for managed queue configuration and call entry management.
"""
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, List

from pydantic import BaseModel, Field, field_validator

from backend.app.core.constants import (
    RETRY_DELAY_NO_ANSWER,
    RETRY_DELAY_BUSY,
    RETRY_DELAY_FAILED,
    RETRY_DELAY_TIMEOUT,
    RETRY_DELAY_PERSON_NOT_AVAILABLE,
    RETRY_DELAY_SHORT_DURATION,
    RETRY_DELAY_DEFAULT,
    MAX_QUEUE_RETRIES,
    MAX_CONCURRENT_CALLS,
)


class QueueState(str, Enum):
    """Queue state enum"""
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class QueueType(str, Enum):
    """Queue type for distinguishing sync behavior"""
    MANUAL = "manual"      # Calls added manually via API
    NEXUS = "nexus"    # Auto-synced from Nexus API


class CallEntryStatus(str, Enum):
    """Call entry status enum"""
    PENDING = "pending"
    CALLING = "calling"
    SUCCESS = "success"
    FAILED = "failed"
    RETRY_SCHEDULED = "retry_scheduled"
    DEAD_LETTER = "dead_letter"
    CANCELLED = "cancelled"


class FailureReason(str, Enum):
    """Call failure reason enum"""
    NO_ANSWER = "no_answer"
    BUSY = "busy"
    FAILED = "failed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"
    INVALID_NUMBER = "invalid_number"
    PERSON_NOT_AVAILABLE = "person_not_available"
    SHORT_DURATION = "short_duration"
    ERROR = "error"


# Non-retriable failure reasons (terminal failures)
NON_RETRIABLE_FAILURES = [FailureReason.INVALID_NUMBER, FailureReason.REJECTED]


class TimeWindow(BaseModel):
    """Time window configuration for queue operation"""
    start_time_utc: str = Field(..., description="Start time in HH:MM format (UTC)")
    end_time_utc: str = Field(..., description="End time in HH:MM format (UTC)")
    days_of_week: List[int] = Field(
        default=[0, 1, 2, 3, 4],  # Monday to Friday by default
        description="Days of week (0=Monday, 6=Sunday)"
    )

    @field_validator("start_time_utc", "end_time_utc")
    @classmethod
    def validate_time_format(cls, v):
        """Validate time format HH:MM"""
        try:
            hours, minutes = map(int, v.split(":"))
            if not (0 <= hours <= 23 and 0 <= minutes <= 59):
                raise ValueError
        except (ValueError, AttributeError):
            raise ValueError("Time must be in HH:MM format (00:00 to 23:59)")
        return v

    @field_validator("days_of_week")
    @classmethod
    def validate_days_of_week(cls, v):
        """Validate days of week are 0-6"""
        if not all(0 <= day <= 6 for day in v):
            raise ValueError("Days of week must be integers 0-6 (0=Monday, 6=Sunday)")
        return v


class RetryStrategy(BaseModel):
    """Retry strategy configuration"""
    max_retries: int = Field(default=MAX_QUEUE_RETRIES, ge=0, le=10)
    exponential_backoff: bool = Field(default=True)
    base_delay_seconds: int = Field(default=RETRY_DELAY_DEFAULT, ge=60)

    # Per-failure-reason delays (using centralized constants)
    no_answer_delay: int = Field(default=RETRY_DELAY_NO_ANSWER)
    busy_delay: int = Field(default=RETRY_DELAY_BUSY)
    failed_delay: int = Field(default=RETRY_DELAY_FAILED)
    timeout_delay: int = Field(default=RETRY_DELAY_TIMEOUT)
    person_not_available_delay: int = Field(default=RETRY_DELAY_PERSON_NOT_AVAILABLE)
    short_duration_delay: int = Field(default=RETRY_DELAY_SHORT_DURATION)

    # No-retry list (terminal failures)
    no_retry_reasons: List[FailureReason] = Field(
        default_factory=lambda: list(NON_RETRIABLE_FAILURES)
    )

    def get_delay_for_reason(self, reason: FailureReason, retry_count: int) -> int:
        """
        Calculate delay for specific failure reason with optional exponential backoff

        Args:
            reason: Failure reason
            retry_count: Current retry attempt number (0-indexed)

        Returns:
            Delay in seconds
        """
        delay_map = {
            FailureReason.NO_ANSWER: self.no_answer_delay,
            FailureReason.BUSY: self.busy_delay,
            FailureReason.FAILED: self.failed_delay,
            FailureReason.TIMEOUT: self.timeout_delay,
            FailureReason.PERSON_NOT_AVAILABLE: self.person_not_available_delay,
            FailureReason.SHORT_DURATION: self.short_duration_delay,
        }

        base_delay = delay_map.get(reason, self.base_delay_seconds)

        if self.exponential_backoff and retry_count > 0:
            return base_delay * (2 ** retry_count)

        return base_delay

    def should_retry(self, reason: FailureReason, current_retry_count: int) -> bool:
        """Check if a failure should be retried"""
        if reason in self.no_retry_reasons:
            return False
        return current_retry_count < self.max_retries


class StateHistoryEntry(BaseModel):
    """Single state history entry in audit trail"""
    from_state: Optional[CallEntryStatus] = None
    to_state: CallEntryStatus
    reason: str
    failure_reason: Optional[FailureReason] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    call_sid: Optional[str] = None


class CallEntryStorage(BaseModel):
    """Storage tracking for call recordings and transcripts"""
    recording_s3_key: Optional[str] = None
    transcript_saved: bool = False
    recording_metadata_saved: bool = False
    recording_url: Optional[str] = None
    recording_duration_seconds: Optional[int] = None


class QueueConfig(BaseModel):
    """Queue configuration model"""
    queue_id: str = Field(..., description="Unique queue identifier")
    name: str = Field(..., description="Human-readable queue name")
    domain: str = Field(default="vaccination", description="Domain type")
    description: Optional[str] = None

    # Time window
    time_window: Optional[TimeWindow] = None

    # Retry strategy
    retry_strategy: RetryStrategy = Field(default_factory=RetryStrategy)

    # Concurrency
    max_concurrent_calls: int = Field(default=1, ge=1, le=MAX_CONCURRENT_CALLS)

    # State
    state: QueueState = Field(default=QueueState.PAUSED)

    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    model_config = {"use_enum_values": True}


class CallEntry(BaseModel):
    """Call entry model"""
    entry_id: str = Field(..., description="Unique entry identifier")
    queue_id: str = Field(..., description="Parent queue reference")

    # Call details
    phone_number: str
    call_type: str = Field(default="vaccination")
    call_data: Dict[str, Any] = Field(default_factory=dict)

    # Status tracking
    status: CallEntryStatus = Field(default=CallEntryStatus.PENDING)

    # Retry tracking
    retry_count: int = Field(default=0, ge=0)
    parent_call_sid: Optional[str] = None
    child_call_sids: List[str] = Field(default_factory=list)

    # Failure tracking
    failure_reason: Optional[FailureReason] = None
    failure_details: Optional[str] = None

    # Scheduling
    scheduled_for: Optional[datetime] = None
    retry_scheduled_at: Optional[datetime] = None

    # Execution tracking
    call_sid: Optional[str] = None
    call_duration: Optional[int] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Storage integration
    storage: CallEntryStorage = Field(default_factory=CallEntryStorage)

    # Audit trail
    state_history: List[StateHistoryEntry] = Field(default_factory=list)

    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"use_enum_values": True}


# Request/Response Models

class QueueConfigCreate(BaseModel):
    """Request model for creating a queue"""
    queue_id: str
    name: str
    domain: str = "vaccination"
    description: Optional[str] = None
    time_window: Optional[TimeWindow] = None
    retry_strategy: Optional[RetryStrategy] = None
    max_concurrent_calls: int = Field(default=1, ge=1, le=MAX_CONCURRENT_CALLS)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class QueueConfigUpdate(BaseModel):
    """Request model for updating a queue"""
    name: Optional[str] = None
    description: Optional[str] = None
    time_window: Optional[TimeWindow] = None
    retry_strategy: Optional[RetryStrategy] = None
    max_concurrent_calls: Optional[int] = Field(None, ge=1, le=MAX_CONCURRENT_CALLS)
    metadata: Optional[Dict[str, Any]] = None


class CallEntryCreate(BaseModel):
    """Request model for creating a call entry"""
    phone_number: str
    call_type: str = "vaccination"
    call_data: Dict[str, Any] = Field(default_factory=dict)
    scheduled_for: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CallEntryBulkCreate(BaseModel):
    """Request model for bulk creating call entries"""
    calls: List[CallEntryCreate]


class QueueStatistics(BaseModel):
    """Queue statistics response model"""
    queue_id: str
    queue_name: str
    state: QueueState
    total_calls: int = 0
    pending_calls: int = 0
    calling_now: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    retry_scheduled_calls: int = 0
    dead_letter_calls: int = 0
    cancelled_calls: int = 0
    failure_breakdown: Dict[str, int] = Field(default_factory=dict)
    average_call_duration: Optional[float] = None
    success_rate: float = 0.0
    estimated_completion: Optional[datetime] = None
    storage_stats: Dict[str, Any] = Field(default_factory=dict)
    last_updated: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"use_enum_values": True}


class QueueResponse(BaseModel):
    """Response model for queue operations"""
    queue_id: str
    name: str
    domain: str
    state: QueueState
    description: Optional[str] = None
    time_window: Optional[TimeWindow] = None
    retry_strategy: RetryStrategy
    max_concurrent_calls: int
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    model_config = {"use_enum_values": True}


class CallEntryResponse(BaseModel):
    """Response model for call entry"""
    entry_id: str
    queue_id: str
    phone_number: str
    call_type: str
    status: CallEntryStatus
    retry_count: int
    failure_reason: Optional[FailureReason] = None
    failure_details: Optional[str] = None
    call_sid: Optional[str] = None
    call_duration: Optional[int] = None
    scheduled_for: Optional[datetime] = None
    retry_scheduled_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"use_enum_values": True}
