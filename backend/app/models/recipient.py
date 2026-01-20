"""
Recipient model for call queue entries.

Replaces QueueEntry with richer context including:
- Contact type handling (patient, guardian, caregiver)
- Event info from Clarity
- Detailed call timeline tracking
- Clarity sync status
"""

from beanie import Document, Link
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List, Dict, Any

from backend.app.models.enums import (
    CallType,
    ContactType,
    ExternalSource,
    RecipientStatus,
    CallOutcome,
    FailureReason,
    EventCategory,
    SyncStatus,
)
from backend.app.models.call_queue import CallQueue


class ClarityEventInfo(BaseModel):
    """
    Event info from Clarity - determines confirmation message.

    The event_type from Clarity is mapped to an EventCategory which
    determines which confirmation message to use in the call flow.
    """

    clarity_verification_id: str = Field(
        ...,
        description="Unique ID from Clarity for this verification",
    )
    event_type: str = Field(
        ...,
        description="Raw event type from Clarity (e.g., 'Suivi des Enfants')",
    )
    event_category: EventCategory = Field(
        default=EventCategory.OTHER,
        description="Mapped category for flow handling",
    )
    confirmation_message_key: str = Field(
        default="generic",
        description="Key for confirmation message (e.g., 'child_vaccination_rr1')",
    )
    event_date: Optional[datetime] = Field(
        default=None,
        description="Date of the health event",
    )
    facility_name: Optional[str] = Field(
        default=None,
        description="Name of the health facility",
    )
    facility_id: Optional[str] = Field(
        default=None,
        description="Clarity ID of the health facility",
    )
    attributes: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional attributes from Clarity",
    )
    vaccines: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Vaccine information for vaccination events",
    )
    requires_side_effects: bool = Field(
        default=False,
        description="True for vaccination events to check side effects",
    )
    requires_satisfaction: bool = Field(
        default=True,
        description="Whether to collect satisfaction rating",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "clarity_verification_id": "cv-12345",
                "event_type": "Suivi des Enfants (moins de 5 ans)",
                "event_category": "child_vaccination",
                "confirmation_message_key": "child_vaccination_rr1",
                "event_date": "2026-01-15T10:00:00Z",
                "facility_name": "Centre de Santé Port-au-Prince",
                "vaccines": [{"name": "Rougeole rubéole 1", "dose": 1}],
                "requires_side_effects": True,
            }
        }


class CallAttempt(BaseModel):
    """
    Single call attempt in timeline.

    Tracks each call made to this recipient with outcome details.
    """

    attempt_number: int = Field(..., ge=1)
    call_record_id: str = Field(
        ...,
        description="Reference to CallRecord document",
    )
    outcome: CallOutcome
    failure_reason: Optional[FailureReason] = None
    duration_seconds: Optional[int] = Field(
        default=None,
        ge=0,
        description="Call duration in seconds",
    )
    started_at: datetime
    ended_at: Optional[datetime] = None
    notes: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Human-readable notes (e.g., 'Reached voicemail')",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "attempt_number": 1,
                "call_record_id": "507f1f77bcf86cd799439011",
                "outcome": "no_answer",
                "failure_reason": "no_answer",
                "started_at": "2026-01-21T10:00:00Z",
                "ended_at": "2026-01-21T10:00:30Z",
                "notes": "No answer after 30 seconds",
            }
        }


class ConversationResult(BaseModel):
    """
    Results extracted from the conversation.

    Used for Clarity sync and reporting.
    """

    is_visit_confirmed: Optional[bool] = Field(
        default=None,
        description="Whether the visit was confirmed",
    )
    is_service_confirmed: Optional[bool] = Field(
        default=None,
        description="Whether the specific service was confirmed",
    )
    satisfaction_rating: Optional[int] = Field(
        default=None,
        ge=1,
        le=10,
        description="Satisfaction rating (1-10)",
    )
    side_effects_reported: Optional[str] = Field(
        default=None,
        description="Any side effects reported",
    )
    has_side_effects: Optional[bool] = Field(
        default=None,
        description="Whether side effects were reported",
    )
    specific_concerns: Optional[str] = Field(
        default=None,
        description="Any specific concerns mentioned",
    )
    additional_notes: Optional[str] = Field(
        default=None,
        description="Additional notes from conversation",
    )
    extracted_data: Dict[str, Any] = Field(
        default_factory=dict,
        description="All extracted data from conversation",
    )


class Recipient(Document):
    """
    Person/record to be called from a queue.

    Replaces QueueEntry with richer context including:
    - Contact type (patient, guardian, caregiver)
    - Event info from Clarity
    - Detailed call timeline
    - Clarity sync status

    Supports multiple call attempts with detailed tracking.
    """

    queue_id: Link[CallQueue]

    # Source tracking
    external_source: ExternalSource = Field(default=ExternalSource.MANUAL)
    external_id: Optional[str] = Field(
        default=None,
        description="External identifier (clarity_verification_id for Clarity)",
    )

    # Contact information
    contact_phone: str = Field(
        ...,
        description="Phone number in E.164 format",
    )
    contact_name: Optional[str] = Field(
        default=None,
        max_length=200,
    )
    contact_type: ContactType = Field(default=ContactType.UNKNOWN)
    language: str = Field(
        default="en",
        description="Preferred language (en, ht, fr, es)",
    )

    # Patient context (when calling guardian/caregiver)
    patient_name: Optional[str] = Field(
        default=None,
        max_length=200,
        description="Patient's name (for child/dependent calls)",
    )
    patient_relation: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Relation to patient (e.g., 'Father', 'Caregiver')",
    )
    patient_age: Optional[int] = Field(
        default=None,
        ge=0,
        le=150,
        description="Patient's age in years",
    )

    # Event context (from Clarity or manual)
    event_info: Optional[ClarityEventInfo] = Field(
        default=None,
        description="Event context for patient feedback calls",
    )

    # Call configuration (overrides queue defaults)
    call_type: Optional[CallType] = Field(
        default=None,
        description="Override queue's call_type",
    )
    flow_template_id: Optional[str] = Field(
        default=None,
        description="Override queue's flow_template_id",
    )

    # Processing state
    status: RecipientStatus = Field(default=RecipientStatus.PENDING)
    priority: int = Field(
        default=0,
        description="Higher = processed first",
    )

    # Retry tracking
    retry_count: int = Field(default=0, ge=0)
    last_failure_reason: Optional[FailureReason] = None
    next_retry_at: Optional[datetime] = Field(
        default=None,
        description="When to retry (for RETRYING status)",
    )

    # Call timeline (all attempts)
    call_attempts: List[CallAttempt] = Field(
        default_factory=list,
        description="History of all call attempts",
    )
    current_call_record_id: Optional[str] = Field(
        default=None,
        description="ID of current/latest call record",
    )

    # DLQ tracking
    moved_to_dlq: bool = Field(default=False)
    dlq_reason: Optional[str] = Field(
        default=None,
        max_length=500,
    )
    dlq_moved_at: Optional[datetime] = None

    # Conversation results (for Clarity sync)
    conversation_result: ConversationResult = Field(
        default_factory=ConversationResult,
    )

    # Urgency flagging
    urgency_flagged: bool = Field(default=False)
    urgency_keywords_detected: List[str] = Field(default_factory=list)

    # Human callback request
    human_callback_requested: bool = Field(default=False)
    human_callback_reason: Optional[str] = Field(
        default=None,
        max_length=500,
    )

    # Clarity sync status
    sync_status: SyncStatus = Field(default=SyncStatus.PENDING)
    last_synced_at: Optional[datetime] = None
    sync_error: Optional[str] = Field(
        default=None,
        max_length=500,
    )

    # Recording URL (for Clarity sync)
    recording_url: Optional[str] = Field(
        default=None,
        description="Presigned URL for call recording",
    )

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    first_attempted_at: Optional[datetime] = Field(
        default=None,
        description="When first call attempt was made",
    )
    completed_at: Optional[datetime] = Field(
        default=None,
        description="When recipient reached terminal status",
    )

    class Settings:
        name = "recipients"
        indexes = [
            "queue_id",
            "status",
            "contact_phone",
            "external_source",
            "external_id",
            "next_retry_at",
            "priority",
            "sync_status",
            "created_at",
        ]

    class Config:
        json_schema_extra = {
            "example": {
                "contact_phone": "+50912345678",
                "contact_name": "Marie Joseph",
                "contact_type": "guardian",
                "language": "ht",
                "patient_name": "Jean Joseph",
                "patient_relation": "Mother",
                "external_source": "clarity",
                "external_id": "cv-12345",
                "status": "pending",
                "priority": 0,
                "event_info": {
                    "clarity_verification_id": "cv-12345",
                    "event_type": "Suivi des Enfants",
                    "event_category": "child_vaccination",
                    "confirmation_message_key": "child_vaccination_rr1",
                    "facility_name": "Centre de Santé",
                    "requires_side_effects": True,
                },
            }
        }


def determine_contact_type(
    patient_age: Optional[int],
    contact_name: Optional[str],
    patient_name: Optional[str],
    phone_owner_name: Optional[str] = None,
) -> ContactType:
    """
    Determine contact type based on available information.

    Rules:
    - If patient.age < 18 → GUARDIAN
    - If contact_phone_owner_name != patient_name → CAREGIVER
    - Otherwise → PATIENT
    """
    if patient_age is not None and patient_age < 18:
        return ContactType.GUARDIAN

    if phone_owner_name and patient_name:
        if phone_owner_name.lower() != patient_name.lower():
            return ContactType.CAREGIVER

    if contact_name and patient_name:
        if contact_name.lower() != patient_name.lower():
            return ContactType.CAREGIVER

    return ContactType.PATIENT
