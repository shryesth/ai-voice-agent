"""
Queue management request/response schemas.

Schemas for:
- QueueEntry responses with retry tracking
- DLQ (Dead Letter Queue) management
- Queue statistics and summaries
"""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List

from backend.app.models.queue_entry import QueueState, FailureReason


class RetryHistoryResponse(BaseModel):
    """Single retry attempt record"""
    attempt_number: int = Field(..., ge=1, le=3)
    attempted_at: datetime
    failure_reason: FailureReason
    error_details: Optional[str] = None


class QueueEntryResponse(BaseModel):
    """Queue entry with retry tracking"""
    id: str
    campaign_id: str
    call_record_id: Optional[str] = None
    patient_phone: str
    language: str
    state: QueueState
    retry_count: int
    retry_history: List[RetryHistoryResponse]
    next_retry_at: Optional[datetime] = None
    last_failure_reason: Optional[FailureReason] = None
    moved_to_dlq: bool
    dlq_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    first_attempted_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    class Config:
        json_schema_extra = {
            "example": {
                "id": "507f1f77bcf86cd799439011",
                "campaign_id": "507f191e810c19729de860ea",
                "patient_phone": "+12025551234",
                "language": "en",
                "state": "retrying",
                "retry_count": 1,
                "retry_history": [
                    {
                        "attempt_number": 1,
                        "attempted_at": "2026-01-18T10:00:00Z",
                        "failure_reason": "no_answer"
                    }
                ],
                "next_retry_at": "2026-01-18T10:30:00Z",
                "last_failure_reason": "no_answer",
                "moved_to_dlq": False
            }
        }


class QueueSummaryResponse(BaseModel):
    """Summary statistics for a campaign queue"""
    campaign_id: str
    total_entries: int
    pending_count: int
    calling_count: int
    success_count: int
    failed_count: int
    retrying_count: int
    dlq_count: int

    class Config:
        json_schema_extra = {
            "example": {
                "campaign_id": "507f191e810c19729de860ea",
                "total_entries": 100,
                "pending_count": 20,
                "calling_count": 5,
                "success_count": 60,
                "failed_count": 10,
                "retrying_count": 5,
                "dlq_count": 10
            }
        }


class QueueListResponse(BaseModel):
    """Paginated list of queue entries"""
    total: int
    skip: int
    limit: int
    items: List[QueueEntryResponse]


class DLQResponse(BaseModel):
    """Dead Letter Queue entry with failure context"""
    id: str
    campaign_id: str
    call_record_id: Optional[str] = None
    patient_phone: str
    language: str
    retry_count: int
    retry_history: List[RetryHistoryResponse]
    last_failure_reason: Optional[FailureReason] = None
    dlq_reason: str
    created_at: datetime
    updated_at: datetime
    first_attempted_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    class Config:
        json_schema_extra = {
            "example": {
                "id": "507f1f77bcf86cd799439011",
                "campaign_id": "507f191e810c19729de860ea",
                "patient_phone": "+12025551234",
                "language": "en",
                "retry_count": 3,
                "retry_history": [
                    {
                        "attempt_number": 1,
                        "attempted_at": "2026-01-18T10:00:00Z",
                        "failure_reason": "no_answer"
                    },
                    {
                        "attempt_number": 2,
                        "attempted_at": "2026-01-18T10:30:00Z",
                        "failure_reason": "no_answer"
                    },
                    {
                        "attempt_number": 3,
                        "attempted_at": "2026-01-18T11:00:00Z",
                        "failure_reason": "no_answer"
                    }
                ],
                "last_failure_reason": "no_answer",
                "dlq_reason": "Max retry attempts (3) exceeded for NO_ANSWER",
                "created_at": "2026-01-18T09:55:00Z",
                "completed_at": "2026-01-18T11:00:00Z"
            }
        }


class DLQListResponse(BaseModel):
    """Paginated list of DLQ entries"""
    total: int
    skip: int
    limit: int
    items: List[DLQResponse]


class GlobalQueueStatsResponse(BaseModel):
    """Global queue statistics across all campaigns"""
    total_campaigns_active: int
    total_queue_entries: int
    total_pending: int
    total_calling: int
    total_success: int
    total_failed: int
    total_retrying: int
    total_dlq: int

    # Additional metrics
    average_retry_count: float
    dlq_rate_percent: float

    class Config:
        json_schema_extra = {
            "example": {
                "total_campaigns_active": 5,
                "total_queue_entries": 500,
                "total_pending": 100,
                "total_calling": 10,
                "total_success": 300,
                "total_failed": 50,
                "total_retrying": 40,
                "total_dlq": 50,
                "average_retry_count": 0.8,
                "dlq_rate_percent": 10.0
            }
        }


class DLQRetryRequest(BaseModel):
    """Request to manually retry a DLQ entry"""
    reset_retry_count: bool = Field(
        default=True,
        description="Whether to reset retry count to 0 (default: true)"
    )
