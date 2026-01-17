"""
Pydantic schemas for Call API requests and responses.

These schemas define the API contract for call endpoints.
"""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum

from backend.app.models.call_record import (
    CallOutcome,
    ConversationStage
)


class TestScenario(str, Enum):
    """Test scenario types for simulated calls"""
    HAPPY_PATH = "happy_path"  # Full conversation, success
    WRONG_PERSON = "wrong_person"  # Caller not patient/guardian
    URGENT_KEYWORDS = "urgent_keywords"  # Simulate urgency detection
    NETWORK_FAILURE = "network_failure"  # Simulate mid-call disconnect
    SHORT_DURATION = "short_duration"  # Simulate <30s call


class TestCallRequest(BaseModel):
    """Request schema for test call initiation"""
    phone_number: str = Field(..., pattern=r'^\+[1-9]\d{1,14}$', description="E.164 format")
    language: str = Field(default="en", pattern="^(en|es|fr|ht)$")

    class Config:
        json_schema_extra = {
            "example": {
                "phone_number": "+12025551234",
                "language": "en"
            }
        }


class TestScenarioRequest(BaseModel):
    """Request schema for test scenario simulation"""
    phone_number: str = Field(..., pattern=r'^\+[1-9]\d{1,14}$')
    language: str = Field(default="en", pattern="^(en|es|fr|ht)$")
    scenario: TestScenario
    scenario_params: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        json_schema_extra = {
            "example": {
                "phone_number": "+12025551234",
                "language": "es",
                "scenario": "wrong_person",
                "scenario_params": {
                    "wrong_person_attempts": 2,
                    "offer_callback": True
                }
            }
        }


class TestCallResponse(BaseModel):
    """Response schema for test call initiation"""
    call_id: str
    status: str  # "queued" | "ringing" | "in-progress"
    phone_number: str
    language: str
    message: str
    scenario: Optional[str] = None  # For test scenario responses

    class Config:
        json_schema_extra = {
            "example": {
                "call_id": "65c3d4e5f6g7h8i9j0k1l2m3",
                "status": "queued",
                "phone_number": "+12025551234",
                "language": "en",
                "message": "Test call queued. Check status at /api/v1/calls/65c3d4e5f6g7h8i9j0k1l2m3"
            }
        }


class ConversationTurnResponse(BaseModel):
    """Conversation turn in API responses"""
    speaker: str  # "patient" | "ai"
    text: str
    timestamp: datetime
    language: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "speaker": "ai",
                "text": "Hello! This is a call from your healthcare provider.",
                "timestamp": "2026-01-18T15:00:10Z"
            }
        }


class ConversationStateResponse(BaseModel):
    """Conversation state in API responses"""
    current_stage: Optional[ConversationStage]
    completed_stages: List[ConversationStage]
    failed_stages: List[ConversationStage]
    stage_retry_counts: Dict[str, int]

    class Config:
        json_schema_extra = {
            "example": {
                "current_stage": "call_completion",
                "completed_stages": [
                    "greeting",
                    "language_selection",
                    "patient_verification",
                    "feedback_collection",
                    "urgency_detection"
                ],
                "failed_stages": [],
                "stage_retry_counts": {}
            }
        }


class FeedbackDataResponse(BaseModel):
    """Feedback data in API responses"""
    overall_satisfaction: Optional[int]
    specific_concerns: Optional[str]
    side_effects_reported: Optional[str]
    experience_quality: Optional[str]

    class Config:
        json_schema_extra = {
            "example": {
                "overall_satisfaction": 8,
                "specific_concerns": "Wait time was a bit long",
                "side_effects_reported": None,
                "experience_quality": "Good overall, staff was friendly"
            }
        }


class CallTrackingResponse(BaseModel):
    """Call tracking metadata in API responses"""
    call_sid: Optional[str]
    stream_sid: Optional[str]
    status: str
    outcome: Optional[CallOutcome]
    created_at: datetime
    started_at: Optional[datetime]
    ended_at: Optional[datetime]
    duration_seconds: Optional[int]

    class Config:
        json_schema_extra = {
            "example": {
                "call_sid": "CA1234567890abcdef",
                "stream_sid": "MZ9876543210fedcba",
                "status": "completed",
                "outcome": "success",
                "created_at": "2026-01-18T15:00:00Z",
                "started_at": "2026-01-18T15:00:05Z",
                "ended_at": "2026-01-18T15:03:25Z",
                "duration_seconds": 200
            }
        }


class CallRecordResponse(BaseModel):
    """Response schema for call record endpoints"""
    id: str
    campaign_id: str
    patient_phone: str  # Hidden from User role in service layer
    language: str
    conversation_state: ConversationStateResponse
    transcript: List[ConversationTurnResponse]
    feedback: FeedbackDataResponse
    urgency_flagged: bool
    urgency_keywords_detected: List[str]
    call_tracking: CallTrackingResponse
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        json_schema_extra = {
            "example": {
                "id": "65c3d4e5f6g7h8i9j0k1l2m3",
                "campaign_id": "65b2c3d4e5f6g7h8i9j0k1l2",
                "patient_phone": "+12025551234",
                "language": "en",
                "conversation_state": {
                    "current_stage": "call_completion",
                    "completed_stages": ["greeting", "language_selection"],
                    "failed_stages": [],
                    "stage_retry_counts": {}
                },
                "transcript": [],
                "feedback": {
                    "overall_satisfaction": 8,
                    "specific_concerns": None,
                    "side_effects_reported": None,
                    "experience_quality": None
                },
                "urgency_flagged": False,
                "urgency_keywords_detected": [],
                "call_tracking": {
                    "call_sid": "CA1234567890abcdef",
                    "status": "completed",
                    "outcome": "success",
                    "created_at": "2026-01-18T15:00:00Z",
                    "started_at": "2026-01-18T15:00:05Z",
                    "ended_at": "2026-01-18T15:03:25Z",
                    "duration_seconds": 200
                },
                "error_message": None,
                "created_at": "2026-01-18T15:00:00Z",
                "updated_at": "2026-01-18T15:03:30Z"
            }
        }


class CallListResponse(BaseModel):
    """Response schema for call list endpoint"""
    total: int
    skip: int
    limit: int
    items: List[CallRecordResponse]

    class Config:
        json_schema_extra = {
            "example": {
                "total": 42,
                "skip": 0,
                "limit": 50,
                "items": [
                    {
                        "id": "65c3d4e5f6g7h8i9j0k1l2m3",
                        "campaign_id": "65b2c3d4e5f6g7h8i9j0k1l2",
                        "patient_phone": "+12025551234",
                        "language": "en",
                        "urgency_flagged": False,
                        "call_tracking": {
                            "call_sid": "CA1234567890abcdef",
                            "status": "completed",
                            "outcome": "success"
                        },
                        "created_at": "2026-01-18T15:00:00Z"
                    }
                ]
            }
        }
