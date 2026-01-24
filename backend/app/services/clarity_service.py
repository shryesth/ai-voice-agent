"""
Clarity Service for bidirectional sync with Clarity API.

This service handles:
- Pull: Fetching verification subjects from Clarity to create Recipients
- Push: Updating verification status after calls complete
"""

import httpx
import logging
from asyncio import Semaphore
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from backend.app.models.enums import (
    EventCategory,
    ContactType,
    ExternalSource,
    RecipientStatus,
    SyncStatus,
)
from backend.app.models.geography import Geography, ClarityConfig
from backend.app.models.call_queue import CallQueue
from backend.app.models.recipient import (
    Recipient,
    ClarityEventInfo,
    determine_contact_type,
)
from backend.app.domains.supervisor.event_type_config import (
    get_event_type_config,
    is_callable_event,
)

logger = logging.getLogger(__name__)


class ClarityService:
    """
    Service for integrating with Clarity API.

    Supports bidirectional sync:
    - Pull: GET /api/v1/hmis/client-visits/verification?status=IN_PROGRESS
    - Push: PUT /api/v1/hmis/client-visits/verification/{id}
    """

    # Clarity verification status codes
    CLARITY_STATUS_IN_PROGRESS = 1
    CLARITY_STATUS_VALID = 2
    CLARITY_STATUS_NOT_VALID = 3
    CLARITY_STATUS_NOT_REACHABLE = 4

    def __init__(self, clarity_config: ClarityConfig):
        """
        Initialize the Clarity service.

        Args:
            clarity_config: Clarity API configuration from Geography
        """
        self.config = clarity_config
        self.base_url = clarity_config.api_url.rstrip("/")
        self.api_key = clarity_config.api_key
        self.timeout = httpx.Timeout(30.0, connect=10.0)
        self._client: Optional[httpx.AsyncClient] = None
        self._semaphore = Semaphore(10)  # Max 10 concurrent requests to Clarity API

    @property
    def headers(self) -> Dict[str, str]:
        """Get headers for API requests."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.api_key:
            # Use X-API-Key header (as expected by Clarity mock server)
            headers["X-API-Key"] = self.api_key
        return headers

    async def _get_client(self) -> httpx.AsyncClient:
        """
        Get or create the HTTP client for connection pooling.

        Reuses an existing client if available, creates new one if closed.

        Returns:
            Reusable AsyncClient instance
        """
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def close(self):
        """Close the HTTP client and release resources."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def pull_verification_subjects(
        self,
        queue: CallQueue,
        max_count: int = 100,
        event_type_filter: List[str] = None,
    ) -> List[Recipient]:
        """
        Pull verification subjects from Clarity and create Recipients.

        Args:
            queue: CallQueue to add recipients to
            max_count: Maximum number of subjects to pull
            event_type_filter: Optional list of event types to filter

        Returns:
            List of created Recipient documents
        """
        if not self.config.enabled:
            logger.warning("Clarity sync is not enabled")
            return []

        # Get subjects with IN_PROGRESS status
        url = f"{self.base_url}/api/v1/hmis/client-visits/verification"
        params = {
            "page": 1,
            "pageSize": max_count,
        }

        try:
            async with self._semaphore:
                client = await self._get_client()
                response = await client.get(url, headers=self.headers, params=params)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as e:
            logger.error(f"Failed to fetch verification subjects: {e}")
            raise ClarityAPIError(f"Failed to fetch from Clarity: {e}")

        # Process subjects and create recipients
        # Mock server returns: {"items": [...], "page": 1, "pageSize": 50, "total": 5, "pages": 1}
        subjects = data.get("items", []) if isinstance(data, dict) else data
        recipients = []

        for subject in subjects:
            try:
                recipient = await self._create_recipient_from_subject(
                    queue=queue,
                    subject=subject,
                    event_type_filter=event_type_filter,
                )
                if recipient:
                    recipients.append(recipient)
            except Exception as e:
                logger.error(f"Failed to create recipient from subject: {e}")
                continue

        logger.info(f"Pulled {len(recipients)} recipients from Clarity for queue {queue.id}")
        return recipients

    async def _create_recipient_from_subject(
        self,
        queue: CallQueue,
        subject: Dict[str, Any],
        event_type_filter: List[str] = None,
    ) -> Optional[Recipient]:
        """
        Create a Recipient from a Clarity verification subject.

        Args:
            queue: CallQueue to add recipient to
            subject: Raw subject data from Clarity API
            event_type_filter: Optional event type filter

        Returns:
            Created Recipient or None if skipped
        """
        # Extract basic info
        verification_id = subject.get("id") or subject.get("verification_id")
        if not verification_id:
            logger.warning("Subject missing verification_id, skipping")
            return None

        # Extract event info (handle camelCase and nested eventInfo)
        event_info_obj = subject.get("eventInfo", subject.get("event_info", {}))
        event_type = (
            subject.get("event_type")
            or subject.get("eventType")
            or subject.get("service_type")
            or event_info_obj.get("eventType")
            or event_info_obj.get("event_type")
            or ""
        )

        # Check if this event type should trigger calls
        if not is_callable_event(event_type):
            logger.debug(f"Skipping non-callable event type: {event_type}")
            return None

        # Apply event type filter
        if event_type_filter and event_type not in event_type_filter:
            logger.debug(f"Skipping filtered event type: {event_type}")
            return None

        # Get event type configuration (check eventInfo structure)
        vaccines = (
            subject.get("vaccines")
            or event_info_obj.get("vaccineDoses")
            or event_info_obj.get("vaccines")
            or []
        )
        attributes_list = (
            subject.get("attributes")
            or event_info_obj.get("attributes")
            or []
        )
        # Convert attributes list to dict if needed
        if isinstance(attributes_list, list):
            attributes = {attr.get("name", ""): attr.get("value", "") for attr in attributes_list}
        else:
            attributes = attributes_list or {}
        event_config = get_event_type_config(event_type, vaccines, attributes)

        # Extract contact information
        phone = self._extract_phone(subject)
        if not phone:
            logger.warning(f"Subject {verification_id} missing phone number, skipping")
            return None

        # Determine contact type (handle camelCase)
        patient_name = (
            subject.get("patient_name")
            or subject.get("patientName")
            or subject.get("name")
            or ""
        )
        contact_name = (
            subject.get("contact_name")
            or subject.get("contactName")
            or subject.get("phone_owner_name")
            or subject.get("contactPhoneOwnerName")
            or patient_name
        )
        patient_age = (
            subject.get("patient_age")
            or subject.get("patientAge")
            or subject.get("age")
        )
        phone_owner_name = (
            subject.get("phone_owner_name")
            or subject.get("contactPhoneOwnerName")
        )

        contact_type = determine_contact_type(
            patient_age=patient_age,
            contact_name=contact_name,
            patient_name=patient_name,
            phone_owner_name=phone_owner_name,
        )

        # Extract facility info (check eventInfo and camelCase)
        facility_name = (
            subject.get("facility_name")
            or subject.get("facilityName")
            or subject.get("dispensary_name")
            or event_info_obj.get("eventFacility")
            or event_info_obj.get("facility_name")
            or ""
        )
        facility_id = (
            subject.get("facility_id")
            or subject.get("facilityId")
            or subject.get("dispensary_id")
        )

        # Parse event date (check eventInfo and camelCase)
        event_date = None
        date_str = (
            subject.get("event_date")
            or subject.get("eventDate")
            or subject.get("visit_date")
            or event_info_obj.get("eventDate")
        )
        if date_str:
            try:
                event_date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass

        # Create ClarityEventInfo
        event_info = ClarityEventInfo(
            clarity_verification_id=str(verification_id),
            event_type=event_type,
            event_category=event_config.event_category,
            confirmation_message_key=event_config.confirmation_message_key,
            event_date=event_date,
            facility_name=facility_name,
            facility_id=facility_id,
            attributes=attributes,
            vaccines=vaccines,
            requires_side_effects=event_config.requires_side_effects,
            requires_satisfaction=event_config.requires_satisfaction,
        )

        # Determine language
        language = subject.get("language", subject.get("preferred_language", queue.default_language))

        # Check if recipient already exists (for upsert logic)
        existing = await Recipient.find_one(
            Recipient.external_id == str(verification_id),
            Recipient.external_source == ExternalSource.CLARITY,
        )

        if existing:
            # Update existing recipient with latest data from Clarity
            # Only update if status is still PENDING or NOT_REACHABLE (not yet processed)
            if existing.status in [RecipientStatus.PENDING, RecipientStatus.NOT_REACHABLE, RecipientStatus.FAILED]:
                existing.queue_id = queue.id
                existing.contact_phone = phone
                existing.contact_name = contact_name
                existing.contact_type = contact_type
                existing.language = language
                existing.patient_name = patient_name if patient_name != contact_name else None
                existing.patient_relation = subject.get("relation", subject.get("relationship"))
                existing.patient_age = patient_age
                existing.event_info = event_info
                existing.priority = subject.get("priority", 0)
                existing.updated_at = datetime.utcnow()

                # Reset status to PENDING if it was FAILED or NOT_REACHABLE (allow retry)
                if existing.status in [RecipientStatus.FAILED, RecipientStatus.NOT_REACHABLE]:
                    existing.status = RecipientStatus.PENDING
                    existing.retry_count = 0
                    existing.last_failure_reason = None

                await existing.save()
                logger.info(f"Updated existing recipient for verification {verification_id}")
                return existing
            else:
                # Recipient already processed (COMPLETED, CALLING, etc.), skip
                logger.debug(f"Recipient already exists and processed for verification {verification_id}, status={existing.status}")
                return None

        # Create new recipient (just use queue.id for the Link field)
        recipient = Recipient(
            queue_id=queue.id,  # Link field accepts document ID
            external_source=ExternalSource.CLARITY,
            external_id=str(verification_id),
            contact_phone=phone,
            contact_name=contact_name,
            contact_type=contact_type,
            language=language,
            patient_name=patient_name if patient_name != contact_name else None,
            patient_relation=subject.get("relation", subject.get("relationship")),
            patient_age=patient_age,
            event_info=event_info,
            status=RecipientStatus.PENDING,
            priority=subject.get("priority", 0),
            sync_status=SyncStatus.PENDING,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        await recipient.insert()
        logger.info(f"Created new recipient for verification {verification_id}")
        return recipient

    def _extract_phone(self, subject: Dict[str, Any]) -> Optional[str]:
        """
        Extract and normalize phone number from subject.

        Normalizes to E.164 format using the geography's default country code.
        """
        # Try various phone fields (support both snake_case and camelCase)
        phone = (
            subject.get("contact_phone")
            or subject.get("contactPhone")  # Mock server uses camelCase
            or subject.get("phone")
            or subject.get("phone_number")
            or subject.get("mobile")
        )

        if not phone:
            return None

        # Normalize to E.164 format
        phone = str(phone).strip()
        if not phone.startswith("+"):
            # Use configured country code if not specified
            country_code = self.config.default_country_code
            if phone.startswith(country_code):
                phone = f"+{phone}"
            else:
                phone = f"+{country_code}{phone}"

        return phone

    async def push_verification_result(
        self,
        recipient: Recipient,
        recording_url: Optional[str] = None,
    ) -> bool:
        """
        Push verification result to Clarity.

        Args:
            recipient: Recipient with completed call
            recording_url: Optional presigned URL for recording

        Returns:
            True if push was successful
        """
        if not self.config.enabled:
            logger.warning("Clarity sync is not enabled")
            return False

        if not recipient.external_id or recipient.external_source != ExternalSource.CLARITY:
            logger.warning(f"Recipient {recipient.id} is not from Clarity, skipping push")
            return False

        # Map recipient status to Clarity status
        clarity_status = self._map_status_to_clarity(recipient.status)

        # Build payload
        payload = {
            "status": clarity_status,
            "is_visit_confirmed": recipient.conversation_result.is_visit_confirmed,
            "is_service_confirmed": recipient.conversation_result.is_service_confirmed,
            "satisfaction_rating": recipient.conversation_result.satisfaction_rating,
            "side_effects_reported": recipient.conversation_result.side_effects_reported,
            "has_side_effects": recipient.conversation_result.has_side_effects,
            "specific_concerns": recipient.conversation_result.specific_concerns,
            "urgency_flagged": recipient.urgency_flagged,
            "human_callback_requested": recipient.human_callback_requested,
            "call_attempts": len(recipient.call_attempts),
            "completed_at": recipient.completed_at.isoformat() if recipient.completed_at else None,
        }

        # Add recording URL if configured
        if self.config.include_recording_url and recording_url:
            payload["recording_url"] = recording_url

        # Make API call
        url = f"{self.base_url}/api/v1/hmis/client-visits/verification/{recipient.external_id}"

        # Log the complete payload being sent to Clarity
        logger.info(
            f"Pushing verification result to Clarity - "
            f"Recipient ID: {recipient.id}, "
            f"External ID: {recipient.external_id}, "
            f"URL: {url}"
        )
        logger.info(f"Clarity Push Payload: {payload}")

        try:
            async with self._semaphore:
                client = await self._get_client()
                response = await client.put(url, headers=self.headers, json=payload)
                response.raise_for_status()

            # Log successful response
            logger.info(
                f"Successfully pushed result to Clarity - "
                f"Recipient: {recipient.id}, "
                f"HTTP Status: {response.status_code}, "
                f"Response: {response.text[:200]}"  # Limit response to 200 chars
            )

            # Update sync status
            recipient.sync_status = SyncStatus.SYNCED
            recipient.last_synced_at = datetime.now(timezone.utc)
            recipient.sync_error = None
            recipient.updated_at = datetime.now(timezone.utc)
            await recipient.save()

            logger.info(f"Pushed result for recipient {recipient.id} to Clarity")
            return True

        except httpx.HTTPError as e:
            # Log detailed error information
            error_details = f"HTTP {e.response.status_code}: {e.response.text}" if hasattr(e, 'response') else str(e)
            logger.error(
                f"Failed to push result to Clarity - "
                f"Recipient: {recipient.id}, "
                f"Error: {error_details}, "
                f"Payload: {payload}"
            )
            recipient.sync_status = SyncStatus.FAILED
            recipient.sync_error = str(e)
            recipient.updated_at = datetime.now(timezone.utc)
            await recipient.save()
            return False

    def _map_status_to_clarity(self, status: RecipientStatus) -> int:
        """Map RecipientStatus to Clarity verification status."""
        mapping = {
            RecipientStatus.COMPLETED: self.CLARITY_STATUS_VALID,
            RecipientStatus.FAILED: self.CLARITY_STATUS_NOT_VALID,
            RecipientStatus.NOT_REACHABLE: self.CLARITY_STATUS_NOT_REACHABLE,
            RecipientStatus.DLQ: self.CLARITY_STATUS_NOT_REACHABLE,
            RecipientStatus.SKIPPED: self.CLARITY_STATUS_NOT_VALID,
        }
        return mapping.get(status, self.CLARITY_STATUS_NOT_REACHABLE)

    async def test_connection(self) -> bool:
        """Test connection to Clarity API."""
        if not self.config.enabled:
            return False

        url = f"{self.base_url}/health"
        try:
            async with self._semaphore:
                client = await self._get_client()
                response = await client.get(url, headers=self.headers)
                return response.status_code < 500
        except httpx.HTTPError:
            return False


class ClarityAPIError(Exception):
    """Exception raised for Clarity API errors."""
    pass


# Factory function to get ClarityService from Geography
async def get_clarity_service(geography_id: str) -> Optional[ClarityService]:
    """
    Get a ClarityService for a geography.

    Args:
        geography_id: Geography document ID

    Returns:
        ClarityService if Clarity is configured, None otherwise

    Note:
        The returned service maintains a reusable HTTP client for connection pooling.
        Callers should call await service.close() to clean up resources when done,
        or rely on async context manager usage for automatic cleanup.
    """
    from bson import ObjectId

    geography = await Geography.get(ObjectId(geography_id))
    if not geography:
        return None

    if not geography.clarity_config.enabled:
        return None

    return ClarityService(geography.clarity_config)
