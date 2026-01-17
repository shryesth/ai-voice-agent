"""
Pydantic schemas for Campaign API requests and responses.

These schemas define the API contract for campaign endpoints.
"""

from pydantic import BaseModel, Field, validator
from datetime import datetime, time
from typing import Optional, List
from enum import Enum

from backend.app.models.campaign import CampaignState, DayOfWeek


class TimeWindowCreate(BaseModel):
    """Time window for campaign execution"""
    start_time: time
    end_time: time
    days_of_week: List[DayOfWeek] = Field(default_factory=lambda: list(DayOfWeek))

    class Config:
        json_schema_extra = {
            "example": {
                "start_time": "09:00:00",
                "end_time": "17:00:00",
                "days_of_week": ["monday", "tuesday", "wednesday", "thursday", "friday"]
            }
        }


class TimeWindowResponse(BaseModel):
    """Time window in API responses"""
    start_time: time
    end_time: time
    days_of_week: List[DayOfWeek]

    class Config:
        json_schema_extra = {
            "example": {
                "start_time": "09:00:00",
                "end_time": "17:00:00",
                "days_of_week": ["monday", "tuesday", "wednesday", "thursday", "friday"]
            }
        }


class CampaignConfigCreate(BaseModel):
    """Campaign configuration for creation/update"""
    max_concurrent_calls: int = Field(default=10, ge=1, le=50)
    time_windows: List[TimeWindowCreate] = Field(default_factory=list)
    patient_list: List[str] = Field(..., min_items=1)  # Required, at least one patient
    language_preference: str = Field(default="en", pattern="^(en|es|fr|ht)$")

    @validator('patient_list', each_item=True)
    def validate_phone_number(cls, v):
        """Validate E.164 phone number format"""
        import re
        if not re.match(r'^\+[1-9]\d{1,14}$', v):
            raise ValueError(f'Invalid E.164 phone number format. Expected: +12025551234, got: {v}')
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
                "patient_list": ["+12025551234", "+12025555678", "+13105559999"],
                "language_preference": "en"
            }
        }


class CampaignConfigResponse(BaseModel):
    """Campaign configuration in API responses"""
    max_concurrent_calls: int
    time_windows: List[TimeWindowResponse]
    patient_list: List[str]  # Hidden from User role in service layer
    language_preference: str

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


class CampaignStatsResponse(BaseModel):
    """Campaign statistics"""
    total_calls: int
    queued_count: int
    in_progress_count: int
    completed_count: int
    failed_count: int
    urgent_flagged_count: int

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


class CampaignCreate(BaseModel):
    """Request schema for creating a new campaign"""
    name: str = Field(..., min_length=1, max_length=200)
    config: CampaignConfigCreate

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Post-Vaccination Feedback - January 2026",
                "config": {
                    "max_concurrent_calls": 10,
                    "patient_list": ["+12025551234", "+12025555678"],
                    "language_preference": "en"
                }
            }
        }


class CampaignUpdate(BaseModel):
    """Request schema for updating campaign (all fields optional)"""
    name: Optional[str] = None
    config: Optional[CampaignConfigCreate] = None

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Updated Campaign Name",
                "config": {
                    "max_concurrent_calls": 15
                }
            }
        }


class CampaignResponse(BaseModel):
    """Response schema for campaign endpoints"""
    id: str
    geography_id: str
    name: str
    state: CampaignState
    config: CampaignConfigResponse
    stats: CampaignStatsResponse
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]

    class Config:
        json_schema_extra = {
            "example": {
                "id": "65b2c3d4e5f6g7h8i9j0k1l2",
                "geography_id": "65a1b2c3d4e5f6g7h8i9j0k1",
                "name": "Post-Vaccination Feedback - January 2026",
                "state": "active",
                "config": {
                    "max_concurrent_calls": 10,
                    "patient_list": ["+12025551234"],
                    "language_preference": "en",
                    "time_windows": []
                },
                "stats": {
                    "total_calls": 150,
                    "queued_count": 47,
                    "in_progress_count": 3,
                    "completed_count": 98,
                    "failed_count": 2,
                    "urgent_flagged_count": 5
                },
                "created_at": "2026-01-18T14:30:00Z",
                "updated_at": "2026-01-18T14:30:00Z",
                "started_at": "2026-01-18T15:00:00Z",
                "completed_at": None
            }
        }


class CampaignListResponse(BaseModel):
    """Response schema for campaign list endpoint"""
    total: int
    skip: int
    limit: int
    items: List[CampaignResponse]

    class Config:
        json_schema_extra = {
            "example": {
                "total": 15,
                "skip": 0,
                "limit": 50,
                "items": [{
                    "id": "65b2c3d4e5f6g7h8i9j0k1l2",
                    "geography_id": "65a1b2c3d4e5f6g7h8i9j0k1",
                    "name": "Post-Vaccination Feedback - January 2026",
                    "state": "active",
                    "stats": {
                        "total_calls": 150,
                        "queued_count": 47,
                        "completed_count": 98
                    },
                    "created_at": "2026-01-18T14:30:00Z"
                }]
            }
        }


class CampaignStateChangeResponse(BaseModel):
    """Response for campaign state transition endpoints"""
    id: str
    state: CampaignState
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    message: str

    class Config:
        json_schema_extra = {
            "example": {
                "id": "65b2c3d4e5f6g7h8i9j0k1l2",
                "state": "active",
                "started_at": "2026-01-18T15:00:00Z",
                "completed_at": None,
                "message": "Campaign started. Queue entries created for 150 patients."
            }
        }


class ExecutionWindow(BaseModel):
    """Next execution window for campaign"""
    starts_at: datetime
    ends_at: datetime

    class Config:
        json_schema_extra = {
            "example": {
                "starts_at": "2026-01-19T09:00:00Z",
                "ends_at": "2026-01-19T17:00:00Z"
            }
        }


class CampaignStatusResponse(BaseModel):
    """Response for campaign status endpoint"""
    campaign_id: str
    state: CampaignState
    stats: CampaignStatsResponse
    progress_percent: float
    estimated_completion: Optional[datetime]
    current_concurrency: int
    next_execution_window: Optional[ExecutionWindow]

    class Config:
        json_schema_extra = {
            "example": {
                "campaign_id": "65b2c3d4e5f6g7h8i9j0k1l2",
                "state": "active",
                "stats": {
                    "total_calls": 150,
                    "queued_count": 47,
                    "in_progress_count": 3,
                    "completed_count": 98,
                    "failed_count": 2,
                    "urgent_flagged_count": 5
                },
                "progress_percent": 65.3,
                "estimated_completion": "2026-01-18T18:45:00Z",
                "current_concurrency": 3,
                "next_execution_window": {
                    "starts_at": "2026-01-19T09:00:00Z",
                    "ends_at": "2026-01-19T17:00:00Z"
                }
            }
        }
