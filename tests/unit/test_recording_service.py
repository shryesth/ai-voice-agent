"""
Unit tests for RecordingService.

Tests recording upload and management functionality.
"""

import pytest
import pytest_asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
import wave
import io


class TestRecordingService:
    """Tests for RecordingService."""

    @pytest_asyncio.fixture
    async def mock_call_record(self):
        """Create a mock CallRecord for testing."""
        mock = MagicMock()
        mock.id = "test-call-id-12345"
        mock.geography_id = "test-geography-id"
        mock.recording = None
        mock.updated_at = None
        mock.save = AsyncMock()
        return mock

    @pytest.fixture
    def mock_storage_client(self):
        """Create a mock S3StorageClient."""
        mock = MagicMock()
        mock.upload_recording = AsyncMock(
            return_value="https://s3.example.com/bucket/recording.wav"
        )
        mock.get_presigned_url = MagicMock(
            return_value="https://s3.example.com/presigned/recording.wav"
        )
        mock.delete_recording = AsyncMock(return_value=True)
        return mock

    @pytest_asyncio.fixture
    async def recording_service(self, mock_storage_client):
        """Create a RecordingService instance with mocked storage."""
        from backend.app.services.recording_service import RecordingService

        service = RecordingService()
        service.storage = mock_storage_client
        return service

    @pytest.mark.asyncio
    async def test_upload_call_recording_success(
        self, recording_service, mock_call_record, mock_storage_client
    ):
        """Test successful recording upload."""
        audio_data = b"\x00\x01" * 1000  # 2000 bytes of audio
        sample_rate = 24000
        num_channels = 1

        result = await recording_service.upload_call_recording(
            call_record=mock_call_record,
            audio_data=audio_data,
            sample_rate=sample_rate,
            num_channels=num_channels,
        )

        # Verify storage upload was called
        mock_storage_client.upload_recording.assert_called_once()
        call_args = mock_storage_client.upload_recording.call_args

        # Verify object key format
        assert "recordings/" in call_args.kwargs["object_key"]
        assert mock_call_record.id in call_args.kwargs["object_key"]
        assert ".wav" in call_args.kwargs["object_key"]

        # Verify WAV data was created
        wav_data = call_args.kwargs["audio_data"]
        assert len(wav_data) > len(audio_data)  # WAV header added

        # Verify call record was updated
        assert mock_call_record.recording is not None
        assert mock_call_record.recording.recording_url is not None
        assert mock_call_record.recording.sample_rate == sample_rate
        assert mock_call_record.recording.num_channels == num_channels
        assert mock_call_record.save.called

    @pytest.mark.asyncio
    async def test_create_wav_format(self, recording_service):
        """Test WAV file creation from raw PCM audio."""
        audio_data = b"\x00\x01\x02\x03" * 100
        sample_rate = 24000
        num_channels = 1

        wav_data = recording_service._create_wav(audio_data, sample_rate, num_channels)

        # Verify WAV file is valid
        buffer = io.BytesIO(wav_data)
        with wave.open(buffer, "rb") as wf:
            assert wf.getnchannels() == num_channels
            assert wf.getframerate() == sample_rate
            assert wf.getsampwidth() == 2  # 16-bit
            assert wf.readframes(wf.getnframes()) == audio_data

    @pytest.mark.asyncio
    async def test_calculate_duration(self, recording_service):
        """Test audio duration calculation."""
        # 24000 samples per second, 2 bytes per sample, 1 channel
        # 48000 bytes = 24000 samples = 1 second
        audio_bytes = 48000
        sample_rate = 24000
        num_channels = 1

        duration = recording_service._calculate_duration(
            audio_bytes, sample_rate, num_channels
        )

        assert duration == 1

    @pytest.mark.asyncio
    async def test_calculate_duration_stereo(self, recording_service):
        """Test audio duration calculation for stereo audio."""
        # 24000 samples per second, 2 bytes per sample, 2 channels
        # 96000 bytes = 24000 samples = 1 second
        audio_bytes = 96000
        sample_rate = 24000
        num_channels = 2

        duration = recording_service._calculate_duration(
            audio_bytes, sample_rate, num_channels
        )

        assert duration == 1

    @pytest.mark.asyncio
    async def test_generate_object_key_format(
        self, recording_service, mock_call_record
    ):
        """Test S3 object key generation."""
        object_key = recording_service._generate_object_key(mock_call_record)

        # Verify key format: recordings/{geography_id}/{year}/{month}/call_recording_{call_id}_dual.wav
        assert object_key.startswith("recordings/")
        assert str(mock_call_record.geography_id) in object_key
        assert f"call_recording_{mock_call_record.id}" in object_key
        assert "_dual.wav" in object_key

    @pytest.mark.asyncio
    async def test_get_presigned_url(
        self, recording_service, mock_call_record, mock_storage_client
    ):
        """Test presigned URL generation."""
        from backend.app.models.call_record import RecordingMetadata

        # Set up recording metadata
        mock_call_record.recording = RecordingMetadata(
            recording_url="https://s3.example.com/recording.wav",
            s3_object_key="recordings/campaign/2026/01/call.wav",
            sample_rate=24000,
            num_channels=1,
        )

        url = recording_service.get_presigned_url(mock_call_record, expiration=3600)

        mock_storage_client.get_presigned_url.assert_called_once_with(
            object_key="recordings/campaign/2026/01/call.wav", expiration=3600
        )
        assert url == "https://s3.example.com/presigned/recording.wav"

    @pytest.mark.asyncio
    async def test_get_presigned_url_no_recording(
        self, recording_service, mock_call_record
    ):
        """Test presigned URL fails when no recording exists."""
        mock_call_record.recording = None

        with pytest.raises(ValueError, match="has no recording"):
            recording_service.get_presigned_url(mock_call_record)

    @pytest.mark.asyncio
    async def test_delete_recording(
        self, recording_service, mock_call_record, mock_storage_client
    ):
        """Test recording deletion."""
        from backend.app.models.call_record import RecordingMetadata

        mock_call_record.recording = RecordingMetadata(
            recording_url="https://s3.example.com/recording.wav",
            s3_object_key="recordings/campaign/2026/01/call.wav",
            sample_rate=24000,
            num_channels=1,
        )

        result = await recording_service.delete_recording(mock_call_record)

        assert result is True
        mock_storage_client.delete_recording.assert_called_once_with(
            object_key="recordings/campaign/2026/01/call.wav"
        )
        assert mock_call_record.recording is None
        assert mock_call_record.save.called

    @pytest.mark.asyncio
    async def test_delete_recording_no_recording(
        self, recording_service, mock_call_record
    ):
        """Test delete fails when no recording exists."""
        mock_call_record.recording = None

        with pytest.raises(ValueError, match="has no recording"):
            await recording_service.delete_recording(mock_call_record)
