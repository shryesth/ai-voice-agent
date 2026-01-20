"""
Pydantic schemas for Test Call API endpoints.
"""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Dict, Any, List

from backend.app.models.enums import (
    CallType,
    ContactType,
    CallOutcome,
)


class MockEventInfo(BaseModel):
    """Mock event info for test calls."""

    event_type: str = Field(default="Suivi des Enfants")
    event_category: str = Field(default="child_vaccination")
    confirmation_message_key: str = Field(default="child_vaccination_generic")
    event_date: Optional[str] = None
    facility_name: str = Field(default="Test Clinic")
    vaccines: List[Dict[str, Any]] = Field(default_factory=list)
    requires_side_effects: bool = Field(default=False)


class TestCallRequest(BaseModel):
    """Request schema for initiating a test call."""

    phone_number: str = Field(..., description="Phone number in E.164 format")
    geography_id: str = Field(..., description="Geography ID")
    call_type: CallType = Field(default=CallType.PATIENT_FEEDBACK)
    flow_template_id: Optional[str] = Field(default=None)
    language: str = Field(default="en", description="Language code (en, ht, fr, es)")
    contact_name: str = Field(default="Test User")
    contact_type: ContactType = Field(default=ContactType.PATIENT)
    patient_name: Optional[str] = Field(default=None, description="Patient name for guardian/caregiver calls")
    event_info: Optional[MockEventInfo] = Field(default=None, description="Mock event data")


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
    clarity_sync_enabled: bool
    last_clarity_sync: Optional[str]
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


class SyncClarityRequest(BaseModel):
    """Request schema for manual Clarity sync."""

    direction: str = Field(
        default="both",
        description="Sync direction: pull, push, or both",
    )
    max_count: int = Field(default=100, ge=1, le=1000)


class SyncClarityResponse(BaseModel):
    """Response schema for Clarity sync."""

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
