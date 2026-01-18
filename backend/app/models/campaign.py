"""
Campaign model with state machine and queue configuration.

This model represents a patient feedback collection campaign with configurable
time windows, concurrency limits, and patient lists.
"""

from __future__ import annotations

from beanie import Document, Link
from pydantic import BaseModel, Field, validator
from datetime import datetime, time
from typing import Optional, List
from enum import Enum


class CampaignState(str, Enum):
    """Campaign lifecycle states"""
    DRAFT = "draft"          # Created but not started
    ACTIVE = "active"        # Running and processing calls
    PAUSED = "paused"        # Temporarily stopped
    COMPLETED = "completed"  # All calls processed
    CANCELLED = "cancelled"  # Manually terminated


class DayOfWeek(str, Enum):
    """Days when campaign can execute"""
    MONDAY = "monday"
    TUESDAY = "tuesday"
    WEDNESDAY = "wednesday"
    THURSDAY = "thursday"
    FRIDAY = "friday"
    SATURDAY = "saturday"
    SUNDAY = "sunday"


class TimeWindow(BaseModel):
    """UTC-based time window for campaign execution"""
    start_time: str = Field(..., description="UTC start time (HH:MM:SS)")
    end_time: str = Field(..., description="UTC end time (HH:MM:SS)")
    days_of_week: List[DayOfWeek] = Field(
        default_factory=lambda: list(DayOfWeek),
        description="Days when campaign can run"
    )

    @validator('start_time', 'end_time')
    def validate_time_format(cls, v):
        """Validate time string format (HH:MM:SS or HH:MM)"""
        import re
        if not re.match(r'^\d{2}:\d{2}(:\d{2})?$', v):
            raise ValueError(f'Invalid time format: {v}. Expected HH:MM:SS or HH:MM')
        # Parse and validate the time value
        try:
            parts = v.split(':')
            hour, minute = int(parts[0]), int(parts[1])
            second = int(parts[2]) if len(parts) > 2 else 0
            if not (0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59):
                raise ValueError(f'Invalid time value: {v}')
        except (ValueError, IndexError):
            raise ValueError(f'Invalid time format: {v}')
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "start_time": "09:00:00",
                "end_time": "17:00:00",
                "days_of_week": ["monday", "tuesday", "wednesday", "thursday", "friday"]
            }
        }


class CampaignConfig(BaseModel):
    """Campaign execution parameters"""
    max_concurrent_calls: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Maximum simultaneous calls (default: 10)"
    )
    time_windows: List[TimeWindow] = Field(
        default_factory=list,
        description="When campaign can execute (empty = always)"
    )
    patient_list: List[str] = Field(
        default_factory=list,
        description="E.164 formatted phone numbers"
    )
    language_preference: str = Field(
        default="en",
        description="Default language: en, es, fr, ht"
    )

    @validator('patient_list', each_item=True)
    def validate_phone_number(cls, v):
        """Validate E.164 phone number format"""
        import re
        if not re.match(r'^\+[1-9]\d{1,14}$', v):
            raise ValueError(f'Invalid E.164 phone number format. Expected: +12025551234, got: {v}')
        return v

    @validator('language_preference')
    def validate_language(cls, v):
        """Validate supported languages"""
        if v not in ['en', 'es', 'fr', 'ht']:
            raise ValueError(f'Unsupported language: {v}. Supported: en, es, fr, ht')
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "max_concurrent_calls": 10,
                "time_windows": [{
                    "start_time": "09:00:00",
                    "end_time": "17:00:00",
                    "days_of_week": ["monday", "tuesday", "wednesday", "thursday", "friday"]
                }],
                "patient_list": ["+12025551234", "+12025555678"],
                "language_preference": "en"
            }
        }


class CampaignStats(BaseModel):
    """Real-time campaign progress metrics"""
    total_calls: int = 0
    queued_count: int = 0
    in_progress_count: int = 0
    completed_count: int = 0
    failed_count: int = 0
    urgent_flagged_count: int = 0

    class Config:
        json_schema_extra = {
            "example": {
                "total_calls": 150,
                "queued_count": 47,
                "in_progress_count": 3,
                "completed_count": 98,
                "failed_count": 2,
                "urgent_flagged_count": 5
            }
        }


class Campaign(Document):
    """
    Patient feedback collection campaign with queue configuration.

    Indexes:
    - geography_id: Filter campaigns by region
    - state: Query active/paused campaigns
    - created_at: Sort by recency
    """

    name: str = Field(..., min_length=1, max_length=200)
    geography_id: Link[Geography]  # Reference to parent geography

    # Campaign configuration
    config: CampaignConfig = Field(default_factory=CampaignConfig)

    # State management
    state: CampaignState = Field(default=CampaignState.DRAFT)

    # Real-time statistics (updated by queue processor)
    stats: CampaignStats = Field(default_factory=CampaignStats)

    # Audit timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None

    class Settings:
        name = "campaigns"
        indexes = [
            "geography_id",
            "state",
            "created_at",
        ]

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Post-Vaccination Feedback - January 2026",
                "state": "active",
                "config": {
                    "max_concurrent_calls": 10,
                    "patient_list": ["+12025551234", "+12025555678"],
                    "language_preference": "en"
                },
                "stats": {
                    "total_calls": 150,
                    "queued_count": 47,
                    "completed_count": 98
                }
            }
        }


# Import Geography after Campaign class definition to resolve Link[Geography]
# This works with `from __future__ import annotations` which makes annotations lazy
from backend.app.models.geography import Geography

# Rebuild model to resolve forward references
Campaign.model_rebuild()
