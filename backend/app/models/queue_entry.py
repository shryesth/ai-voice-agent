"""
QueueEntry model for campaign queue with retry logic and DLQ management.

Handles:
- Queue state machine (PENDING → CALLING → SUCCESS/FAILED/RETRYING)
- Intelligent retry logic with per-failure-reason delays
- Dead Letter Queue (DLQ) routing for terminal failures
- Max 3 retry attempts before DLQ
"""

from beanie import Document
from pydantic import BaseModel, Field
from datetime import datetime, timezone
from typing import Optional, List
from enum import Enum


class QueueState(str, Enum):
    """Queue entry lifecycle states"""
    PENDING = "pending"      # Waiting to be processed
    CALLING = "calling"      # Call in progress
    SUCCESS = "success"      # Call completed successfully
    FAILED = "failed"        # Terminal failure (moved to DLQ)
    RETRYING = "retrying"    # Scheduled for retry


class FailureReason(str, Enum):
    """
    Call failure classification for retry logic.

    Retry Delays:
    - NO_ANSWER: 30 minutes
    - BUSY: 1 hour
    - FAILED: 15 minutes
    - PERSON_NOT_AVAILABLE: 2 hours
    - SHORT_DURATION: 1 hour (<30s call)
    - NETWORK_FAILURE: 15 minutes
    - TIMEOUT: 1 hour

    Non-Retriable (→ DLQ immediately):
    - INVALID_NUMBER
    - REJECTED
    """
    NO_ANSWER = "no_answer"
    BUSY = "busy"
    FAILED = "failed"
    PERSON_NOT_AVAILABLE = "person_not_available"
    SHORT_DURATION = "short_duration"
    INVALID_NUMBER = "invalid_number"
    REJECTED = "rejected"
    NETWORK_FAILURE = "network_failure"
    TIMEOUT = "timeout"


class RetryHistory(BaseModel):
    """Single retry attempt record"""
    attempt_number: int = Field(..., ge=1, le=3)
    attempted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    failure_reason: FailureReason
    error_details: Optional[str] = Field(
        None,
        description="Additional context for debugging"
    )


class QueueEntry(Document):
    """
    Campaign queue entry with intelligent retry logic.

    Retry Strategy:
    - Max 3 attempts before DLQ
    - Per-failure-reason delays (see FailureReason enum)
    - Non-retriable failures go to DLQ immediately

    DLQ Conditions:
    - retry_count >= 3
    - FailureReason in [INVALID_NUMBER, REJECTED]

    Indexes:
    - campaign_id: Query all entries for campaign
    - state: Find pending/retrying entries for processing
    - next_retry_at: Scheduler finds ready-to-retry entries
    - moved_to_dlq: Query DLQ entries
    """

    campaign_id: str = Field(..., description="Campaign ID (referenced as string)")
    call_record_id: Optional[str] = Field(
        None,
        description="CallRecord ID (populated after call initiated)"
    )

    patient_phone: str = Field(
        ...,
        pattern=r'^\+[1-9]\d{1,14}$',
        description="E.164 format phone number"
    )
    language: str = Field(
        default="en",
        pattern="^(en|es|fr|ht)$",
        description="Language preference"
    )

    # State machine
    state: QueueState = Field(default=QueueState.PENDING)

    # Retry tracking
    retry_count: int = Field(default=0, ge=0, le=3)
    retry_history: List[RetryHistory] = Field(default_factory=list)
    next_retry_at: Optional[datetime] = Field(
        None,
        description="When to retry (None = ready now)"
    )

    # Failure tracking
    last_failure_reason: Optional[FailureReason] = None
    moved_to_dlq: bool = Field(
        default=False,
        description="True if non-retriable or max retries exceeded"
    )
    dlq_reason: Optional[str] = Field(
        None,
        description="Human-readable reason for DLQ placement"
    )

    # Audit timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    first_attempted_at: Optional[datetime] = Field(
        None,
        description="Timestamp of first call attempt"
    )
    completed_at: Optional[datetime] = Field(
        None,
        description="Timestamp when reached terminal state (SUCCESS or FAILED)"
    )

    class Settings:
        name = "queue_entries"
        indexes = [
            "campaign_id",
            "state",
            "next_retry_at",
            "moved_to_dlq",
        ]

    class Config:
        json_schema_extra = {
            "example": {
                "campaign_id": "507f1f77bcf86cd799439011",
                "patient_phone": "+12025551234",
                "language": "en",
                "state": "pending",
                "retry_count": 0,
                "moved_to_dlq": False
            }
        }
