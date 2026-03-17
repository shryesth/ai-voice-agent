"""
Nexus HMIS Integration Module

Provides integration with Nexus HMIS for automated vaccination verification calls.
"""

from backend.app.integrations.nexus.models import (
    NexusAttribute,
    NexusVaccineDose,
    NexusSptDocument,
    NexusEventInfo,
    NexusVerification,
    NexusPaginatedResponse,
    NexusVerificationUpdate,
)
from backend.app.integrations.nexus.client import (
    NexusClient,
    NexusClientError,
    NexusAuthenticationError,
    NexusNotFoundError,
    NexusForbiddenError,
    create_nexus_client,
)
from backend.app.integrations.nexus.sync_service import NexusSyncService

__all__ = [
    # Models
    "NexusAttribute",
    "NexusVaccineDose",
    "NexusSptDocument",
    "NexusEventInfo",
    "NexusVerification",
    "NexusPaginatedResponse",
    "NexusVerificationUpdate",
    # Client
    "NexusClient",
    "NexusClientError",
    "NexusAuthenticationError",
    "NexusNotFoundError",
    "NexusForbiddenError",
    "create_nexus_client",
    # Sync Service
    "NexusSyncService",
]
