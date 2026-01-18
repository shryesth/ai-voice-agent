"""
Celery task for downloading Twilio recordings and uploading to MinIO.
"""
import logging
from typing import Optional

import httpx
from twilio.rest import Client

from backend.app.celery_app import celery_app, get_worker_event_loop
from backend.app.core.config import settings
from backend.app.core.database import db
from backend.app.models.call_record import CallRecord
from backend.app.services.recording_service import RecordingService

logger = logging.getLogger(__name__)


@celery_app.task(
    name="download_twilio_recording",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def download_twilio_recording(
    self,
    call_sid: str,
    recording_sid: str,
    recording_url: str,
    recording_duration: int,
):
    """
    Download recording from Twilio and upload to MinIO.

    Args:
        call_sid: Twilio call SID
        recording_sid: Twilio recording SID
        recording_url: Twilio recording URL (JSON endpoint)
        recording_duration: Recording duration in seconds
    """
    logger.info(f"📥 Starting recording download for call: {call_sid}")

    try:
        # Initialize Twilio client
        twilio_client = Client(settings.twilio_account_sid, settings.twilio_auth_token)

        # Fetch recording metadata from Twilio
        recording = twilio_client.recordings(recording_sid).fetch()

        # Construct audio download URL (convert .json to .mp3)
        audio_url = f"https://api.twilio.com{recording.uri.replace('.json', '.mp3')}"
        logger.info(f"📥 Downloading recording from: {audio_url}")

        # Get worker event loop for async operations
        loop = get_worker_event_loop()

        # Download audio from Twilio with authentication
        audio_data = loop.run_until_complete(_download_audio(audio_url))

        if not audio_data:
            logger.error(f"❌ Failed to download recording for call: {call_sid}")
            raise Exception("Failed to download audio from Twilio")

        logger.info(f"✅ Downloaded recording: {len(audio_data)} bytes")

        # Process recording upload in async context
        success = loop.run_until_complete(_process_recording_upload(
            call_sid=call_sid,
            recording_sid=recording_sid,
            recording_url=recording_url,
            recording_duration=recording_duration,
            audio_data=audio_data,
        ))

        if not success:
            logger.error(f"❌ Failed to upload recording to MinIO for call: {call_sid}")
            raise Exception("Failed to upload recording to MinIO")

        logger.info(f"✅ Uploaded recording to MinIO for call: {call_sid}")

        # Delete recording from Twilio to save costs
        try:
            twilio_client.recordings(recording_sid).delete()
            logger.info(f"🗑️ Deleted recording from Twilio: {recording_sid}")
        except Exception as delete_error:
            logger.warning(f"⚠️ Failed to delete Twilio recording: {delete_error}")
            # Don't fail the task if Twilio deletion fails

        logger.info(f"✅ Recording processing complete for call: {call_sid}")

    except Exception as e:
        logger.error(f"❌ Error processing recording: {e}", exc_info=True)
        # Retry with exponential backoff
        raise self.retry(exc=e)


async def _download_audio(audio_url: str) -> Optional[bytes]:
    """Download audio from Twilio using authenticated HTTP request."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                audio_url,
                auth=(settings.twilio_account_sid, settings.twilio_auth_token)
            )
            response.raise_for_status()
            return response.content
    except Exception as e:
        logger.error(f"❌ Failed to download audio: {e}")
        return None


async def _process_recording_upload(
    call_sid: str,
    recording_sid: str,
    recording_url: str,
    recording_duration: int,
    audio_data: bytes,
) -> bool:
    """
    Process recording upload asynchronously.
    
    This function handles all async database and storage operations.
    """
    # Get call record from database
    call_record = await CallRecord.find_one(
        CallRecord.call_tracking.call_sid == call_sid
    )

    if not call_record:
        logger.error(f"❌ CallRecord not found for call_sid: {call_sid}")
        raise Exception(f"CallRecord not found: {call_sid}")

    # Prepare metadata
    metadata = {
        "domain": "patient_feedback",
        "campaign_id": str(call_record.campaign_id),
        "recording_sid": recording_sid,
        "twilio_url": recording_url,
        "channels": "dual",
        "format": "mp3",
    }

    # Upload to MinIO via RecordingService
    recording_service = RecordingService()
    success = await recording_service.upload_twilio_recording(
        call_record=call_record,
        audio_data=audio_data,
        duration_seconds=recording_duration,
        metadata=metadata,
    )

    return success
