"""Pydantic models for the mock client visit verification API."""

from __future__ import annotations

import datetime
from enum import IntEnum
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field


def to_camel(string: str) -> str:
    """Convert snake_case to camelCase."""
    components = string.split("_")
    return components[0] + "".join(x.title() for x in components[1:])


class CamelModel(BaseModel):
    """Base model with camelCase aliases."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )


class VerificationStatus(IntEnum):
    """Status values for client visit verification."""

    UNKNOWN = 999  # No status
    IN_PROGRESS = 1  # Not verified yet
    VALID = 2  # Valid
    NOT_VALID = 3  # Not valid
    NOT_REACHABLE = 4  # Not reachable

    @classmethod
    def can_be_updated(cls, status: int) -> bool:
        """Check if a status can be updated."""
        return status in (cls.UNKNOWN, cls.IN_PROGRESS)


class Attribute(CamelModel):
    """Visit attribute."""

    name: str
    value: str


class VaccineDose(CamelModel):
    """Vaccine dose information."""

    name: str
    administered: bool


class SptDocument(CamelModel):
    """SPT document reference."""

    name: str
    url: str
    image: str


class EventInfo(CamelModel):
    """Information about the client visit event."""

    event_date: datetime.date
    event_facility: str
    event_type: str
    attributes: list[Attribute] = Field(default_factory=list)
    vaccine_doses: list[VaccineDose] = Field(default_factory=list)
    spt_document_ids: list[SptDocument] = Field(default_factory=list)


class VerificationSubjectOutput(CamelModel):
    """Output model for a verification subject."""

    id: int
    status: VerificationStatus
    can_be_changed: bool
    contact_client_spt_id: str | None = None
    contact_name: str | None = None
    contact_gender: str | None = None
    contact_phone: str | None = None
    contact_phones: list[str] | None = None
    contact_phone_owner_name: str | None = None
    event_info: EventInfo
    recording_url: str | None = None
    is_visit_confirmed: bool | None = None


class VerificationSubjectInput(CamelModel):
    """Input model for updating a verification subject."""

    status: VerificationStatus | None = Field(
        default=None,
        description="Status of the subject: 999 - No status, 1 - Not verified yet, "
        "2 - Valid, 3 - Not valid, 4 - Not reachable",
    )
    recording_url: str | None = Field(
        default=None,
        description="Link to the audio recording used for verifying the visit",
    )
    is_visit_confirmed: bool | None = Field(
        default=None,
        description="Indicates whether the visit has been successfully confirmed",
    )


T = TypeVar("T")


class PaginatedResponse(CamelModel, Generic[T]):
    """Paginated response wrapper."""

    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int
    has_next: bool
    has_previous: bool
