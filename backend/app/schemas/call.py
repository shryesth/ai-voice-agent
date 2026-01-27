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
    current_stage: Optional[str]
    completed_stages: List[str]
    failed_stages: List[str]
    stage_retry_counts: Dict[str, int]

    class Config:
        arbitrary_types_allowed = True
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


class RecordingMetadataResponse(BaseModel):
    """Recording metadata in API responses"""
    recording_url: Optional[str]
    s3_object_key: Optional[str]
    duration_seconds: Optional[int]
    file_size_bytes: Optional[int]
    sample_rate: int
    num_channels: int
    uploaded_at: Optional[datetime]

    class Config:
        json_schema_extra = {
            "example": {
                "recording_url": "https://s3.us-east-1.amazonaws.com/voice-recordings/recordings/campaign123/2026/01/call456.wav",
                "s3_object_key": "recordings/campaign123/2026/01/call456.wav",
                "duration_seconds": 180,
                "file_size_bytes": 8640000,
                "sample_rate": 24000,
                "num_channels": 1,
                "uploaded_at": "2026-01-18T15:03:30Z"
            }
        }


class SplitRecordingResponse(BaseModel):
    """Response schema for split recording endpoint"""
    # If already split (cached)
    caller_url: Optional[str] = None
    callee_url: Optional[str] = None
    mixed_url: Optional[str] = None
    dual_url: Optional[str] = None
    split_created_at: Optional[datetime] = None

    # If splitting in progress
    task_id: Optional[str] = None
    status: Optional[str] = None  # "processing" or "completed"
    message: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "caller_url": "https://minio.example.com/voice-recordings/recordings/campaign123/2026/01/call456_caller.mp3?signature=...",
                "callee_url": "https://minio.example.com/voice-recordings/recordings/campaign123/2026/01/call456_callee.mp3?signature=...",
                "mixed_url": "https://minio.example.com/voice-recordings/recordings/campaign123/2026/01/call456_mixed.mp3?signature=...",
                "dual_url": "https://minio.example.com/voice-recordings/recordings/campaign123/2026/01/call456_dual.mp3?signature=...",
                "split_created_at": "2026-01-19T12:00:00Z"
            }
        }


class TranslatedMessageResponse(BaseModel):
    """Translated message entry in API responses"""
    speaker: str
    original_text: str
    english_text: str
    timestamp: datetime

    class Config:
        json_schema_extra = {
            "example": {
                "speaker": "patient",
                "original_text": "Wi, se mwen menm",
                "english_text": "Yes, it's me",
                "timestamp": "2026-01-21T06:10:05Z"
            }
        }


class EnglishTranslationResponse(BaseModel):
    """English translation of non-English transcript in API responses"""
    status: str  # pending, in_progress, completed, failed
    source_language: Optional[str]
    messages: List[TranslatedMessageResponse]
    completed_at: Optional[datetime]
    attempts: int
    error: Optional[str]

    class Config:
        json_schema_extra = {
            "example": {
                "status": "completed",
                "source_language": "ht",
                "messages": [
                    {
                        "speaker": "ai",
                        "original_text": "Bonjou, mwen se yon Asistan AI...",
                        "english_text": "Hello, I am an AI Assistant...",
                        "timestamp": "2026-01-21T06:10:00Z"
                    }
                ],
                "completed_at": "2026-01-21T06:12:00Z",
                "attempts": 1,
                "error": None
            }
        }


class CallRecordResponse(BaseModel):
    """Response schema for call record endpoints"""
    id: str
    queue_id: Optional[str] = None
    patient_phone: str  # Hidden from User role in service layer
    language: str
    conversation_state: ConversationStateResponse
    transcript: List[ConversationTurnResponse]
    feedback: FeedbackDataResponse
    urgency_flagged: bool
    urgency_keywords_detected: List[str]
    call_tracking: CallTrackingResponse
    recording: Optional[RecordingMetadataResponse] = None
    english_translation: Optional[EnglishTranslationResponse] = None
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        json_schema_extra = {
            "example": {
                "id": "65c3d4e5f6g7h8i9j0k1l2m3",
                "queue_id": "65b2c3d4e5f6g7h8i9j0k1l2",
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
                        "queue_id": "65b2c3d4e5f6g7h8i9j0k1l2",
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
