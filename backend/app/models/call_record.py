"""
CallRecord model for individual patient feedback calls.

Tracks:
- Patient contact information
- Conversation state and transcript
- Feedback responses
- Urgency flags and keywords
- Call tracking metadata (Twilio integration)
"""

from beanie import Document, Link
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List, Dict
from enum import Enum


class CallOutcome(str, Enum):
    """Final call disposition."""
    SUCCESS = "success"  # Completed full conversation
    PARTIAL_SUCCESS = "partial_success"  # Partial feedback collected
    NO_ANSWER = "no_answer"  # Did not pick up
    BUSY = "busy"  # Line busy
    FAILED = "failed"  # Technical failure
    INVALID_NUMBER = "invalid_number"  # Not a valid phone number
    REJECTED = "rejected"  # Call rejected by carrier
    WRONG_PERSON = "wrong_person"  # Not patient/guardian/helper
    TIMEOUT = "timeout"  # Exceeded 10-minute max duration
    NETWORK_FAILURE = "network_failure"  # Dropped mid-call


class FeedbackData(BaseModel):
    """Structured patient feedback responses."""
    overall_satisfaction: Optional[int] = Field(
        None,
        ge=1,
        le=10,
        description="Satisfaction rating (1-10 scale)"
    )
    specific_concerns: Optional[str] = Field(
        None,
        description="Free-text concerns or complaints"
    )
    side_effects_reported: Optional[str] = Field(
        None,
        description="Reported side effects (if applicable)"
    )
    experience_quality: Optional[str] = Field(
        None,
        description="Overall experience description"
    )


class ConversationTurn(BaseModel):
    """Single speaker turn in conversation."""
    speaker: str = Field(..., description="'patient' or 'ai'")
    text: str = Field(..., description="Transcribed text")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    language: Optional[str] = Field(None, description="Language code for this turn")


class ConversationStage(str, Enum):
    """6-stage conversation flow."""
    GREETING = "greeting"
    LANGUAGE_SELECTION = "language_selection"
    PATIENT_VERIFICATION = "patient_verification"
    FEEDBACK_COLLECTION = "feedback_collection"
    URGENCY_DETECTION = "urgency_detection"
    CALL_COMPLETION = "call_completion"


class ConversationState(BaseModel):
    """Tracks progress through conversation stages."""
    current_stage: Optional[ConversationStage] = None
    completed_stages: List[ConversationStage] = Field(default_factory=list)
    failed_stages: List[ConversationStage] = Field(default_factory=list)
    stage_retry_counts: Dict[str, int] = Field(
        default_factory=dict,
        description="Retry attempts per stage (max 2 per stage)"
    )


class CallTracking(BaseModel):
    """Twilio call metadata and timing."""
    call_sid: Optional[str] = Field(None, description="Twilio Call SID")
    stream_sid: Optional[str] = Field(None, description="Twilio Stream SID")
    status: str = Field(default="queued")
    outcome: Optional[CallOutcome] = None

    # Timing
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    duration_seconds: Optional[int] = Field(
        None,
        description="Call duration in seconds"
    )


class CallRecord(Document):
    """
    Individual patient feedback call with full conversation history.

    Indexes:
    - campaign_id: Query all calls for a campaign
    - call_tracking.call_sid: Twilio webhook lookups
    - call_tracking.outcome: Filter by call result
    - urgency_flagged: Query urgent cases for clinical review
    - created_at: Sort by recency
    """

    # Import Campaign here to avoid circular import
    from backend.app.models.campaign import Campaign

    campaign_id: Link[Campaign]

    # Patient contact (phone number ownership = authentication)
    patient_phone: str = Field(..., description="E.164 format")
    language: str = Field(default="en", description="en, es, fr, ht")

    # Conversation data
    conversation_state: ConversationState = Field(default_factory=ConversationState)
    transcript: List[ConversationTurn] = Field(
        default_factory=list,
        description="Full conversation history with timestamps"
    )
    feedback: FeedbackData = Field(default_factory=FeedbackData)

    # Urgency detection
    urgency_flagged: bool = Field(
        default=False,
        description="True if keywords detected: hospital, severe, can't breathe"
    )
    urgency_keywords_detected: List[str] = Field(default_factory=list)

    # Call tracking
    call_tracking: CallTracking = Field(default_factory=CallTracking)

    # Error context
    error_message: Optional[str] = Field(
        None,
        description="Detailed error for debugging (not shown to patients)"
    )

    # Audit
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "call_records"
        indexes = [
            "campaign_id",
            "call_tracking.call_sid",
            "call_tracking.outcome",
            "urgency_flagged",
            "created_at",
        ]

    class Config:
        json_schema_extra = {
            "example": {
                "patient_phone": "+12025551234",
                "language": "en",
                "urgency_flagged": False,
                "call_tracking": {
                    "call_sid": "CA1234567890abcdef",
                    "outcome": "success",
                    "duration_seconds": 180
                }
            }
        }
