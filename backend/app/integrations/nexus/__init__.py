"""
Clarity HMIS Integration Module

Provides integration with Clarity HMIS for automated vaccination verification calls.
"""

from backend.app.integrations.clarity.models import (
    ClarityAttribute,
    ClarityVaccineDose,
    ClaritySptDocument,
    ClarityEventInfo,
    ClarityVerification,
    ClarityPaginatedResponse,
    ClarityVerificationUpdate,
)
from backend.app.integrations.clarity.client import (
    ClarityClient,
    ClarityClientError,
    ClarityAuthenticationError,
    ClarityNotFoundError,
    ClarityForbiddenError,
    create_clarity_client,
)
from backend.app.integrations.clarity.sync_service import ClaritySyncService

__all__ = [
    # Models
    "ClarityAttribute",
    "ClarityVaccineDose",
    "ClaritySptDocument",
    "ClarityEventInfo",
    "ClarityVerification",
    "ClarityPaginatedResponse",
    "ClarityVerificationUpdate",
    # Client
    "ClarityClient",
    "ClarityClientError",
    "ClarityAuthenticationError",
    "ClarityNotFoundError",
    "ClarityForbiddenError",
    "create_clarity_client",
    # Sync Service
    "ClaritySyncService",
]
