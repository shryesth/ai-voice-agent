"""
Geography model with RetentionPolicy for regional organization.

This model represents geographic regions or operational units that contain campaigns.
Each geography can have configurable data retention policies for compliance.
"""

from beanie import Document, Indexed
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Dict, Any


class RetentionPolicy(BaseModel):
    """
    Configurable data retention rules per geography for compliance.

    Default: Indefinite retention with audit trail.
    Override: Per-geography archival and purge rules.
    """

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
    compliance_notes: Optional[str] = Field(
        None,
        description="Regulatory requirements justifying retention policy"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "retention_days": 2555,  # 7 years for HIPAA
                "archival_destination": "s3://backups/us-east/",
                "auto_purge_enabled": False,
                "compliance_notes": "HIPAA requires 7-year retention (2555 days)"
            }
        }


class Geography(Document):
    """
    Geographic region or operational unit containing campaigns.

    Indexes:
    - name: Fast lookup and filtering
    - region_code: Filter by region
    """

    name: Indexed(str, unique=True) = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    region_code: Optional[str] = Field(
        None,
        description="ISO 3166-1 alpha-2 country code or custom region identifier",
        max_length=20
    )

    # Configurable retention policy
    retention_policy: RetentionPolicy = Field(
        default_factory=RetentionPolicy,
        description="Data retention rules for this geography"
    )

    # Metadata for operational tracking
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Custom key-value pairs for operational context"
    )

    # Audit timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    deleted_at: Optional[datetime] = Field(
        None,
        description="Soft delete timestamp for audit trail"
    )

    class Settings:
        name = "geographies"
        indexes = [
            "name",
            "region_code",
        ]

    class Config:
        json_schema_extra = {
            "example": {
                "name": "North America - East Coast",
                "description": "US East Coast operations covering NY, NJ, PA, MD",
                "region_code": "US-EAST",
                "retention_policy": {
                    "retention_days": 2555,
                    "archival_destination": "s3://backups/us-east/",
                    "auto_purge_enabled": False,
                    "compliance_notes": "HIPAA requires 7-year retention"
                },
                "metadata": {
                    "timezone": "America/New_York",
                    "primary_language": "en",
                    "contact_email": "ops-east@example.com"
                }
            }
        }
