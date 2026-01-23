"""
RecordingDLQ model for tracking failed recording uploads.

Dead-letter queue for recordings that failed to upload to S3/MinIO
after all retry attempts. Enables manual recovery and monitoring.
"""

from beanie import Document
from pydantic import BaseModel, Field
from datetime import datetime, timezone
from typing import Optional, List


class ErrorEntry(BaseModel):
    """Single error occurrence in the error history."""

    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    error_type: str = Field(..., description="Type of error (e.g., 'S3Error', 'ValidationError')")
    error_message: str = Field(..., description="Error message")
    attempt_number: int = Field(..., description="Which attempt this error occurred on")


class RecordingDLQ(Document):
    """
    Dead-letter queue entry for failed recording uploads.

    Tracks recordings that failed to upload to S3/MinIO after all retry
    attempts have been exhausted. Provides context for manual recovery.

    Indexes:
    - call_id: Quick lookup by call
    - call_sid: Twilio reference lookup
    - resolved: Filter unresolved entries
    - created_at: Sort by recency
    - geography_id: Filter by geography
    """

    # Call identifiers
    call_id: str = Field(..., description="CallRecord document ID")
    call_sid: Optional[str] = Field(
        default=None,
        description="Twilio Call SID"
    )
    recording_sid: Optional[str] = Field(
        default=None,
        description="Twilio Recording SID"
    )

    # Context for recovery
    geography_id: str = Field(..., description="Geography ID for partitioning")
    is_test_call: bool = Field(default=False, description="Whether this was a test call")

    # Failure tracking
    failure_reason: str = Field(..., description="Primary reason for failure")
    failure_count: int = Field(default=1, description="Number of failed upload attempts")
    error_history: List[ErrorEntry] = Field(
        default_factory=list,
        description="History of all errors during upload attempts"
    )

    # Recovery data
    has_redis_fallback: bool = Field(
        default=False,
        description="Whether audio data is stored in Redis fallback"
    )
    redis_fallback_key: Optional[str] = Field(
        default=None,
        description="Redis key for fallback storage"
    )
    redis_fallback_expires_at: Optional[datetime] = Field(
        default=None,
        description="When Redis fallback data expires"
    )

    # Original recording metadata
    recording_duration_seconds: Optional[int] = Field(
        default=None,
        description="Recording duration for reference"
    )
    recording_size_bytes: Optional[int] = Field(
        default=None,
        description="Size of audio data for reference"
    )
    twilio_recording_url: Optional[str] = Field(
        default=None,
        description="Original Twilio recording URL (may have expired)"
    )

    # Resolution tracking
    resolved: bool = Field(
        default=False,
        description="Whether this DLQ entry has been resolved"
    )
    resolution_method: Optional[str] = Field(
        default=None,
        description="How the entry was resolved: 'retry_success', 'manual_upload', 'abandoned'"
    )
    resolved_at: Optional[datetime] = Field(
        default=None,
        description="When the entry was resolved"
    )
    resolved_by: Optional[str] = Field(
        default=None,
        description="User or system that resolved the entry"
    )
    resolution_notes: Optional[str] = Field(
        default=None,
        description="Notes about the resolution"
    )

    # Audit timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "recording_dlq"
        indexes = [
            "call_id",
            "call_sid",
            "recording_sid",
            "geography_id",
            "resolved",
            "created_at",
            "has_redis_fallback",
        ]

    class Config:
        json_schema_extra = {
            "example": {
                "call_id": "507f1f77bcf86cd799439011",
                "call_sid": "CA1234567890abcdef",
                "recording_sid": "RE1234567890abcdef",
                "geography_id": "507f1f77bcf86cd799439012",
                "is_test_call": False,
                "failure_reason": "S3 upload failed after 5 retries: ConnectionError",
                "failure_count": 5,
                "error_history": [
                    {
                        "timestamp": "2024-01-15T10:00:00Z",
                        "error_type": "S3Error",
                        "error_message": "Connection refused",
                        "attempt_number": 1
                    }
                ],
                "has_redis_fallback": True,
                "redis_fallback_key": "recording_fallback:507f1f77bcf86cd799439011",
                "resolved": False,
            }
        }

    def add_error(self, error_type: str, error_message: str, attempt_number: int) -> None:
        """Add an error entry to the history."""
        self.error_history.append(ErrorEntry(
            error_type=error_type,
            error_message=error_message,
            attempt_number=attempt_number
        ))
        self.failure_count = attempt_number
        self.updated_at = datetime.now(timezone.utc)

    def mark_resolved(
        self,
        method: str,
        resolved_by: Optional[str] = None,
        notes: Optional[str] = None
    ) -> None:
        """Mark this DLQ entry as resolved."""
        self.resolved = True
        self.resolution_method = method
        self.resolved_at = datetime.now(timezone.utc)
        self.resolved_by = resolved_by
        self.resolution_notes = notes
        self.updated_at = datetime.now(timezone.utc)
