"""
Celery task for splitting dual-channel MP3 recordings.

Handles:
- Downloading dual-channel MP3 from MinIO
- Splitting into caller/callee/mixed mono tracks
- Uploading split tracks back to MinIO
- Updating CallRecord with split S3 keys (cache)
"""
import logging
from datetime import datetime
from typing import Optional
from io import BytesIO
import asyncio

from pydub import AudioSegment

from backend.app.celery_app import celery_app
from backend.app.models.call_record import CallRecord
from backend.app.infrastructure.storage.s3_storage import S3StorageClient
from bson import ObjectId

logger = logging.getLogger(__name__)


@celery_app.task(
    name="split_recording_task",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def split_recording_task(self, call_id: str):
    """
    Split dual-channel recording into caller, callee, and mixed tracks.

    Steps:
    1. Fetch dual-channel MP3 from MinIO
    2. Split using pydub:
       - Extract left channel (caller)
       - Extract right channel (callee)
       - Mix both channels (mono)
    3. Upload 3 new MP3s to MinIO
    4. Update CallRecord with S3 keys

    Args:
        call_id: CallRecord ID

    Returns:
        Dict with S3 keys for split recordings
    """
    logger.info(f"📂 Starting recording split for call: {call_id}")

    try:
        # Get call record
        call_record = asyncio.run(CallRecord.get(ObjectId(call_id)))

        if not call_record or not call_record.recording:
            raise Exception(f"Call record or recording not found: {call_id}")

        dual_s3_key = call_record.recording.s3_object_key
        logger.info(f"Fetching dual recording from MinIO: {dual_s3_key}")

        # Download dual-channel MP3 from MinIO
        s3_client = S3StorageClient()
        dual_audio_bytes = asyncio.run(s3_client.download_recording(dual_s3_key))

        if not dual_audio_bytes:
            raise Exception(f"Failed to download dual recording: {dual_s3_key}")

        logger.info(f"Downloaded {len(dual_audio_bytes)} bytes")

        # Load audio with pydub
        audio = AudioSegment.from_file(BytesIO(dual_audio_bytes), format="mp3")

        # Verify it's stereo
        if audio.channels != 2:
            raise Exception(f"Expected 2 channels, got {audio.channels}")

        logger.info(f"Audio loaded: {audio.duration_seconds}s, {audio.channels} channels")

        # Split channels
        caller_audio = audio.split_to_mono()[0]  # Left channel (caller)
        callee_audio = audio.split_to_mono()[1]  # Right channel (callee)

        # Mix to mono (average both channels)
        mixed_audio = audio.set_channels(1)

        logger.info("Channels split successfully")

        # Export to MP3 bytes
        caller_bytes = BytesIO()
        callee_bytes = BytesIO()
        mixed_bytes = BytesIO()

        caller_audio.export(caller_bytes, format="mp3", bitrate="64k")
        callee_audio.export(callee_bytes, format="mp3", bitrate="64k")
        mixed_audio.export(mixed_bytes, format="mp3", bitrate="64k")

        logger.info("Exported split tracks to MP3")

        # Generate S3 keys
        base_key = dual_s3_key.replace("_dual.mp3", "")
        caller_s3_key = f"{base_key}_caller.mp3"
        callee_s3_key = f"{base_key}_callee.mp3"
        mixed_s3_key = f"{base_key}_mixed.mp3"

        # Upload to MinIO
        success_caller = asyncio.run(s3_client.upload_recording(
            object_key=caller_s3_key,
            audio_data=caller_bytes.getvalue(),
            content_type="audio/mpeg"
        ))

        success_callee = asyncio.run(s3_client.upload_recording(
            object_key=callee_s3_key,
            audio_data=callee_bytes.getvalue(),
            content_type="audio/mpeg"
        ))

        success_mixed = asyncio.run(s3_client.upload_recording(
            object_key=mixed_s3_key,
            audio_data=mixed_bytes.getvalue(),
            content_type="audio/mpeg"
        ))

        if not (success_caller and success_callee and success_mixed):
            raise Exception("Failed to upload one or more split recordings")

        logger.info(f"✅ Uploaded all split tracks to MinIO")

        # Update CallRecord
        call_record.recording.caller_s3_key = caller_s3_key
        call_record.recording.callee_s3_key = callee_s3_key
        call_record.recording.mixed_s3_key = mixed_s3_key
        call_record.recording.split_created_at = datetime.utcnow()

        asyncio.run(call_record.save())

        logger.info(f"✅ Split recording complete for call: {call_id}")

        return {
            "caller_s3_key": caller_s3_key,
            "callee_s3_key": callee_s3_key,
            "mixed_s3_key": mixed_s3_key,
        }

    except Exception as e:
        logger.error(f"❌ Error splitting recording: {e}", exc_info=True)
        raise self.retry(exc=e)
