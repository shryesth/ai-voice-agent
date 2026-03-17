"""
Pydantic schemas for Recipient API endpoints.
"""

import re
from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import Optional, List, Dict, Any

from backend.app.models.enums import (
    ContactType,
    RecipientStatus,
    CallOutcome,
    FailureReason,
    ExternalSource,
    EventCategory,
    SyncStatus,
    UserRole,
)


class NexusEventInfoSchema(BaseModel):
    """Event info from Nexus."""

    nexus_verification_id: str
    event_type: str
    event_category: str
    confirmation_message_key: str
    event_date: Optional[datetime] = None
    facility_name: Optional[str] = None
    facility_id: Optional[str] = None
    attributes: Dict[str, Any] = {}
    vaccines: List[Dict[str, Any]] = []
    requires_side_effects: bool = False
    requires_satisfaction: bool = True


class CallAttemptSchema(BaseModel):
    """Single call attempt in timeline."""

    attempt_number: int
    call_record_id: str
    outcome: str
    failure_reason: Optional[str] = None
    duration_seconds: Optional[int] = None
    started_at: datetime
    ended_at: Optional[datetime] = None
    notes: Optional[str] = None


class ConversationResultSchema(BaseModel):
    """Results extracted from conversation."""

    is_visit_confirmed: Optional[bool] = None
    is_service_confirmed: Optional[bool] = None
    satisfaction_rating: Optional[int] = None
    side_effects_reported: Optional[str] = None
    has_side_effects: Optional[bool] = None
    specific_concerns: Optional[str] = None
    additional_notes: Optional[str] = None
    extracted_data: Dict[str, Any] = {}


# Request schemas
class RecipientCreate(BaseModel):
    """Request schema for creating a recipient."""

    contact_phone: str = Field(..., description="Phone number in E.164 format")
    contact_name: Optional[str] = Field(default=None, max_length=200)
    contact_type: ContactType = Field(default=ContactType.UNKNOWN)
    language: str = Field(default="en")
    patient_name: Optional[str] = Field(default=None, max_length=200)
    patient_relation: Optional[str] = Field(default=None, max_length=100)
    patient_age: Optional[int] = Field(default=None, ge=0, le=150)
    priority: int = Field(default=0)
    event_info: Optional[NexusEventInfoSchema] = None

    @field_validator("contact_phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        """Validate phone number is in E.164 format."""
        if not re.match(r"^\+[1-9]\d{6,14}$", v):
            raise ValueError("Phone must be in E.164 format (+[country][number])")
        return v


class RecipientUpdate(BaseModel):
    """Request schema for updating a recipient."""

    contact_name: Optional[str] = Field(default=None, max_length=200)
    language: Optional[str] = None
    priority: Optional[int] = None


class RecipientBulkCreate(BaseModel):
    """Request schema for bulk creating recipients."""

    recipients: List[RecipientCreate]


class DLQRetryRequest(BaseModel):
    """Request schema for retrying DLQ entry."""

    reset_retry_count: bool = Field(
        default=False,
        description="Reset retry count to 0",
    )


class SkipRecipientRequest(BaseModel):
    """Request schema for skipping a recipient."""

    reason: Optional[str] = Field(default=None, max_length=500)


# Response schemas
class RecipientResponse(BaseModel):
    """Response schema for a recipient."""

    id: str
    queue_id: str
    external_source: str
    external_id: Optional[str]
    contact_phone: str
    contact_name: Optional[str]
    contact_type: str
    language: str
    patient_name: Optional[str]
    patient_relation: Optional[str]
    patient_age: Optional[int]
    event_info: Optional[NexusEventInfoSchema]
    status: str
    priority: int
    retry_count: int
    last_failure_reason: Optional[str]
    next_retry_at: Optional[datetime]
    call_attempts: List[CallAttemptSchema]
    current_call_record_id: Optional[str]
    conversation_result: ConversationResultSchema
    urgency_flagged: bool
    human_callback_requested: bool
    human_callback_reason: Optional[str]
    sync_status: str
    last_synced_at: Optional[datetime]
    moved_to_dlq: bool
    dlq_reason: Optional[str]
    dlq_moved_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    first_attempted_at: Optional[datetime]
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True


class RecipientListResponse(BaseModel):
    """Response schema for listing recipients."""

    items: List[RecipientResponse]
    total: int
    skip: int
    limit: int


class RecipientTimelineResponse(BaseModel):
    """Response schema for recipient call timeline."""

    recipient_id: str
    contact_phone: str
    contact_name: Optional[str]
    status: str
    timeline: List[CallAttemptSchema]


class DLQListResponse(BaseModel):
    """Response schema for DLQ listing."""

    items: List[RecipientResponse]
    total: int
    skip: int
    limit: int


class RecipientSummaryResponse(BaseModel):
    """Response schema for recipient summary stats."""

    queue_id: str
    total: int
    by_status: Dict[str, int]
    urgent_count: int
    callback_requested_count: int


def recipient_to_response(
    recipient,
    user_role: UserRole = UserRole.ADMIN,
) -> RecipientResponse:
    """Convert Recipient model to response schema."""

    # Privacy filtering for non-admin users
    contact_phone = recipient.contact_phone
    if user_role == UserRole.USER:
        # Redact phone number for non-admin users
        if contact_phone and len(contact_phone) > 4:
            contact_phone = contact_phone[:3] + "****" + contact_phone[-2:]

    # Convert event_info
    event_info = None
    if recipient.event_info:
        event_info = NexusEventInfoSchema(
            nexus_verification_id=recipient.event_info.nexus_verification_id,
            event_type=recipient.event_info.event_type,
            event_category=recipient.event_info.event_category.value if hasattr(recipient.event_info.event_category, 'value') else str(recipient.event_info.event_category),
            confirmation_message_key=recipient.event_info.confirmation_message_key,
            event_date=recipient.event_info.event_date,
            facility_name=recipient.event_info.facility_name,
            facility_id=recipient.event_info.facility_id,
            attributes=recipient.event_info.attributes,
            vaccines=recipient.event_info.vaccines,
            requires_side_effects=recipient.event_info.requires_side_effects,
            requires_satisfaction=recipient.event_info.requires_satisfaction,
        )

    # Convert call attempts
    call_attempts = [
        CallAttemptSchema(
            attempt_number=attempt.attempt_number,
            call_record_id=attempt.call_record_id,
            outcome=attempt.outcome.value if hasattr(attempt.outcome, 'value') else str(attempt.outcome),
            failure_reason=attempt.failure_reason.value if attempt.failure_reason and hasattr(attempt.failure_reason, 'value') else None,
            duration_seconds=attempt.duration_seconds,
            started_at=attempt.started_at,
            ended_at=attempt.ended_at,
            notes=attempt.notes,
        )
        for attempt in recipient.call_attempts
    ]

    # Convert conversation result
    conversation_result = ConversationResultSchema(
        is_visit_confirmed=recipient.conversation_result.is_visit_confirmed,
        is_service_confirmed=recipient.conversation_result.is_service_confirmed,
        satisfaction_rating=recipient.conversation_result.satisfaction_rating,
        side_effects_reported=recipient.conversation_result.side_effects_reported,
        has_side_effects=recipient.conversation_result.has_side_effects,
        specific_concerns=recipient.conversation_result.specific_concerns,
        additional_notes=getattr(recipient.conversation_result, 'additional_notes', None),
        extracted_data=recipient.conversation_result.extracted_data,
    )

    return RecipientResponse(
        id=str(recipient.id),
        queue_id=str(recipient.queue_id),
        external_source=recipient.external_source.value,
        external_id=recipient.external_id,
        contact_phone=contact_phone,
        contact_name=recipient.contact_name,
        contact_type=recipient.contact_type.value,
        language=recipient.language,
        patient_name=recipient.patient_name,
        patient_relation=recipient.patient_relation,
        patient_age=recipient.patient_age,
        event_info=event_info,
        status=recipient.status.value,
        priority=recipient.priority,
        retry_count=recipient.retry_count,
        last_failure_reason=recipient.last_failure_reason.value if recipient.last_failure_reason else None,
        next_retry_at=recipient.next_retry_at,
        call_attempts=call_attempts,
        current_call_record_id=recipient.current_call_record_id,
        conversation_result=conversation_result,
        urgency_flagged=recipient.urgency_flagged,
        human_callback_requested=recipient.human_callback_requested,
        human_callback_reason=recipient.human_callback_reason,
        sync_status=recipient.sync_status.value,
        last_synced_at=recipient.last_synced_at,
        moved_to_dlq=recipient.moved_to_dlq,
        dlq_reason=recipient.dlq_reason,
        dlq_moved_at=recipient.dlq_moved_at,
        created_at=recipient.created_at,
        updated_at=recipient.updated_at,
        first_attempted_at=recipient.first_attempted_at,
        completed_at=recipient.completed_at,
    )
