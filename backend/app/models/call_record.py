"""
CallRecord model for individual call records.

Tracks:
- Contact information (patient, guardian, caregiver)
- Conversation state and transcript
- Conversation data (feedback, verification responses)
- Urgency flags and keywords
- Call tracking metadata (Twilio integration)
- Human callback requests
"""

from __future__ import annotations

from beanie import Document, PydanticObjectId
from pydantic import BaseModel, Field
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from backend.app.models.enums import (
    CallType,
    CallOutcome,
    ContactType,
)


class ConversationData(BaseModel):
    """
    Flexible data extracted from conversation.

    Supports both legacy FeedbackData fields and new flexible extraction.
    """

    # Verification fields
    is_visit_confirmed: Optional[bool] = Field(
        default=None,
        description="Whether the visit was confirmed",
    )
    is_service_confirmed: Optional[bool] = Field(
        default=None,
        description="Whether the specific service was confirmed",
    )
    verification_responses: Dict[str, Any] = Field(
        default_factory=dict,
        description="Stage-by-stage verification responses",
    )

    # Legacy fields (backward compatible with FeedbackData)
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
    has_side_effects: Optional[bool] = Field(
        default=None,
        description="Whether side effects were reported",
    )
    experience_quality: Optional[str] = Field(
        None,
        description="Overall experience description"
    )

    # Flexible extraction
    extracted_data: Dict[str, Any] = Field(
        default_factory=dict,
        description="All extracted data from conversation (per flow schema)",
    )


# Backward compatibility alias
FeedbackData = ConversationData


class ConversationTurn(BaseModel):
    """Single speaker turn in conversation."""

    speaker: str = Field(..., description="'patient', 'ai', 'contact', or 'system'")
    text: str = Field(..., description="Transcribed text")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    language: Optional[str] = Field(None, description="Language code for this turn")


class TranslatedMessage(BaseModel):
    """A translated message entry for non-English transcripts."""

    speaker: str = Field(..., description="Original speaker: 'patient' or 'ai'")
    original_text: str = Field(..., description="Original text in source language")
    english_text: str = Field(..., description="Translated text in English")
    timestamp: datetime = Field(..., description="Original message timestamp")


class EnglishTranslation(BaseModel):
    """English translation of non-English call transcript."""

    status: str = Field(
        default="pending",
        description="Translation status: pending, in_progress, completed, failed"
    )
    source_language: Optional[str] = Field(
        default=None,
        description="Source language code (ht, fr, es)"
    )
    messages: List[TranslatedMessage] = Field(
        default_factory=list,
        description="List of translated messages"
    )
    completed_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp when translation completed"
    )
    attempts: int = Field(
        default=0,
        description="Number of translation attempts"
    )
    error: Optional[str] = Field(
        default=None,
        description="Error message if translation failed"
    )


class ConversationStage(str):
    """
    Conversation flow stages.

    Common stages for Patient Feedback Collection:
    - GREETING: Greet and identify as Ministry of Health AI
    - CONFIRM_IDENTITY: Confirm speaking with correct person
    - CONFIRM_VISIT: Confirm visited facility on date
    - CONFIRM_SERVICE: Event-specific confirmation (varies by event_type)
    - SIDE_EFFECTS: [Optional] Check for side effects (vaccination)
    - SATISFACTION: [Optional] Collect rating
    - COMPLETION: Thank and end call

    Note: This class inherits from str to allow string operations while providing
    enum-like constants. Pydantic v2 compatibility requires this approach rather
    than inheriting from both str and Enum.
    """

    GREETING = "greeting"
    CONFIRM_IDENTITY = "confirm_identity"
    CONFIRM_VISIT = "confirm_visit"
    CONFIRM_SERVICE = "confirm_service"
    SIDE_EFFECTS = "side_effects"
    SATISFACTION = "satisfaction"
    COMPLETION = "completion"

    # Legacy stages (backward compatibility)
    LANGUAGE_SELECTION = "language_selection"
    PATIENT_VERIFICATION = "patient_verification"
    FEEDBACK_COLLECTION = "feedback_collection"
    URGENCY_DETECTION = "urgency_detection"
    CALL_COMPLETION = "call_completion"


class ConversationState(BaseModel):
    """Tracks progress through conversation stages."""

    current_stage: Optional[str] = Field(
        default=None,
        description="Current conversation stage",
    )
    completed_stages: List[str] = Field(
        default_factory=list,
        description="Stages that have been completed",
    )
    failed_stages: List[str] = Field(
        default_factory=list,
        description="Stages that failed",
    )
    stage_retry_counts: Dict[str, int] = Field(
        default_factory=dict,
        description="Retry attempts per stage (max 2 per stage)"
    )
    stage_data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Data collected at each stage",
    )


class CallTracking(BaseModel):
    """Twilio call metadata and timing."""

    call_sid: Optional[str] = Field(None, description="Twilio Call SID")
    stream_sid: Optional[str] = Field(None, description="Twilio Stream SID")
    status: str = Field(default="queued")
    outcome: Optional[CallOutcome] = Field(
        default=None,
        description="Detailed call outcome",
    )

    # Twilio status (from webhook)
    twilio_status: Optional[str] = Field(
        default=None,
        description="Raw Twilio call status",
    )

    # Answering machine detection
    answered_by: Optional[str] = Field(
        default=None,
        description="'human', 'machine_start', 'machine_end_beep', 'fax', 'unknown'",
    )

    # Timing
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    duration_seconds: Optional[int] = Field(
        None,
        description="Call duration in seconds"
    )


class RecordingMetadata(BaseModel):
    """Metadata for call recording stored in S3/MinIO."""

    # Original dual-channel recording (always stored)
    recording_url: Optional[str] = Field(
        None,
        description="S3/MinIO URL to the recording file"
    )
    s3_object_key: Optional[str] = Field(
        None,
        description="S3 object key for dual-channel recording (e.g., {call_id}_dual.mp3)"
    )
    duration_seconds: Optional[int] = Field(
        None,
        description="Recording duration in seconds"
    )
    file_size_bytes: Optional[int] = Field(
        None,
        description="Recording file size in bytes"
    )
    sample_rate: int = Field(
        default=8000,
        description="Audio sample rate in Hz (8kHz for Twilio telephony)"
    )
    num_channels: int = Field(
        default=2,
        description="Number of audio channels (1=mono, 2=stereo/dual-channel)"
    )
    uploaded_at: Optional[datetime] = Field(
        None,
        description="Timestamp when recording was uploaded to S3"
    )

    # Twilio-specific metadata
    recording_source: str = Field(
        default="twilio",
        description="Source of recording (twilio or pipecat)"
    )
    recording_sid: Optional[str] = Field(
        None,
        description="Twilio Recording SID"
    )
    recording_format: str = Field(
        default="mp3",
        description="Audio format (mp3, wav, etc.)"
    )

    # Upload tracking fields
    upload_status: str = Field(
        default="pending",
        description="Upload status: pending, uploading, completed, failed, dlq"
    )
    upload_attempts: int = Field(
        default=0,
        description="Number of upload attempts"
    )
    last_upload_error: Optional[str] = Field(
        None,
        description="Last upload error message"
    )
    dlq_entry_id: Optional[str] = Field(
        None,
        description="Reference to RecordingDLQ entry if upload failed"
    )

    # Split recordings (lazy-created on demand via /split-recording endpoint)
    caller_s3_key: Optional[str] = Field(
        None,
        description="S3 object key for caller-only track (e.g., {call_id}_caller.mp3)"
    )
    callee_s3_key: Optional[str] = Field(
        None,
        description="S3 object key for callee-only track (e.g., {call_id}_callee.mp3)"
    )
    mixed_s3_key: Optional[str] = Field(
        None,
        description="S3 object key for mixed mono track (e.g., {call_id}_mixed.mp3)"
    )
    split_created_at: Optional[datetime] = Field(
        None,
        description="Timestamp when split recordings were created (cache validation)"
    )


class CallRecord(Document):
    """
    Individual call record with full conversation history.

    Supports both:
    - Legacy campaign-based calls (campaign_id)
    - New queue-based calls (queue_id, recipient_id)

    Indexes:
    - geography_id: Query all calls for a geography
    - queue_id: Query all calls for a queue
    - recipient_id: Query all calls for a recipient
    - campaign_id: Legacy campaign queries
    - call_tracking.call_sid: Twilio webhook lookups
    - call_tracking.outcome: Filter by call result
    - call_outcome: Filter by detailed outcome
    - urgency_flagged: Query urgent cases for clinical review
    - is_test_call: Filter test calls
    - created_at: Sort by recency
    """

    # Parent references (new model)
    geography_id: Optional[str] = Field(
        default=None,
        description="Geography this call belongs to",
    )
    queue_id: Optional[str] = Field(
        default=None,
        description="CallQueue this call belongs to",
    )
    recipient_id: Optional[str] = Field(
        default=None,
        description="Recipient this call is for",
    )

    # Legacy reference (backward compatibility)
    campaign_id: Optional[PydanticObjectId] = Field(
        default=None,
        description="[Deprecated] Use queue_id instead",
    )

    # Call configuration
    call_type: CallType = Field(
        default=CallType.PATIENT_FEEDBACK,
        description="Type of call (patient_feedback, survey, etc.)",
    )
    flow_template_id: Optional[str] = Field(
        default=None,
        description="Flow template used for this call",
    )

    # Contact info (copied for record integrity)
    contact_phone: str = Field(..., description="E.164 format")
    contact_name: Optional[str] = Field(
        default=None,
        max_length=200,
        description="Contact's name",
    )
    contact_type: ContactType = Field(
        default=ContactType.UNKNOWN,
        description="Type of contact (patient, guardian, caregiver)",
    )
    language: str = Field(default="en", description="en, es, fr, ht")

    # Patient context (for guardian/caregiver calls)
    patient_name: Optional[str] = Field(
        default=None,
        max_length=200,
        description="Patient's name (for child/dependent calls)",
    )
    guardian_relation: Optional[str] = Field(
        default=None,
        max_length=50,
        description="Guardian's relation to patient (Father, Mother, etc.)",
    )

    # Event context (REQUIRED for proper AI conversation)
    event_info: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Event data: event_type, facility_name, visit_date, vaccine_name, etc.",
    )
    greeting_template: str = Field(
        default="default",
        description="Greeting template key (default, facility)",
    )

    # Legacy field alias (backward compatibility)
    @property
    def patient_phone(self) -> str:
        """Backward compatibility alias for contact_phone."""
        return self.contact_phone

    # Conversation data
    conversation_state: ConversationState = Field(default_factory=ConversationState)
    transcript: List[ConversationTurn] = Field(
        default_factory=list,
        description="Full conversation history with timestamps"
    )
    conversation_data: ConversationData = Field(
        default_factory=ConversationData,
        description="Extracted data from conversation",
    )

    # Legacy field alias (backward compatibility)
    @property
    def feedback(self) -> ConversationData:
        """Backward compatibility alias for conversation_data."""
        return self.conversation_data

    # Call outcome (new detailed enum)
    call_outcome: Optional[CallOutcome] = Field(
        default=None,
        description="Detailed call outcome",
    )

    # Urgency detection
    urgency_flagged: bool = Field(
        default=False,
        description="True if keywords detected: hospital, severe, can't breathe"
    )
    urgency_keywords_detected: List[str] = Field(default_factory=list)

    # Human callback request
    human_callback_requested: bool = Field(
        default=False,
        description="True if person requested human callback",
    )
    human_callback_reason: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Reason for callback request",
    )

    # Call tracking
    call_tracking: CallTracking = Field(default_factory=CallTracking)

    # Recording metadata (S3/MinIO)
    recording: Optional[RecordingMetadata] = Field(
        default=None,
        description="Call recording metadata (when recording_enabled=true)"
    )

    # English translation of non-English transcripts
    english_translation: Optional[EnglishTranslation] = Field(
        default=None,
        description="English translation of transcript for non-English calls"
    )

    # Test call flag
    is_test_call: bool = Field(
        default=False,
        description="True if this is a test call (not counted in stats)",
    )

    # Error context
    error_message: Optional[str] = Field(
        None,
        description="Detailed error for debugging (not shown to patients)"
    )

    # Audit
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "call_records"
        indexes = [
            "geography_id",
            "queue_id",
            "recipient_id",
            "campaign_id",
            "call_type",
            "call_outcome",
            "call_tracking.call_sid",
            "call_tracking.outcome",
            "urgency_flagged",
            "is_test_call",
            "created_at",
        ]

    class Config:
        json_schema_extra = {
            "example": {
                "geography_id": "507f1f77bcf86cd799439011",
                "queue_id": "507f1f77bcf86cd799439012",
                "recipient_id": "507f1f77bcf86cd799439013",
                "call_type": "patient_feedback",
                "contact_phone": "+50912345678",
                "contact_name": "Marie Joseph",
                "contact_type": "guardian",
                "language": "ht",
                "patient_name": "Jean Joseph",
                "call_outcome": "completed_full",
                "urgency_flagged": False,
                "is_test_call": False,
                "call_tracking": {
                    "call_sid": "CA1234567890abcdef",
                    "outcome": "completed_full",
                    "duration_seconds": 180
                },
                "conversation_data": {
                    "is_visit_confirmed": True,
                    "is_service_confirmed": True,
                    "overall_satisfaction": 8,
                }
            }
        }


# Import Campaign after CallRecord class definition for model_rebuild() to work
# This import must happen at runtime (not just type checking) so that Campaign
# is in the module's globals when Pydantic resolves the forward reference
from backend.app.models.campaign import Campaign  # noqa: F401, E402
