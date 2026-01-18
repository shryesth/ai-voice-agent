"""
RecordingService for managing call recording uploads to S3/MinIO.

Handles:
- Converting raw audio to WAV format
- Uploading recordings to S3/MinIO
- Updating CallRecord with recording metadata
- Generating presigned URLs for playback
"""

import io
import logging
import wave
from datetime import datetime
from typing import TYPE_CHECKING

from backend.app.core.config import settings
from backend.app.infrastructure.storage import S3StorageClient
from backend.app.models.call_record import RecordingMetadata

if TYPE_CHECKING:
    from backend.app.models.call_record import CallRecord

logger = logging.getLogger(__name__)


class RecordingService:
    """
    Service for uploading and managing call recordings in S3/MinIO.

    Provides methods for converting raw audio to WAV format,
    uploading to S3/MinIO, and updating CallRecord documents.
    """

    def __init__(self):
        """Initialize the RecordingService with S3 client."""
        self.storage = S3StorageClient()

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
                uploaded_at=datetime.utcnow()
            )
            call_record.updated_at = datetime.utcnow()
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
        Upload Twilio recording (MP3 format) to MinIO.

        Args:
            call_record: CallRecord document to update
            audio_data: MP3 audio bytes from Twilio
            duration_seconds: Recording duration
            metadata: Recording metadata (recording_sid, channels, etc.)

        Returns:
            True if successful, False otherwise
        """
        try:
            # Generate S3 object key
            object_key = self._generate_object_key(
                call_record=call_record,
                format="mp3",  # Twilio provides MP3
            )

            # Upload to S3/MinIO
            url = await self.storage.upload_recording(
                object_key=object_key,
                audio_data=audio_data,
                content_type="audio/mpeg"  # MP3 MIME type
            )

            logger.info(f"Uploaded Twilio recording to S3: {object_key}")

            # Update CallRecord with recording metadata
            call_record.recording = RecordingMetadata(
                recording_url=url,
                s3_object_key=object_key,
                duration_seconds=duration_seconds,
                file_size_bytes=len(audio_data),
                sample_rate=8000,  # Twilio uses 8kHz for telephony
                num_channels=2,    # Dual-channel recording
                uploaded_at=datetime.utcnow(),
                recording_source="twilio",
                recording_sid=metadata.get("recording_sid"),
                recording_format="mp3"
            )

            await call_record.save()
            logger.info(f"Updated CallRecord with recording metadata: {call_record.id}")

            return True

        except Exception as e:
            logger.error(f"Error uploading Twilio recording: {e}", exc_info=True)
            return False

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

    def _generate_object_key(
        self,
        call_record: "CallRecord",
        format: str = "wav"
    ) -> str:
        """
        Generate S3 object key for the recording.

        Format: recordings/{campaign_id}/{year}/{month:02d}/{call_id}.{format}

        Args:
            call_record: CallRecord document
            format: File format extension (wav, mp3, etc.)

        Returns:
            S3 object key string
        """
        now = datetime.utcnow()
        campaign_id = str(call_record.campaign_id)
        call_id = str(call_record.id)

        return f"recordings/{campaign_id}/{now.year}/{now.month:02d}/{call_id}_dual.{format}"

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
        call_record.updated_at = datetime.utcnow()
        await call_record.save()

        logger.info(f"Deleted recording for call {call_record.id}")
        return result
