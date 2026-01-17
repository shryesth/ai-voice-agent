"""
Pydantic schemas for Geography API requests and responses.

These schemas define the API contract for geography endpoints.
"""

from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from typing import Optional, Dict, Any


class RetentionPolicyCreate(BaseModel):
    """Retention policy configuration for geography creation/update"""
    retention_days: Optional[int] = Field(
        None,
        description="Days to retain data before archival (None = indefinite)"
    )
    archival_destination: Optional[str] = Field(
        None,
        description="Storage location for archived data (S3 bucket, MinIO path, etc.)"
    )
    auto_purge_enabled: bool = Field(
        default=False,
        description="Automatically delete data after retention period expires"
    )
    compliance_notes: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "retention_days": 2555,
                "archival_destination": "s3://backups/us-east/",
                "auto_purge_enabled": False,
                "compliance_notes": "HIPAA requires 7-year retention (2555 days)"
            }
        }


class RetentionPolicyResponse(RetentionPolicyCreate):
    """Retention policy in API responses (same as create)"""
    model_config = ConfigDict(from_attributes=True)


class GeographyCreate(BaseModel):
    """Request schema for creating a new geography"""
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    region_code: Optional[str] = Field(None, max_length=20)
    retention_policy: RetentionPolicyCreate = Field(default_factory=RetentionPolicyCreate)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        json_schema_extra = {
            "example": {
                "name": "North America - East Coast",
                "description": "US East Coast operations covering NY, NJ, PA, MD",
                "region_code": "US-EAST",
                "retention_policy": {
                    "retention_days": 2555,
                    "compliance_notes": "HIPAA requires 7-year retention"
                },
                "metadata": {
                    "timezone": "America/New_York",
                    "primary_language": "en"
                }
            }
        }


class GeographyUpdate(BaseModel):
    """Request schema for updating geography (all fields optional)"""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    region_code: Optional[str] = None
    retention_policy: Optional[RetentionPolicyCreate] = None
    metadata: Optional[Dict[str, Any]] = None

    class Config:
        json_schema_extra = {
            "example": {
                "description": "Updated description",
                "retention_policy": {
                    "retention_days": 3650,
                    "compliance_notes": "Extended to 10 years per new regulation"
                }
            }
        }


class GeographyResponse(BaseModel):
    """Response schema for geography endpoints"""
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: Optional[str]
    region_code: Optional[str]
    retention_policy: RetentionPolicyResponse
    metadata: Dict[str, Any]
    created_at: datetime
    updated_at: datetime


class GeographyListResponse(BaseModel):
    """Response schema for geography list endpoint"""
    total: int
    skip: int
    limit: int
    items: list[GeographyResponse]

    class Config:
        json_schema_extra = {
            "example": {
                "total": 42,
                "skip": 0,
                "limit": 50,
                "items": [
                    {
                        "id": "65a1b2c3d4e5f6g7h8i9j0k1",
                        "name": "North America - East Coast",
                        "region_code": "US-EAST",
                        "retention_policy": {"retention_days": 2555},
                        "metadata": {},
                        "created_at": "2026-01-18T14:30:00Z",
                        "updated_at": "2026-01-18T14:30:00Z"
                    }
                ]
            }
        }
