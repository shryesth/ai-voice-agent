"""
RecordingService for managing call recording uploads to S3/MinIO.

Handles:
- Converting raw audio to WAV format
- Uploading recordings to S3/MinIO with retry logic
- Audio validation before upload
- Redis fallback storage for failed uploads
- Dead-letter queue for persistent failures
- Updating CallRecord with recording metadata
- Generating presigned URLs for playback
"""

import base64
import io
import json
import logging
import wave
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Optional, Tuple

import redis.asyncio as redis

from backend.app.core.config import settings
from backend.app.infrastructure.storage import S3StorageClient, S3UploadError
from backend.app.models.call_record import RecordingMetadata
from backend.app.models.recording_dlq import RecordingDLQ, ErrorEntry

if TYPE_CHECKING:
    from backend.app.models.call_record import CallRecord

logger = logging.getLogger(__name__)

# MP3 file signatures (magic bytes)
MP3_SIGNATURES = [
    b'\xff\xfb',  # MPEG Audio Layer 3, no CRC
    b'\xff\xfa',  # MPEG Audio Layer 3, with CRC
    b'\xff\xf3',  # MPEG Audio Layer 3, MPEG 2
    b'\xff\xf2',  # MPEG Audio Layer 3, MPEG 2 with CRC
    b'ID3',       # ID3v2 tag (common in MP3 files)
]

# WAV file signature
WAV_SIGNATURE = b'RIFF'


class AudioValidationError(Exception):
    """Exception raised when audio validation fails."""

    def __init__(self, message: str, audio_size: int = 0):
        super().__init__(message)
        self.audio_size = audio_size


class RecordingFallbackStorage:
    """
    Redis-based fallback storage for recordings when S3 upload fails.

    Stores audio data in Redis with TTL to allow retry attempts.
    """

    KEY_PREFIX = "recording_fallback:"
    METADATA_PREFIX = "recording_fallback_meta:"

    def __init__(self):
        """Initialize with Redis client."""
        self._redis: Optional[redis.Redis] = None

    @property
    async def redis_client(self) -> redis.Redis:
        """Lazy-initialize Redis client."""
        if self._redis is None:
            self._redis = redis.from_url(settings.redis_url)
        return self._redis

    async def store_fallback(
        self,
        call_id: str,
        audio_data: bytes,
        metadata: dict
    ) -> Tuple[str, datetime]:
        """
        Store audio data in Redis fallback.

        Args:
            call_id: CallRecord ID
            audio_data: Raw audio bytes
            metadata: Recording metadata dict

        Returns:
            Tuple of (redis_key, expiry_datetime)
        """
        client = await self.redis_client
        ttl_seconds = settings.recording_fallback_ttl_days * 86400

        # Store audio data (base64 encoded)
        audio_key = f"{self.KEY_PREFIX}{call_id}"
        await client.setex(
            audio_key,
            ttl_seconds,
            base64.b64encode(audio_data)
        )

        # Store metadata separately
        meta_key = f"{self.METADATA_PREFIX}{call_id}"
        await client.setex(
            meta_key,
            ttl_seconds,
            json.dumps(metadata)
        )

        expiry = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)

        logger.info(
            f"Stored recording fallback in Redis: {audio_key} "
            f"({len(audio_data)} bytes, expires {expiry.isoformat()})"
        )

        return audio_key, expiry

    async def get_fallback(self, call_id: str) -> Optional[Tuple[bytes, dict]]:
        """
        Retrieve audio data from Redis fallback.

        Args:
            call_id: CallRecord ID

        Returns:
            Tuple of (audio_data, metadata) or None if not found
        """
        client = await self.redis_client

        audio_key = f"{self.KEY_PREFIX}{call_id}"
        meta_key = f"{self.METADATA_PREFIX}{call_id}"

        # Get audio data
        audio_b64 = await client.get(audio_key)
        if not audio_b64:
            return None

        # Get metadata
        meta_json = await client.get(meta_key)
        metadata = json.loads(meta_json) if meta_json else {}

        audio_data = base64.b64decode(audio_b64)

        logger.info(f"Retrieved recording fallback from Redis: {call_id} ({len(audio_data)} bytes)")

        return audio_data, metadata

    async def delete_fallback(self, call_id: str) -> bool:
        """
        Delete fallback data after successful upload.

        Args:
            call_id: CallRecord ID

        Returns:
            True if deleted
        """
        client = await self.redis_client

        audio_key = f"{self.KEY_PREFIX}{call_id}"
        meta_key = f"{self.METADATA_PREFIX}{call_id}"

        deleted = await client.delete(audio_key, meta_key)
        logger.info(f"Deleted recording fallback from Redis: {call_id} (keys deleted: {deleted})")

        return deleted > 0

    async def has_fallback(self, call_id: str) -> bool:
        """Check if fallback exists for call."""
        client = await self.redis_client
        return await client.exists(f"{self.KEY_PREFIX}{call_id}") > 0


class RecordingService:
    """
    Service for uploading and managing call recordings in S3/MinIO.

    Provides methods for converting raw audio to WAV format,
    uploading to S3/MinIO with retry and fallback, and updating
    CallRecord documents.
    """

    def __init__(self):
        """Initialize the RecordingService with S3 client and fallback storage."""
        self.storage = S3StorageClient()
        self.fallback = RecordingFallbackStorage()

    def validate_audio_data(
        self,
        audio_data: bytes,
        expected_format: str = "mp3"
    ) -> Tuple[bool, str]:
        """
        Validate audio data before upload.

        Checks:
        - Minimum size requirement
        - Valid file signature (magic bytes)

        Args:
            audio_data: Raw audio bytes
            expected_format: Expected format ('mp3' or 'wav')

        Returns:
            Tuple of (is_valid, error_message)
        """
        min_size = settings.recording_min_size_bytes

        # Check minimum size
        if not audio_data or len(audio_data) < min_size:
            return False, f"Audio too small: {len(audio_data) if audio_data else 0} bytes (min: {min_size})"

        # Check file signature based on format
        if expected_format == "mp3":
            if not any(audio_data.startswith(sig) for sig in MP3_SIGNATURES):
                # Log first few bytes for debugging
                first_bytes = audio_data[:10].hex() if len(audio_data) >= 10 else audio_data.hex()
                return False, f"Invalid MP3 signature. First bytes: {first_bytes}"
        elif expected_format == "wav":
            if not audio_data.startswith(WAV_SIGNATURE):
                first_bytes = audio_data[:10].hex() if len(audio_data) >= 10 else audio_data.hex()
                return False, f"Invalid WAV signature. First bytes: {first_bytes}"

        return True, ""

    def _generate_object_key(
        self,
        call_record: "CallRecord",
        format: str = "wav"
    ) -> str:
        """
        Generate S3 object key for the recording.

        Format: {s3_path_prefix}recordings/{geography_id}/{year}/{month:02d}/call_recording_{call_id}_dual.{format}

        Examples:
        - Development: recordings/geo123/2026/01/call_recording_call456_dual.mp3
        - UAT: uat/recordings/geo123/2026/01/call_recording_call456_dual.mp3
        - Production: prod/recordings/geo123/2026/01/call_recording_call456_dual.mp3

        Uses geography_id as primary partition (always available).

        Args:
            call_record: CallRecord document
            format: File format extension (wav, mp3, etc.)

        Returns:
            S3 object key string
        """
        now = datetime.now(timezone.utc)

        # Geography ID is always present (use "unknown_geography" as fallback)
        geography_id = call_record.geography_id or "unknown_geography"

        # Get call ID
        call_id = str(call_record.id)

        # Build base path with call_recording_ prefix
        base_path = f"recordings/{geography_id}/{now.year}/{now.month:02d}/call_recording_{call_id}_dual.{format}"

        # Add environment prefix if configured
        prefix = settings.s3_path_prefix
        return f"{prefix}{base_path}" if prefix else base_path

    async def upload_call_recording(
        self,
        call_record: "CallRecord",
        audio_data: bytes,
        sample_rate: int,
        num_channels: int
    ) -> "CallRecord":
        """
        Upload call recording to S3/MinIO and update CallRecord.

        Converts raw PCM audio to WAV format, uploads to S3/MinIO,
        and updates the CallRecord with recording metadata.

        Args:
            call_record: CallRecord document to update
            audio_data: Raw PCM audio bytes (16-bit signed integers)
            sample_rate: Audio sample rate in Hz
            num_channels: Number of audio channels

        Returns:
            Updated CallRecord with recording metadata

        Raises:
            Exception: If upload fails
        """
        try:
            # Generate S3 object key
            object_key = self._generate_object_key(call_record)

            # Convert raw PCM to WAV format
            wav_data = self._create_wav(audio_data, sample_rate, num_channels)

            # Calculate duration
            duration_seconds = self._calculate_duration(
                len(audio_data),
                sample_rate,
                num_channels
            )

            # Upload to S3/MinIO
            url = await self.storage.upload_recording(
                object_key=object_key,
                audio_data=wav_data,
                content_type="audio/wav"
            )

            # Update CallRecord with recording metadata
            call_record.recording = RecordingMetadata(
                recording_url=url,
                s3_object_key=object_key,
                duration_seconds=duration_seconds,
                file_size_bytes=len(wav_data),
                sample_rate=sample_rate,
                num_channels=num_channels,
                uploaded_at=datetime.now(timezone.utc),
                upload_status="completed",
                upload_attempts=1,
            )
            call_record.updated_at = datetime.now(timezone.utc)
            await call_record.save()

            logger.info(
                f"Recording uploaded for call {call_record.id}: "
                f"{object_key} ({len(wav_data)} bytes, {duration_seconds}s)"
            )

            return call_record

        except Exception as e:
            logger.error(
                f"Failed to upload recording for call {call_record.id}: {e}",
                exc_info=True
            )
            raise

    async def upload_twilio_recording(
        self,
        call_record: "CallRecord",
        audio_data: bytes,
        duration_seconds: int,
        metadata: dict,
    ) -> bool:
        """
        Upload Twilio recording (MP3 format) to MinIO with full safety mechanisms.

        Includes:
        - Audio validation
        - Exponential backoff retry
        - Redis fallback on failure
        - DLQ entry on exhausted retries

        Args:
            call_record: CallRecord document to update
            audio_data: MP3 audio bytes from Twilio
            duration_seconds: Recording duration
            metadata: Recording metadata (recording_sid, channels, etc.)

        Returns:
            True if successful (including fallback), False on complete failure
        """
        call_id = str(call_record.id)

        # Initialize recording metadata with pending status
        if not call_record.recording:
            call_record.recording = RecordingMetadata(
                recording_source="twilio",
                recording_sid=metadata.get("recording_sid"),
                recording_format="mp3",
                duration_seconds=duration_seconds,
                file_size_bytes=len(audio_data),
                upload_status="pending",
                upload_attempts=0,
            )

        try:
            # 1. Validate audio data
            is_valid, error_msg = self.validate_audio_data(audio_data, expected_format="mp3")
            if not is_valid:
                logger.error(f"Audio validation failed for call {call_id}: {error_msg}")
                raise AudioValidationError(error_msg, len(audio_data))

            # 2. Generate S3 object key (geography-based)
            object_key = self._generate_object_key(
                call_record=call_record,
                format="mp3",
            )

            # 3. Update status to uploading
            call_record.recording.upload_status = "uploading"
            call_record.recording.upload_attempts += 1
            await call_record.save()

            # 4. Upload to S3/MinIO with retry
            url = await self.storage.upload_recording_with_retry(
                object_key=object_key,
                audio_data=audio_data,
                content_type="audio/mpeg"
            )

            logger.info(f"Uploaded Twilio recording to S3: {object_key}")

            # 5. Update CallRecord with success
            call_record.recording.recording_url = url
            call_record.recording.s3_object_key = object_key
            call_record.recording.uploaded_at = datetime.now(timezone.utc)
            call_record.recording.upload_status = "completed"
            call_record.recording.sample_rate = 8000
            call_record.recording.num_channels = 2
            call_record.updated_at = datetime.now(timezone.utc)

            await call_record.save()
            logger.info(f"Updated CallRecord with recording metadata: {call_id}")

            # 6. Clean up any existing Redis fallback
            if await self.fallback.has_fallback(call_id):
                await self.fallback.delete_fallback(call_id)

            return True

        except S3UploadError as e:
            # S3 upload failed after all retries
            logger.error(f"S3 upload failed for call {call_id} after {e.attempts} attempts: {e}")
            return await self._handle_upload_failure(
                call_record=call_record,
                audio_data=audio_data,
                metadata=metadata,
                error=e,
                error_type="S3UploadError",
            )

        except AudioValidationError as e:
            # Audio validation failed - still store in DLQ for investigation
            logger.error(f"Audio validation failed for call {call_id}: {e}")
            return await self._handle_upload_failure(
                call_record=call_record,
                audio_data=audio_data,
                metadata=metadata,
                error=e,
                error_type="AudioValidationError",
            )

        except Exception as e:
            # Unexpected error
            logger.error(f"Unexpected error uploading recording for call {call_id}: {e}", exc_info=True)
            return await self._handle_upload_failure(
                call_record=call_record,
                audio_data=audio_data,
                metadata=metadata,
                error=e,
                error_type="UnexpectedError",
            )

    async def _handle_upload_failure(
        self,
        call_record: "CallRecord",
        audio_data: bytes,
        metadata: dict,
        error: Exception,
        error_type: str,
    ) -> bool:
        """
        Handle upload failure by storing in Redis fallback and creating DLQ entry.

        Args:
            call_record: The CallRecord being processed
            audio_data: Raw audio bytes
            metadata: Recording metadata
            error: The exception that occurred
            error_type: Type of error for categorization

        Returns:
            True if fallback storage succeeded, False otherwise
        """
        call_id = str(call_record.id)
        error_message = str(error)

        try:
            # 1. Store in Redis fallback
            redis_key, expiry = await self.fallback.store_fallback(
                call_id=call_id,
                audio_data=audio_data,
                metadata={
                    **metadata,
                    "duration_seconds": call_record.recording.duration_seconds if call_record.recording else None,
                    "file_size_bytes": len(audio_data),
                }
            )

            # 2. Create or update DLQ entry
            dlq_entry = await RecordingDLQ.find_one(RecordingDLQ.call_id == call_id)

            if dlq_entry:
                # Update existing entry
                dlq_entry.add_error(
                    error_type=error_type,
                    error_message=error_message,
                    attempt_number=dlq_entry.failure_count + 1
                )
                dlq_entry.has_redis_fallback = True
                dlq_entry.redis_fallback_key = redis_key
                dlq_entry.redis_fallback_expires_at = expiry
                await dlq_entry.save()
            else:
                # Create new entry
                dlq_entry = RecordingDLQ(
                    call_id=call_id,
                    call_sid=call_record.call_tracking.call_sid if call_record.call_tracking else None,
                    recording_sid=metadata.get("recording_sid"),
                    geography_id=call_record.geography_id or "unknown_geography",
                    is_test_call=call_record.is_test_call,
                    failure_reason=f"{error_type}: {error_message}",
                    failure_count=1,
                    error_history=[
                        ErrorEntry(
                            error_type=error_type,
                            error_message=error_message,
                            attempt_number=1
                        )
                    ],
                    has_redis_fallback=True,
                    redis_fallback_key=redis_key,
                    redis_fallback_expires_at=expiry,
                    recording_duration_seconds=call_record.recording.duration_seconds if call_record.recording else None,
                    recording_size_bytes=len(audio_data),
                    twilio_recording_url=metadata.get("twilio_url"),
                )
                await dlq_entry.insert()

            # 3. Update call record status
            if call_record.recording:
                call_record.recording.upload_status = "dlq"
                call_record.recording.last_upload_error = error_message
                call_record.recording.dlq_entry_id = str(dlq_entry.id)
            else:
                call_record.recording = RecordingMetadata(
                    recording_source="twilio",
                    recording_sid=metadata.get("recording_sid"),
                    recording_format="mp3",
                    file_size_bytes=len(audio_data),
                    upload_status="dlq",
                    last_upload_error=error_message,
                    dlq_entry_id=str(dlq_entry.id),
                )

            call_record.updated_at = datetime.now(timezone.utc)
            await call_record.save()

            logger.info(
                f"Recording for call {call_id} stored in Redis fallback "
                f"(DLQ entry: {dlq_entry.id}, expires: {expiry.isoformat()})"
            )

            return True  # Fallback succeeded

        except Exception as fallback_error:
            logger.error(
                f"Failed to store recording fallback for call {call_id}: {fallback_error}",
                exc_info=True
            )

            # Update call record with failed status
            if call_record.recording:
                call_record.recording.upload_status = "failed"
                call_record.recording.last_upload_error = f"Fallback failed: {fallback_error}"
            call_record.updated_at = datetime.now(timezone.utc)
            await call_record.save()

            return False

    async def retry_from_fallback(self, call_id: str) -> bool:
        """
        Retry upload from Redis fallback storage.

        Args:
            call_id: CallRecord ID

        Returns:
            True if retry succeeded
        """
        # Get fallback data
        fallback_data = await self.fallback.get_fallback(call_id)
        if not fallback_data:
            logger.warning(f"No fallback data found for call {call_id}")
            return False

        audio_data, metadata = fallback_data

        # Get call record
        from backend.app.models.call_record import CallRecord
        call_record = await CallRecord.get(call_id)
        if not call_record:
            logger.error(f"CallRecord not found: {call_id}")
            return False

        # Attempt upload
        success = await self.upload_twilio_recording(
            call_record=call_record,
            audio_data=audio_data,
            duration_seconds=metadata.get("duration_seconds", 0),
            metadata=metadata,
        )

        if success and call_record.recording and call_record.recording.upload_status == "completed":
            # Mark DLQ entry as resolved
            dlq_entry = await RecordingDLQ.find_one(RecordingDLQ.call_id == call_id)
            if dlq_entry:
                dlq_entry.mark_resolved(method="retry_success", resolved_by="system")
                await dlq_entry.save()

            # Delete fallback data
            await self.fallback.delete_fallback(call_id)

            logger.info(f"Successfully retried upload from fallback for call {call_id}")

        return success

    def _create_wav(
        self,
        audio_data: bytes,
        sample_rate: int,
        num_channels: int
    ) -> bytes:
        """
        Convert raw PCM audio to WAV format.

        Args:
            audio_data: Raw PCM audio bytes (16-bit signed integers)
            sample_rate: Audio sample rate in Hz
            num_channels: Number of audio channels

        Returns:
            WAV file bytes
        """
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wf:
            wf.setnchannels(num_channels)
            wf.setsampwidth(2)  # 16-bit PCM = 2 bytes per sample
            wf.setframerate(sample_rate)
            wf.writeframes(audio_data)

        return buffer.getvalue()

    def _calculate_duration(
        self,
        audio_bytes: int,
        sample_rate: int,
        num_channels: int
    ) -> int:
        """
        Calculate audio duration in seconds.

        Args:
            audio_bytes: Size of raw PCM audio in bytes
            sample_rate: Audio sample rate in Hz
            num_channels: Number of audio channels

        Returns:
            Duration in seconds (rounded)
        """
        # 16-bit PCM = 2 bytes per sample
        bytes_per_sample = 2 * num_channels
        total_samples = audio_bytes // bytes_per_sample
        duration = total_samples / sample_rate
        return round(duration)

    def get_presigned_url(
        self,
        call_record: "CallRecord",
        expiration: int = 3600
    ) -> str:
        """
        Generate a presigned URL for downloading a call recording.

        Args:
            call_record: CallRecord with recording metadata
            expiration: URL expiration time in seconds (default: 1 hour)

        Returns:
            Presigned URL for downloading the recording

        Raises:
            ValueError: If call has no recording
        """
        if not call_record.recording or not call_record.recording.s3_object_key:
            raise ValueError(f"Call {call_record.id} has no recording")

        return self.storage.get_presigned_url(
            object_key=call_record.recording.s3_object_key,
            expiration=expiration
        )

    async def delete_recording(self, call_record: "CallRecord") -> bool:
        """
        Delete a call recording from S3/MinIO.

        Args:
            call_record: CallRecord with recording metadata

        Returns:
            True if deletion was successful

        Raises:
            ValueError: If call has no recording
        """
        if not call_record.recording or not call_record.recording.s3_object_key:
            raise ValueError(f"Call {call_record.id} has no recording")

        result = await self.storage.delete_recording(
            object_key=call_record.recording.s3_object_key
        )

        # Clear recording metadata
        call_record.recording = None
        call_record.updated_at = datetime.now(timezone.utc)
        await call_record.save()

        logger.info(f"Deleted recording for call {call_record.id}")
        return result
