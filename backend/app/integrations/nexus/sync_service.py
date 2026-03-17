"""
Nexus Sync Service

Handles bidirectional sync between Nexus API and managed queue system.
"""

import logging
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List

from backend.app.integrations.nexus.client import (
    NexusClient,
    NexusClientError,
    NexusForbiddenError,
    NexusNotFoundError,
    create_nexus_client,
)
from backend.app.integrations.nexus.models import NexusVerification
from backend.app.models.queue_models import (
    QueueConfig,
    CallEntry,
    CallEntryStatus,
    CallEntryStorage,
)

logger = logging.getLogger(__name__)


class NexusSyncService:
    """
    Service for syncing between Nexus API and managed queue.

    Responsibilities:
    1. Pull pending verifications from Nexus
    2. Create/update CallEntry records for each verification
    3. Push completed call results back to Nexus
    """

    def __init__(
        self,
        queue_repo,  # QueueRepository
        call_entry_repo,  # CallEntryRepository
    ):
        """
        Initialize sync service.

        Args:
            queue_repo: Repository for queue operations
            call_entry_repo: Repository for call entry operations
        """
        self.queue_repo = queue_repo
        self.call_entry_repo = call_entry_repo

    async def sync_queue_from_nexus(self, queue: QueueConfig) -> Dict[str, int]:
        """
        Fetch pending verifications from Nexus and create CallEntry records.

        Args:
            queue: Queue configuration with Nexus metadata

        Returns:
            Dict with sync statistics: created, updated, skipped, errors
        """
        metadata = queue.metadata
        stats = {"created": 0, "updated": 0, "skipped": 0, "errors": 0}

        if metadata.get("queue_type") != "nexus":
            logger.warning(f"Queue {queue.queue_id} is not a Nexus queue, skipping sync")
            return stats

        # Create client from queue metadata
        try:
            client = create_nexus_client(metadata)
        except ValueError as e:
            logger.error(f"Failed to create Nexus client for queue {queue.queue_id}: {e}")
            await self._update_sync_status(queue.queue_id, status="error", error=str(e))
            stats["errors"] += 1
            return stats

        try:
            async with client:
                # Fetch all pages of pending verifications
                verifications = await client.fetch_all_pending_verifications(
                    date_from=metadata.get("date_from"),
                    date_to=metadata.get("date_to"),
                )

                logger.info(
                    f"[Nexus:{queue.queue_id}] Fetched {len(verifications)} verifications"
                )

                # Process each verification
                for verification in verifications:
                    try:
                        result = await self._process_verification(queue, verification)
                        stats[result] += 1
                    except Exception as e:
                        logger.error(
                            f"Error processing verification {verification.id}: {e}"
                        )
                        stats["errors"] += 1

                # Update queue sync metadata
                await self._update_sync_status(
                    queue.queue_id,
                    status="success",
                    total_synced=len(verifications),
                )

                return stats

        except NexusClientError as e:
            logger.error(f"[Nexus:{queue.queue_id}] Sync failed: {e}")
            await self._update_sync_status(
                queue.queue_id, status="error", error=str(e)
            )
            raise

    async def _process_verification(
        self,
        queue: QueueConfig,
        verification: NexusVerification,
    ) -> str:
        """
        Process a single verification - create or update CallEntry.

        Returns: "created", "updated", or "skipped"
        """
        nexus_id = verification.id

        # Check if entry already exists for this verification
        existing = await self.call_entry_repo.find_by_external_id(
            queue_id=queue.queue_id,
            external_id_field="metadata.nexus_verification_id",
            external_id_value=nexus_id,
        )

        if existing:
            # Entry exists - check if needs update
            if existing.status in [
                CallEntryStatus.SUCCESS,
                CallEntryStatus.DEAD_LETTER,
            ]:
                # Already processed, skip
                return "skipped"

            # Could update if verification data changed, but for now skip
            return "skipped"

        # Skip if no phone numbers
        if not verification.contact_phones:
            logger.warning(
                f"Verification {nexus_id} has no phone numbers, skipping"
            )
            return "skipped"

        # Skip if verification cannot be changed
        if not verification.can_be_changed:
            logger.info(
                f"Verification {nexus_id} cannot be changed, skipping"
            )
            return "skipped"

        # Create new CallEntry
        phone_number = verification.primary_phone
        if not phone_number:
            return "skipped"

        # Get language from queue metadata
        language = queue.metadata.get("default_language", "en")

        # Build call_data for vaccination call
        call_data = {
            "patientName": verification.contact_name,
            "guardianName": verification.contact_name,  # May be same person
            "phoneNumber": phone_number,
            "dispensaryName": verification.event_info.event_facility,
            "visitDate": self._format_date_for_voice(
                verification.event_info.event_date
            ),
            "vaccineName": verification.vaccine_names_str,
            "language": language,
        }

        # Build metadata
        entry_metadata = {
            "source": "nexus",
            "nexus_verification_id": nexus_id,
            "nexus_environment": queue.metadata.get("nexus_environment"),
            "nexus_event_type": verification.event_info.event_type,
            "nexus_event_facility": verification.event_info.event_facility,
            "nexus_event_date": verification.event_info.event_date,
            "nexus_vaccine_doses": verification.vaccine_names,
            "contact_name": verification.contact_name,
            "contact_gender": verification.contact_gender,
            "contact_phones": verification.contact_phones,
            "sync_status": "pending",
            "synced_from_nexus_at": datetime.utcnow().isoformat(),
        }

        # Create entry
        entry = CallEntry(
            entry_id=f"nexus_{uuid.uuid4().hex[:12]}",
            queue_id=queue.queue_id,
            phone_number=phone_number,
            call_type="vaccination",
            call_data=call_data,
            metadata=entry_metadata,
            status=CallEntryStatus.PENDING,
            storage=CallEntryStorage(),
        )

        success = await self.call_entry_repo.create_entry(entry)
        if success:
            await self.call_entry_repo.add_state_history(
                entry_id=entry.entry_id,
                from_state=None,
                to_state=CallEntryStatus.PENDING,
                reason=f"Synced from Nexus verification {nexus_id}",
            )
            logger.info(
                f"Created CallEntry {entry.entry_id} for Nexus verification {nexus_id}"
            )
            return "created"

        logger.error(f"Failed to create CallEntry for verification {nexus_id}")
        return "errors"

    async def sync_result_to_nexus(self, entry: CallEntry) -> bool:
        """
        Push call result back to Nexus API.

        Called after a call completes (success or final failure).

        Args:
            entry: Completed CallEntry

        Returns:
            True if sync succeeded
        """
        metadata = entry.metadata

        # Only sync Nexus-sourced entries
        if metadata.get("source") != "nexus":
            return True

        nexus_id = metadata.get("nexus_verification_id")
        if not nexus_id:
            logger.warning(f"Entry {entry.entry_id} has no nexus_verification_id")
            return False

        # Get queue for Nexus credentials
        queue = await self.queue_repo.get_queue(entry.queue_id)
        if not queue:
            logger.error(f"Queue {entry.queue_id} not found")
            return False

        try:
            client = create_nexus_client(queue.metadata)
        except ValueError as e:
            logger.error(f"Failed to create Nexus client: {e}")
            return False

        try:
            async with client:
                # Determine status to send to Nexus
                if entry.status == CallEntryStatus.SUCCESS:
                    nexus_status = 1  # Verified
                    is_confirmed = True
                else:
                    nexus_status = 2  # Failed
                    is_confirmed = False

                # Get recording URL if available
                recording_url = None
                if entry.storage and entry.storage.recording_url:
                    recording_url = entry.storage.recording_url

                # Update Nexus
                success = await client.update_verification(
                    verification_id=nexus_id,
                    status=nexus_status,
                    recording_url=recording_url,
                    is_visit_confirmed=is_confirmed,
                )

                # Update entry metadata with sync status
                sync_status = "synced_success" if success else "synced_failed"
                await self.call_entry_repo.update_entry(
                    entry.entry_id,
                    {
                        "metadata.sync_status": sync_status,
                        "metadata.last_sync_attempt": datetime.utcnow().isoformat(),
                        "metadata.synced_to_nexus_at": datetime.utcnow().isoformat()
                        if success
                        else None,
                    },
                )

                return success

        except NexusForbiddenError as e:
            logger.warning(
                f"Cannot update Nexus verification {nexus_id}: {e}"
            )
            await self._mark_sync_failed(entry.entry_id, str(e))
            return False

        except NexusNotFoundError as e:
            logger.warning(
                f"Nexus verification {nexus_id} not found: {e}"
            )
            await self._mark_sync_failed(entry.entry_id, str(e))
            return False

        except NexusClientError as e:
            logger.error(
                f"Failed to sync result to Nexus for entry {entry.entry_id}: {e}"
            )
            await self._mark_sync_failed(entry.entry_id, str(e))
            raise

    async def _mark_sync_failed(self, entry_id: str, error: str) -> None:
        """Mark entry sync as failed."""
        await self.call_entry_repo.update_entry(
            entry_id,
            {
                "metadata.sync_status": "synced_failed",
                "metadata.last_sync_attempt": datetime.utcnow().isoformat(),
                "metadata.sync_error": error,
            },
        )

    async def _update_sync_status(
        self,
        queue_id: str,
        status: str,
        total_synced: int = 0,
        error: Optional[str] = None,
    ) -> None:
        """Update queue metadata with sync status."""
        updates: Dict[str, Any] = {
            "metadata.last_sync_at": datetime.utcnow().isoformat(),
            "metadata.last_sync_status": status,
        }

        if error:
            updates["metadata.last_sync_error"] = error
        else:
            updates["metadata.last_sync_error"] = None

        if total_synced:
            # Note: Ideally use $inc for atomic increment
            updates["metadata.total_synced_items"] = total_synced

        await self.queue_repo.update_queue(queue_id, updates)

    def _format_date_for_voice(self, date_str: str) -> str:
        """
        Format date for voice (human-readable).

        The AI speaks dates aloud, so we need natural language format.
        """
        if not date_str:
            return "your recent visit"

        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            # Format as "January 15th, 2025"
            day = dt.day
            suffix = (
                "th"
                if 11 <= day <= 13
                else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
            )
            return dt.strftime(f"%B {day}{suffix}, %Y")
        except ValueError:
            return date_str
