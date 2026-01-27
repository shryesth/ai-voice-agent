"""
Celery task for downloading Twilio recordings and uploading to MinIO.

This module provides robust recording storage with:
- Twilio recording download with authentication
- Audio validation before upload
- S3/MinIO upload with exponential backoff retry
- Redis fallback storage for failures
- Dead-letter queue for persistent failures
- Automatic cleanup of Twilio recordings after successful upload
- Recipient recording_url update after successful upload
"""
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx
from bson import ObjectId
from twilio.rest import Client

from backend.app.celery_app import celery_app, get_worker_event_loop
from backend.app.core.config import settings
from backend.app.models.call_record import CallRecord
from backend.app.models.recipient import Recipient
from backend.app.services.recording_service import RecordingService

logger = logging.getLogger(__name__)


# Twilio download retry settings
TWILIO_DOWNLOAD_MAX_RETRIES = 3
TWILIO_DOWNLOAD_RETRY_DELAY = 30  # seconds
TWILIO_DOWNLOAD_TIMEOUT = 60  # seconds


@celery_app.task(
    name="download_twilio_recording",
    bind=True,
    max_retries=TWILIO_DOWNLOAD_MAX_RETRIES,
    default_retry_delay=TWILIO_DOWNLOAD_RETRY_DELAY,
    time_limit=settings.recording_task_timeout,
    soft_time_limit=settings.recording_task_timeout - 30,
)
def download_twilio_recording(
    self,
    call_sid: str,
    recording_sid: str,
    recording_url: str,
    recording_duration: int,
):
    """
    Download recording from Twilio and upload to MinIO with full safety mechanisms.

    Flow:
    1. Fetch recording metadata from Twilio API
    2. Download MP3 audio with authentication
    3. Upload to S3/MinIO via RecordingService (handles validation, retry, fallback)
    4. Delete recording from Twilio on success

    On failure:
    - Twilio download failure: Retry up to 3 times with 30s delay
    - S3 upload failure: RecordingService handles retry, fallback, and DLQ

    Args:
        call_sid: Twilio call SID
        recording_sid: Twilio recording SID
        recording_url: Twilio recording URL (JSON endpoint)
        recording_duration: Recording duration in seconds
    """
    logger.info(f"Starting recording download for call: {call_sid}, recording: {recording_sid}")

    try:
        # Initialize Twilio client
        twilio_client = Client(settings.twilio_account_sid, settings.twilio_auth_token)

        # Fetch recording metadata from Twilio
        try:
            recording = twilio_client.recordings(recording_sid).fetch()
        except Exception as twilio_error:
            logger.error(f"Failed to fetch Twilio recording metadata: {twilio_error}")
            raise self.retry(exc=twilio_error)

        # Construct audio download URL (convert .json to .mp3)
        audio_url = f"https://api.twilio.com{recording.uri.replace('.json', '.mp3')}"
        logger.info(f"Downloading recording from: {audio_url}")

        # Get worker event loop for async operations
        loop = get_worker_event_loop()

        # Download audio from Twilio with authentication
        audio_data = loop.run_until_complete(_download_audio_with_retry(
            audio_url=audio_url,
            max_retries=2,  # Retry within this task execution
        ))

        if not audio_data:
            logger.error(f"Failed to download recording for call: {call_sid}")
            raise Exception("Failed to download audio from Twilio")

        logger.info(f"Downloaded recording: {len(audio_data)} bytes")

        # Process recording upload in async context
        # RecordingService handles:
        # - Audio validation
        # - S3 upload with exponential backoff
        # - Redis fallback on failure
        # - DLQ entry on exhausted retries
        success = loop.run_until_complete(_process_recording_upload(
            call_sid=call_sid,
            recording_sid=recording_sid,
            recording_url=recording_url,
            recording_duration=recording_duration,
            audio_data=audio_data,
        ))

        if not success:
            # RecordingService already handled fallback and DLQ
            # Log but don't retry at Celery level - data is safe in Redis
            logger.warning(
                f"Recording upload to S3 failed for call {call_sid}, "
                "but data is stored in Redis fallback. Check DLQ for recovery."
            )
            # Return success=True because data is preserved
            return {
                "status": "fallback",
                "call_sid": call_sid,
                "recording_sid": recording_sid,
                "message": "Recording stored in Redis fallback for later retry"
            }

        logger.info(f"Uploaded recording to MinIO for call: {call_sid}")

        # Delete recording from Twilio to save costs (only on successful S3 upload)
        try:
            twilio_client.recordings(recording_sid).delete()
            logger.info(f"Deleted recording from Twilio: {recording_sid}")
        except Exception as delete_error:
            # Log but don't fail the task - recording is already in S3
            logger.warning(f"Failed to delete Twilio recording (non-fatal): {delete_error}")

        logger.info(f"Recording processing complete for call: {call_sid}")

        return {
            "status": "success",
            "call_sid": call_sid,
            "recording_sid": recording_sid,
            "size_bytes": len(audio_data),
        }

    except Exception as e:
        logger.error(f"Error processing recording: {e}", exc_info=True)

        # Check if we should retry at Celery level
        # Only retry for Twilio download failures, not S3 failures
        # (S3 failures are handled by RecordingService with its own retry/fallback)
        if "Twilio" in str(e) or "download" in str(e).lower():
            raise self.retry(exc=e)

        # For other errors, log and return failure
        return {
            "status": "error",
            "call_sid": call_sid,
            "recording_sid": recording_sid,
            "error": str(e),
        }


@celery_app.task(
    name="retry_recording_from_fallback",
    bind=True,
    max_retries=1,
    time_limit=settings.recording_task_timeout,
)
def retry_recording_from_fallback(self, call_id: str):
    """
    Retry uploading a recording from Redis fallback storage.

    Called manually or by a scheduled task to retry failed uploads
    stored in Redis.

    Args:
        call_id: CallRecord ID to retry
    """
    logger.info(f"Retrying recording upload from fallback for call: {call_id}")

    try:
        loop = get_worker_event_loop()
        recording_service = RecordingService()

        success = loop.run_until_complete(recording_service.retry_from_fallback(call_id))

        if success:
            logger.info(f"Successfully retried recording upload for call: {call_id}")
            return {
                "status": "success",
                "call_id": call_id,
            }
        else:
            logger.warning(f"Failed to retry recording upload for call: {call_id}")
            return {
                "status": "failed",
                "call_id": call_id,
            }

    except Exception as e:
        logger.error(f"Error retrying recording from fallback: {e}", exc_info=True)
        return {
            "status": "error",
            "call_id": call_id,
            "error": str(e),
        }


async def _download_audio_with_retry(
    audio_url: str,
    max_retries: int = 2,
) -> Optional[bytes]:
    """
    Download audio from Twilio with retry logic.

    Args:
        audio_url: Twilio audio URL
        max_retries: Maximum retry attempts within this function

    Returns:
        Audio bytes if successful, None otherwise
    """
    last_error = None

    for attempt in range(max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=TWILIO_DOWNLOAD_TIMEOUT) as client:
                response = await client.get(
                    audio_url,
                    auth=(settings.twilio_account_sid, settings.twilio_auth_token),
                    follow_redirects=True,
                )
                response.raise_for_status()

                audio_data = response.content
                logger.info(f"Downloaded {len(audio_data)} bytes from Twilio (attempt {attempt + 1})")
                return audio_data

        except httpx.TimeoutException as e:
            last_error = e
            logger.warning(f"Twilio download timeout (attempt {attempt + 1}/{max_retries + 1}): {e}")

        except httpx.HTTPStatusError as e:
            last_error = e
            # Don't retry on 4xx errors (except 429)
            if 400 <= e.response.status_code < 500 and e.response.status_code != 429:
                logger.error(f"Twilio download client error (no retry): {e}")
                return None
            logger.warning(f"Twilio download HTTP error (attempt {attempt + 1}/{max_retries + 1}): {e}")

        except Exception as e:
            last_error = e
            logger.warning(f"Twilio download error (attempt {attempt + 1}/{max_retries + 1}): {e}")

        # Wait before retry (simple linear backoff)
        if attempt < max_retries:
            import asyncio
            await asyncio.sleep(5 * (attempt + 1))

    logger.error(f"Failed to download audio after {max_retries + 1} attempts: {last_error}")
    return None


async def _process_recording_upload(
    call_sid: str,
    recording_sid: str,
    recording_url: str,
    recording_duration: int,
    audio_data: bytes,
) -> bool:
    """
    Process recording upload asynchronously via RecordingService.

    RecordingService handles:
    - Audio validation (MP3 signature, minimum size)
    - Geography-based S3 object key generation
    - S3 upload with exponential backoff retry
    - Redis fallback storage on failure
    - DLQ entry creation on exhausted retries

    Args:
        call_sid: Twilio call SID
        recording_sid: Twilio recording SID
        recording_url: Original Twilio recording URL
        recording_duration: Recording duration in seconds
        audio_data: MP3 audio bytes

    Returns:
        True if S3 upload succeeded, False if failed (but may have fallback)
    """
    # Get call record from database
    call_record = await CallRecord.find_one(
        CallRecord.call_tracking.call_sid == call_sid
    )

    if not call_record:
        logger.error(f"CallRecord not found for call_sid: {call_sid}")
        raise Exception(f"CallRecord not found: {call_sid}")

    # Prepare metadata for recording service
    metadata = {
        "domain": "patient_feedback",
        "geography_id": call_record.geography_id,
        "queue_id": call_record.queue_id,
        "recording_sid": recording_sid,
        "twilio_url": recording_url,
        "channels": "dual",
        "format": "mp3",
    }

    # Upload to MinIO via RecordingService
    # This method handles all safety mechanisms internally
    recording_service = RecordingService()
    success = await recording_service.upload_twilio_recording(
        call_record=call_record,
        audio_data=audio_data,
        duration_seconds=recording_duration,
        metadata=metadata,
    )

    # If upload succeeded and call has a recipient, update Recipient.recording_url
    if success and call_record.recipient_id:
        await _update_recipient_recording_url(call_record)

    return success


async def _update_recipient_recording_url(call_record: CallRecord) -> None:
    """
    Update Recipient.recording_url with presigned S3 URL after successful upload.

    This ensures the Recipient has the recording URL even if the initial sync
    ran before the recording was uploaded (race condition fix).

    Args:
        call_record: CallRecord with recording metadata
    """
    if not call_record.recipient_id:
        return

    if not call_record.recording or not call_record.recording.s3_object_key:
        logger.warning(
            f"Cannot update Recipient recording_url: no s3_object_key for call {call_record.id}"
        )
        return

    try:
        # Get Recipient
        recipient = await Recipient.get(ObjectId(call_record.recipient_id))
        if not recipient:
            logger.warning(f"Recipient not found: {call_record.recipient_id}")
            return

        # Generate presigned URL
        from backend.app.infrastructure.storage.s3_storage import S3StorageClient
        storage = S3StorageClient()
        recording_url = await storage.get_presigned_url(
            call_record.recording.s3_object_key,
            expiration=86400,  # 24 hours
        )

        # Update Recipient
        recipient.recording_url = recording_url
        recipient.updated_at = datetime.now(timezone.utc)
        await recipient.save()

        logger.info(
            f"Updated Recipient {recipient.id} recording_url from recording_download task"
        )

    except Exception as e:
        logger.error(
            f"Failed to update Recipient recording_url for call {call_record.id}: {e}",
            exc_info=True
        )
        # Don't fail the task - recording is still in S3
