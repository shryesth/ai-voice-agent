"""
Nexus HMIS API Client

Async HTTP client for interacting with Nexus HMIS verification API.
Supports multiple environments with per-queue credentials.
"""

import logging
from datetime import date
from typing import Optional, Dict, Any

import httpx

from backend.app.integrations.nexus.models import (
    NexusVerification,
    NexusEventInfo,
    NexusPaginatedResponse,
    NexusVerificationUpdate,
)

logger = logging.getLogger(__name__)


class NexusClientError(Exception):
    """Base exception for Nexus client errors."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class NexusAuthenticationError(NexusClientError):
    """Raised when authentication fails (401/403)."""

    pass


class NexusNotFoundError(NexusClientError):
    """Raised when resource is not found (404)."""

    pass


class NexusForbiddenError(NexusClientError):
    """Raised when action is forbidden (e.g., canBeChanged=false)."""

    pass


class NexusClient:
    """
    Async client for Nexus HMIS API.

    Each queue can have its own Nexus configuration, so this client
    is instantiated with queue-specific credentials.

    Usage:
        client = NexusClient(
            api_url="https://nexus.hnd.acme.org/api/v1",
            api_key="bearer-token",
            environment="honduras"
        )

        async with client:
            verifications = await client.fetch_pending_verifications()
            await client.update_verification(123, status=1, is_visit_confirmed=True)
    """

    def __init__(
        self,
        api_url: str,
        api_key: str,
        environment: str,
        timeout: float = 30.0,
    ):
        """
        Initialize Nexus client with queue-specific credentials.

        Args:
            api_url: Base URL for Nexus API (e.g., https://nexus.hnd.acme.org/api/v1)
            api_key: API key or Bearer token
            environment: Environment name for logging (staging, haiti, honduras)
            timeout: Request timeout in seconds
        """
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.environment = environment
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "NexusClient":
        """Async context manager entry."""
        await self._ensure_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()

    async def _ensure_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    def _log_prefix(self) -> str:
        """Get log prefix with environment."""
        return f"[Nexus:{self.environment}]"

    async def fetch_pending_verifications(
        self,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        page: int = 1,
        page_size: int = 100,
    ) -> NexusPaginatedResponse:
        """
        Fetch pending verifications from Nexus API.

        Args:
            date_from: Start date filter (YYYY-MM-DD)
            date_to: End date filter (YYYY-MM-DD), defaults to today
            page: Page number (1-indexed)
            page_size: Number of items per page (max 100)

        Returns:
            Paginated response with verification items

        Raises:
            NexusAuthenticationError: If authentication fails
            NexusClientError: For other API errors
        """
        client = await self._ensure_client()

        # Default date_to to today if not specified
        if date_to is None:
            date_to = date.today().isoformat()

        params: Dict[str, Any] = {
            "page": page,
            "pageSize": min(page_size, 100),  # API limit
        }
        if date_from:
            params["date_from"] = date_from
        if date_to:
            params["date_to"] = date_to

        url = f"{self.api_url}/hmis/client-visits/verification"

        logger.info(f"{self._log_prefix()} Fetching verifications: page={page}, params={params}")

        try:
            response = await client.get(url, params=params)

            if response.status_code == 401:
                raise NexusAuthenticationError(
                    "Authentication failed. Check API key.",
                    status_code=401,
                )
            if response.status_code == 403:
                raise NexusAuthenticationError(
                    "Access forbidden. Check API permissions.",
                    status_code=403,
                )

            response.raise_for_status()
            data = response.json()

            # Parse response
            items = []
            for item in data.get("items", []):
                try:
                    verification = self._parse_verification(item)
                    items.append(verification)
                except Exception as e:
                    logger.warning(
                        f"{self._log_prefix()} Failed to parse verification {item.get('id')}: {e}"
                    )
                    continue

            result = NexusPaginatedResponse(
                items=items,
                total=data.get("total", len(items)),
                page=data.get("page", page),
                page_size=data.get("page_size", page_size),
                pages=data.get("pages", 1),
                has_next=data.get("has_next", False),
                has_previous=data.get("has_previous", False),
            )

            logger.info(
                f"{self._log_prefix()} Fetched {len(items)} verifications "
                f"(page {result.page}/{result.pages}, total={result.total})"
            )

            return result

        except httpx.TimeoutException:
            logger.error(f"{self._log_prefix()} Request timeout after {self.timeout}s")
            raise NexusClientError(f"Request timeout after {self.timeout}s")
        except httpx.HTTPStatusError as e:
            logger.error(
                f"{self._log_prefix()} HTTP error: {e.response.status_code} - {e.response.text}"
            )
            raise NexusClientError(
                f"HTTP error: {e.response.status_code}",
                status_code=e.response.status_code,
            )

    def _parse_verification(self, item: Dict[str, Any]) -> NexusVerification:
        """Parse a verification item from API response."""
        event_info_data = item.get("eventInfo", {})

        event_info = NexusEventInfo(
            eventDate=event_info_data.get("eventDate", ""),
            eventFacility=event_info_data.get("eventFacility", ""),
            eventType=event_info_data.get("eventType", ""),
            attributes=event_info_data.get("attributes", []),
            vaccineDoses=event_info_data.get("vaccineDoses", []),
            sptDocumentIds=event_info_data.get("sptDocumentIds", []),
        )

        return NexusVerification(
            id=item["id"],
            status=item.get("status", 999),
            canBeChanged=item.get("canBeChanged", True),
            contactClientSptId=item.get("contactClientSptId"),
            contactName=item.get("contactName", ""),
            contactGender=item.get("contactGender"),
            contactPhones=item.get("contactPhones", []),
            contactPhoneOwnerName=item.get("contactPhoneOwnerName"),
            eventInfo=event_info,
            recordingUrl=item.get("recordingUrl"),
            isVisitConfirmed=item.get("isVisitConfirmed"),
        )

    async def fetch_all_pending_verifications(
        self,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        page_size: int = 100,
    ) -> list[NexusVerification]:
        """
        Fetch all pending verifications, handling pagination automatically.

        Args:
            date_from: Start date filter (YYYY-MM-DD)
            date_to: End date filter (YYYY-MM-DD), defaults to today
            page_size: Number of items per page

        Returns:
            List of all verification items across all pages
        """
        all_items: list[NexusVerification] = []
        page = 1

        while True:
            response = await self.fetch_pending_verifications(
                date_from=date_from,
                date_to=date_to,
                page=page,
                page_size=page_size,
            )

            all_items.extend(response.items)

            if not response.has_next:
                break

            page += 1

            # Safety limit to prevent infinite loops
            if page > 100:
                logger.warning(f"{self._log_prefix()} Reached page limit (100), stopping pagination")
                break

        logger.info(f"{self._log_prefix()} Fetched {len(all_items)} total verifications")
        return all_items

    async def update_verification(
        self,
        verification_id: int,
        status: int,
        recording_url: Optional[str] = None,
        is_visit_confirmed: Optional[bool] = None,
    ) -> bool:
        """
        Update verification result in Nexus.

        Args:
            verification_id: Nexus verification ID
            status: New status code (1=verified, 2=failed)
            recording_url: URL to call recording (presigned URL)
            is_visit_confirmed: Whether visit was confirmed

        Returns:
            True if update succeeded

        Raises:
            NexusNotFoundError: If verification not found
            NexusForbiddenError: If verification cannot be changed
            NexusClientError: For other API errors
        """
        client = await self._ensure_client()

        url = f"{self.api_url}/hmis/client-visits/verification/{verification_id}"

        # Build request body using alias names
        update = NexusVerificationUpdate(
            status=status,
            recording_url=recording_url,
            is_visit_confirmed=is_visit_confirmed,
        )
        body = update.model_dump(by_alias=True, exclude_none=True)

        logger.info(f"{self._log_prefix()} Updating verification {verification_id}: {body}")

        try:
            response = await client.put(url, json=body)

            if response.status_code == 401:
                raise NexusAuthenticationError(
                    "Authentication failed. Check API key.",
                    status_code=401,
                )
            if response.status_code == 403:
                raise NexusForbiddenError(
                    f"Cannot update verification {verification_id}. It may be locked.",
                    status_code=403,
                )
            if response.status_code == 404:
                raise NexusNotFoundError(
                    f"Verification {verification_id} not found.",
                    status_code=404,
                )

            response.raise_for_status()

            logger.info(f"{self._log_prefix()} Successfully updated verification {verification_id}")
            return True

        except httpx.TimeoutException:
            logger.error(f"{self._log_prefix()} Request timeout updating verification {verification_id}")
            raise NexusClientError(f"Request timeout updating verification {verification_id}")
        except httpx.HTTPStatusError as e:
            logger.error(
                f"{self._log_prefix()} Failed to update verification {verification_id}: "
                f"{e.response.status_code} - {e.response.text}"
            )
            raise NexusClientError(
                f"Failed to update verification: {e.response.status_code}",
                status_code=e.response.status_code,
            )


def create_nexus_client(metadata: Dict[str, Any]) -> NexusClient:
    """
    Create a NexusClient from queue metadata.

    Args:
        metadata: Queue metadata dict containing nexus_api_url, nexus_api_key, etc.

    Returns:
        Configured NexusClient

    Raises:
        ValueError: If required metadata fields are missing
    """
    required_fields = ["nexus_api_url", "nexus_api_key"]
    for field in required_fields:
        if not metadata.get(field):
            raise ValueError(f"Missing required metadata field: {field}")

    return NexusClient(
        api_url=metadata["nexus_api_url"],
        api_key=metadata["nexus_api_key"],
        environment=metadata.get("nexus_environment", "unknown"),
    )
