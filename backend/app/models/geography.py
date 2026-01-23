"""
Geography model with RetentionPolicy and ClarityConfig for regional organization.

This model represents geographic regions or operational units that contain call queues.
Each geography can have:
- Configurable data retention policies for compliance
- Clarity API integration configuration
- Timezone and language settings
"""

from beanie import Document, Indexed
from pydantic import BaseModel, Field
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from backend.app.models.enums import CallType


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


class ClarityConfig(BaseModel):
    """
    Clarity API integration configuration for this geography.

    Enables bidirectional sync with Clarity:
    - Pull: Fetch verification subjects to call
    - Push: Update verification status after calls
    """

    enabled: bool = Field(
        default=False,
        description="Whether Clarity integration is enabled",
    )
    api_url: str = Field(
        default="",
        description="Clarity API base URL",
    )
    api_key: Optional[str] = Field(
        default=None,
        description="Clarity API key (stored securely)",
    )
    organization_id: Optional[str] = Field(
        default=None,
        description="Clarity organization ID",
    )
    # Event type to CallType mapping
    event_type_mapping: Dict[str, str] = Field(
        default_factory=dict,
        description="Map Clarity event types to CallType values",
    )
    # Which event types to skip (NO_CALL events like TB, HIV)
    skip_event_types: List[str] = Field(
        default_factory=list,
        description="Event types that should not trigger calls",
    )
    # Sync settings
    auto_push_results: bool = Field(
        default=True,
        description="Automatically push results to Clarity after calls",
    )
    include_recording_url: bool = Field(
        default=True,
        description="Include recording URL in Clarity push",
    )
    default_country_code: str = Field(
        default="509",
        description="Default country code for phone number normalization (e.g., '509' for Haiti)",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "enabled": True,
                "api_url": "https://clarity.shifo.org/api/v1",
                "organization_id": "haiti-moh",
                "event_type_mapping": {
                    "Suivi des Enfants": "patient_feedback",
                    "Prenatal": "patient_feedback",
                },
                "skip_event_types": ["Cas de Tuberculose", "HIV/ARV"],
                "auto_push_results": True,
                "include_recording_url": True,
                "default_country_code": "509",
            }
        }


class Geography(Document):
    """
    Geographic region or operational unit containing call queues.

    Each geography represents a deployment region (e.g., Haiti, Honduras)
    with its own configuration for:
    - Clarity integration
    - Data retention
    - Timezone and language settings

    Indexes:
    - name: Fast lookup and filtering
    - region_code: Filter by region
    - is_active: Filter active geographies
    """

    name: Indexed(str, unique=True) = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    region_code: Optional[str] = Field(
        None,
        description="ISO 3166-1 alpha-2 country code or custom region identifier",
        max_length=20
    )

    # Timezone for time window calculations
    timezone: str = Field(
        default="UTC",
        description="IANA timezone identifier (e.g., 'America/Port-au-Prince')",
    )

    # Default language for this geography
    default_language: str = Field(
        default="en",
        description="Default language code (en, ht, fr, es)",
    )

    # Supported languages in this geography
    supported_languages: List[str] = Field(
        default_factory=lambda: ["en"],
        description="List of supported language codes",
    )

    # Clarity integration configuration
    clarity_config: ClarityConfig = Field(
        default_factory=ClarityConfig,
        description="Clarity API integration settings",
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

    # Active status
    is_active: bool = Field(
        default=True,
        description="Whether this geography is active",
    )

    # Audit timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    deleted_at: Optional[datetime] = Field(
        None,
        description="Soft delete timestamp for audit trail"
    )

    class Settings:
        name = "geographies"
        indexes = [
            "name",
            "region_code",
            "is_active",
        ]

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Haiti",
                "description": "Haiti Ministry of Health operations",
                "region_code": "HT",
                "timezone": "America/Port-au-Prince",
                "default_language": "ht",
                "supported_languages": ["ht", "fr", "en"],
                "clarity_config": {
                    "enabled": True,
                    "api_url": "https://clarity.shifo.org/api/v1",
                    "organization_id": "haiti-moh",
                    "auto_push_results": True,
                },
                "retention_policy": {
                    "retention_days": 2555,
                    "archival_destination": "s3://backups/haiti/",
                    "auto_purge_enabled": False,
                    "compliance_notes": "HIPAA requires 7-year retention"
                },
                "metadata": {
                    "contact_email": "ops-haiti@shifo.org"
                }
            }
        }
