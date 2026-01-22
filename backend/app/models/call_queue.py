"""
CallQueue model for managing call queues.

Replaces the Campaign model with a more flexible queue-based approach.
Supports multiple queue modes: FOREVER (continuous), BATCH (one-time), MANUAL.
"""

from __future__ import annotations

from beanie import Document, PydanticObjectId
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List

from backend.app.models.enums import (
    CallType,
    QueueMode,
    QueueState,
)


class TimeWindow(BaseModel):
    """
    Time window for queue processing.

    Defines when calls can be made based on UTC time.
    """

    start_time_utc: str = Field(
        ...,
        description="Start time in UTC (HH:MM format)",
        pattern=r"^([01]\d|2[0-3]):([0-5]\d)$",
    )
    end_time_utc: str = Field(
        ...,
        description="End time in UTC (HH:MM format)",
        pattern=r"^([01]\d|2[0-3]):([0-5]\d)$",
    )
    days_of_week: List[int] = Field(
        default=[0, 1, 2, 3, 4],  # Mon-Fri
        description="Days of week (0=Monday, 6=Sunday)",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "start_time_utc": "09:00",
                "end_time_utc": "17:00",
                "days_of_week": [0, 1, 2, 3, 4],
            }
        }


class RetryStrategy(BaseModel):
    """
    Retry configuration for failed calls.

    Per-failure-reason delays allow fine-grained control over retry timing.
    """

    max_retries: int = Field(default=3, ge=0, le=10)
    exponential_backoff: bool = Field(
        default=True,
        description="Multiply delays by attempt number",
    )
    # Per-failure delays (seconds)
    no_answer_delay: int = Field(default=1800, description="30 min")
    busy_delay: int = Field(default=3600, description="1 hour")
    voicemail_delay: int = Field(default=7200, description="2 hours")
    timeout_delay: int = Field(default=1800, description="30 min")
    person_not_available_delay: int = Field(default=7200, description="2 hours")
    short_duration_delay: int = Field(default=3600, description="1 hour")
    failed_delay: int = Field(default=900, description="15 min")

    class Config:
        json_schema_extra = {
            "example": {
                "max_retries": 3,
                "exponential_backoff": True,
                "no_answer_delay": 1800,
                "busy_delay": 3600,
                "voicemail_delay": 7200,
            }
        }


class ClaritySyncConfig(BaseModel):
    """
    Configuration for forever-running queues syncing from Clarity.

    Only applicable when queue mode is FOREVER.
    """

    enabled: bool = Field(default=False)
    sync_interval_minutes: int = Field(
        default=15,
        ge=1,
        le=60,
        description="How often to poll Clarity for new subjects",
    )
    max_per_sync: int = Field(
        default=100,
        ge=1,
        le=1000,
        description="Maximum recipients to pull per sync cycle",
    )
    event_type_filter: List[str] = Field(
        default_factory=list,
        description="Clarity event types to pull (empty = all types)",
    )
    last_sync_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp of last successful sync",
    )
    last_sync_count: int = Field(
        default=0,
        description="Number of recipients pulled in last sync",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "enabled": True,
                "sync_interval_minutes": 15,
                "max_per_sync": 100,
                "event_type_filter": ["Suivi des Enfants", "Prenatal"],
            }
        }


class QueueStats(BaseModel):
    """
    Real-time statistics for the queue.

    Updated by the queue processor task.
    """

    total_recipients: int = 0
    pending_count: int = 0
    calling_count: int = 0
    retrying_count: int = 0
    completed_count: int = 0
    failed_count: int = 0
    not_reachable_count: int = 0
    skipped_count: int = 0
    dlq_count: int = 0

    # Call outcome stats
    total_calls_made: int = 0
    successful_verifications: int = 0
    urgent_flagged_count: int = 0

    # Timing stats
    avg_call_duration_seconds: Optional[float] = None
    last_call_at: Optional[datetime] = None


class CallQueue(Document):
    """
    Queue of calls to process.

    Can be:
    - FOREVER mode: Continuously pulls from Clarity
    - BATCH mode: One-time batch, completes when done
    - MANUAL mode: Recipients added via API only

    Replaces the Campaign model with more flexible queue semantics.
    """

    # Identity
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=1000)
    geography_id: PydanticObjectId = Field(
        ...,
        description="Reference to the parent Geography"
    )

    # Queue configuration
    mode: QueueMode = Field(default=QueueMode.BATCH)
    state: QueueState = Field(default=QueueState.DRAFT)

    # Call configuration
    call_type: CallType = Field(default=CallType.PATIENT_FEEDBACK)
    default_flow_template_id: Optional[str] = Field(
        default=None,
        description="Optional flow template ID (defaults to call_type default)",
    )
    default_language: str = Field(
        default="en",
        description="Default language for calls (en, ht, fr, es)",
    )

    # Processing config
    max_concurrent_calls: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Maximum simultaneous calls",
    )
    time_windows: List[TimeWindow] = Field(
        default_factory=list,
        description="Time windows for call processing (empty = 24/7)",
    )
    retry_strategy: RetryStrategy = Field(default_factory=RetryStrategy)

    # Clarity sync (for FOREVER mode)
    clarity_sync: ClaritySyncConfig = Field(default_factory=ClaritySyncConfig)

    # Statistics (updated by queue processor)
    stats: QueueStats = Field(default_factory=QueueStats)

    # Lifecycle timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = Field(
        default=None,
        description="When queue was first activated",
    )
    completed_at: Optional[datetime] = Field(
        default=None,
        description="When queue completed (BATCH mode only)",
    )

    # Soft delete
    deleted_at: Optional[datetime] = Field(
        default=None,
        description="Soft delete timestamp",
    )

    class Settings:
        name = "call_queues"
        indexes = [
            "geography_id",
            "state",
            "mode",
            "call_type",
            "created_at",
        ]

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Patient Feedback - Haiti",
                "description": "Continuous patient feedback collection for Haiti",
                "mode": "forever",
                "state": "draft",
                "call_type": "patient_feedback",
                "default_language": "ht",
                "max_concurrent_calls": 10,
                "time_windows": [
                    {
                        "start_time_utc": "13:00",
                        "end_time_utc": "21:00",
                        "days_of_week": [0, 1, 2, 3, 4],
                    }
                ],
                "clarity_sync": {
                    "enabled": True,
                    "sync_interval_minutes": 5,
                    "event_type_filter": [],
                },
            }
        }


# Utility functions for state transitions
def can_transition_to(current_state: QueueState, new_state: QueueState) -> bool:
    """
    Check if a state transition is valid.

    Valid transitions:
    - DRAFT -> ACTIVE
    - ACTIVE -> PAUSED, COMPLETED (batch only), CANCELLED
    - PAUSED -> ACTIVE, CANCELLED
    - COMPLETED -> (terminal)
    - CANCELLED -> (terminal)
    """
    valid_transitions = {
        QueueState.DRAFT: {QueueState.ACTIVE, QueueState.CANCELLED},
        QueueState.ACTIVE: {QueueState.PAUSED, QueueState.COMPLETED, QueueState.CANCELLED},
        QueueState.PAUSED: {QueueState.ACTIVE, QueueState.CANCELLED},
        QueueState.COMPLETED: set(),  # Terminal
        QueueState.CANCELLED: set(),  # Terminal
    }
    return new_state in valid_transitions.get(current_state, set())


# Import Geography after CallQueue class definition for model_rebuild() to work
# This import must happen at runtime (not just type checking) so that Geography
# is in the module's globals when Pydantic resolves the forward reference
from backend.app.models.geography import Geography  # noqa: F401, E402
