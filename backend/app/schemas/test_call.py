"""
Pydantic schemas for Test Call API endpoints.
"""

from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import Optional, Dict, Any, List

from backend.app.models.enums import (
    CallType,
    ContactType,
    CallOutcome,
)


class EventInfo(BaseModel):
    """
    Event information for patient feedback calls.

    This data is REQUIRED for calls - it provides context for the AI conversation
    including what service was provided, when, and where.
    """
    # Event classification
    event_type: str = Field(..., description="Event type (e.g., 'Child Vaccination Follow-up', 'Prenatal Care')")
    event_category: str = Field(..., description="Category (e.g., 'child_vaccination', 'prenatal', 'maternity')")
    confirmation_message_key: str = Field(
        ...,
        description="Key for confirmation message template (e.g., 'child_vaccination_penta1')"
    )

    # Visit details
    event_date: str = Field(..., description="Date of visit in human-readable format (e.g., 'January 18th, 2026')")
    facility_name: str = Field(..., description="Name of the health facility/dispensary")

    # Service/vaccine details
    vaccine_name: Optional[str] = Field(None, description="Vaccine name for vaccination events")
    service_name: Optional[str] = Field(None, description="Service name for non-vaccination events")
    vaccines: List[Dict[str, Any]] = Field(default_factory=list, description="List of vaccines administered")

    # Flow configuration
    requires_side_effects: bool = Field(default=True, description="Whether to ask about side effects (vaccines only)")
    requires_satisfaction: bool = Field(default=True, description="Whether to ask for satisfaction rating")
    is_child_event: bool = Field(default=False, description="Whether this is a child health event")

    # Child-specific fields
    child_name: Optional[str] = Field(None, description="Child's name for child health events")


class TestCallRequest(BaseModel):
    """
    Request schema for initiating a test call.

    IMPORTANT: event_info is REQUIRED - calls cannot be initiated without
    proper event context for the AI conversation.
    """
    # Required fields
    phone_number: str = Field(..., description="Phone number in E.164 format")
    geography_id: str = Field(..., description="Geography ID")
    event_info: EventInfo = Field(..., description="Event data - REQUIRED for AI conversation context")

    # Patient/contact information
    patient_name: str = Field(..., description="Patient's full name")
    contact_name: str = Field(..., description="Contact/guardian name (person being called)")
    contact_type: ContactType = Field(default=ContactType.PATIENT, description="Type of contact")
    guardian_relation: Optional[str] = Field(None, description="Guardian's relation to patient (for child events)")

    # Call configuration
    call_type: CallType = Field(default=CallType.PATIENT_FEEDBACK)
    language: str = Field(default="en", description="Language code (en, ht, fr, es)")
    greeting_template: str = Field(default="default", description="Greeting template key")

    # Optional overrides
    flow_template_id: Optional[str] = Field(default=None)

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        if not v.startswith("+"):
            raise ValueError("Phone must be in E.164 format (starting with +)")
        if len(v) < 10:
            raise ValueError("Phone number too short")
        return v


class TestCallResponse(BaseModel):
    """Response schema for test call initiation."""

    call_id: str
    call_sid: Optional[str]
    status: str
    phone_number: str
    language: str
    call_type: str
    is_test_call: bool = True
    created_at: datetime


class ActiveTestCallResponse(BaseModel):
    """Response schema for active test call."""

    call_id: str
    call_sid: Optional[str]
    phone_number: str
    status: str
    call_type: str
    language: str
    duration_seconds: Optional[int]
    started_at: Optional[datetime]
    current_stage: Optional[str]


class ActiveTestCallListResponse(BaseModel):
    """Response schema for listing active test calls."""

    items: List[ActiveTestCallResponse]
    total: int


class CancelTestCallResponse(BaseModel):
    """Response schema for canceling a test call."""

    call_id: str
    status: str
    message: str


# Debug endpoints schemas
class QueueDebugResponse(BaseModel):
    """Response schema for queue debug info."""

    queue_id: str
    name: str
    state: str
    mode: str
    is_within_time_window: bool
    current_time_utc: str
    time_windows: List[Dict[str, Any]]
    nexus_sync_enabled: bool
    last_nexus_sync: Optional[str]
    pending_recipients: int
    calling_recipients: int
    retrying_recipients: int
    recent_failures: List[Dict[str, Any]]


class ForceProcessRequest(BaseModel):
    """Request schema for force processing."""

    max_recipients: int = Field(default=5, ge=1, le=50)


class ForceProcessResponse(BaseModel):
    """Response schema for force processing."""

    queue_id: str
    processed_count: int
    call_ids: List[str]
    message: str


class SyncNexusRequest(BaseModel):
    """Request schema for manual Nexus sync."""

    direction: str = Field(
        default="both",
        description="Sync direction: pull, push, or both",
    )
    max_count: int = Field(default=100, ge=1, le=1000)


class SyncNexusResponse(BaseModel):
    """Response schema for Nexus sync."""

    queue_id: str
    direction: str
    pulled_count: int
    pushed_count: int
    errors: List[str]
    message: str


class TriggerCallRequest(BaseModel):
    """Request schema for manually triggering a call."""

    bypass_time_window: bool = Field(
        default=True,
        description="Bypass time window restrictions",
    )


class TriggerCallResponse(BaseModel):
    """Response schema for triggered call."""

    recipient_id: str
    call_record_id: str
    status: str
    message: str
