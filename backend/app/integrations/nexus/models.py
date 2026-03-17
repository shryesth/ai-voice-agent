"""
Nexus HMIS API Models

Pydantic models for Nexus HMIS API requests and responses.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any

from pydantic import BaseModel, Field


class NexusAttribute(BaseModel):
    """Attribute key-value pair from Nexus eventInfo."""

    name: str
    value: str


class NexusVaccineDose(BaseModel):
    """Vaccine dose information from Nexus eventInfo."""

    name: str = Field(..., description="Vaccine name")
    administered: bool = Field(default=True, description="Whether dose was administered")


class NexusSptDocument(BaseModel):
    """SPT document reference from Nexus eventInfo."""

    name: str = Field(..., description="Document name")
    url: Optional[str] = Field(None, description="Document URL")
    image: Optional[str] = Field(None, description="Base64 encoded image")


class NexusEventInfo(BaseModel):
    """Event information from Nexus verification."""

    event_date: str = Field(..., alias="eventDate", description="Event date (YYYY-MM-DD)")
    event_facility: str = Field(..., alias="eventFacility", description="Facility name")
    event_type: str = Field(..., alias="eventType", description="Event type (e.g., vaccination)")
    attributes: List[NexusAttribute] = Field(default_factory=list)
    vaccine_doses: List[NexusVaccineDose] = Field(
        default_factory=list, alias="vaccineDoses"
    )
    spt_document_ids: List[NexusSptDocument] = Field(
        default_factory=list, alias="sptDocumentIds"
    )

    model_config = {"populate_by_name": True}


class NexusVerification(BaseModel):
    """Single verification record from Nexus API."""

    id: int = Field(..., description="Unique verification ID")
    status: int = Field(..., description="Status code (999 = pending)")
    can_be_changed: bool = Field(..., alias="canBeChanged", description="Whether verification can be modified")
    contact_client_spt_id: Optional[str] = Field(None, alias="contactClientSptId")
    contact_name: str = Field(..., alias="contactName", description="Contact person name")
    contact_gender: Optional[str] = Field(None, alias="contactGender", description="Gender: male, female")
    contact_phones: List[str] = Field(default_factory=list, alias="contactPhones")
    contact_phone_owner_name: Optional[str] = Field(None, alias="contactPhoneOwnerName")
    event_info: NexusEventInfo = Field(..., alias="eventInfo")
    recording_url: Optional[str] = Field(None, alias="recordingUrl")
    is_visit_confirmed: Optional[bool] = Field(None, alias="isVisitConfirmed")

    model_config = {"populate_by_name": True}

    @property
    def primary_phone(self) -> Optional[str]:
        """Get the primary phone number (first in list)."""
        return self.contact_phones[0] if self.contact_phones else None

    @property
    def vaccine_names(self) -> List[str]:
        """Get list of vaccine names."""
        return [
            dose.name
            for dose in self.event_info.vaccine_doses
            if dose.administered
        ]

    @property
    def vaccine_names_str(self) -> str:
        """Get comma-separated vaccine names for voice prompt."""
        names = self.vaccine_names
        if not names:
            return "vaccine"
        if len(names) == 1:
            return names[0]
        return ", ".join(names[:-1]) + " and " + names[-1]


class NexusPaginatedResponse(BaseModel):
    """Paginated response from Nexus API."""

    items: List[NexusVerification] = Field(default_factory=list)
    total: int = Field(default=0, description="Total number of items")
    page: int = Field(default=1, description="Current page number")
    page_size: int = Field(default=50, description="Items per page")
    pages: int = Field(default=0, description="Total number of pages")
    has_next: bool = Field(default=False, description="Whether there are more pages")
    has_previous: bool = Field(default=False, description="Whether there are previous pages")

    model_config = {"populate_by_name": True}


class NexusVerificationUpdate(BaseModel):
    """Request body for updating verification in Nexus."""

    status: int = Field(..., description="New status code (1=verified, 2=failed)")
    recording_url: Optional[str] = Field(None, alias="recordingUrl", description="URL to call recording")
    is_visit_confirmed: Optional[bool] = Field(None, alias="isVisitConfirmed", description="Whether visit was confirmed")

    model_config = {"populate_by_name": True, "by_alias": True}


class NexusQueueMetadata(BaseModel):
    """Schema for Nexus queue metadata stored in QueueConfig.metadata."""

    queue_type: str = Field(default="nexus", description="Must be 'nexus'")

    # Nexus API Configuration
    nexus_api_url: str = Field(..., description="Nexus API base URL")
    nexus_api_key: str = Field(..., description="Bearer token for authentication")
    nexus_environment: str = Field(..., description="Environment name: staging, haiti, honduras")

    # Sync Configuration
    sync_interval_seconds: int = Field(default=300, description="Sync frequency in seconds")
    date_from: Optional[str] = Field(None, description="Fixed start date filter (YYYY-MM-DD)")
    date_to: Optional[str] = Field(None, description="End date filter (YYYY-MM-DD), None = today")
    default_language: str = Field(default="en", description="Default language for calls")

    # Storage Configuration
    storage_prefix: Optional[str] = Field(None, description="Custom S3 prefix, defaults to queue_id")

    # Tracking (auto-updated)
    last_sync_at: Optional[datetime] = Field(None, description="Last successful sync timestamp")
    last_sync_status: Optional[str] = Field(None, description="Last sync status: success, error")
    last_sync_error: Optional[str] = Field(None, description="Last sync error message")
    total_synced_items: int = Field(default=0, description="Total items synced from Nexus")

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NexusQueueMetadata":
        """Create from queue metadata dictionary."""
        return cls(**data)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        data = self.model_dump()
        # Convert datetime to ISO string
        if data.get("last_sync_at"):
            data["last_sync_at"] = data["last_sync_at"].isoformat()
        return data
