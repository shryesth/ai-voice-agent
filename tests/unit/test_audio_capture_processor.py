"""
Unit tests for AudioCaptureProcessor.

Tests the audio capture and recording functionality.
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from pipecat.frames.frames import AudioRawFrame, EndFrame, CancelFrame, Frame
from pipecat.processors.frame_processor import FrameDirection


class TestAudioCaptureProcessor:
    """Tests for AudioCaptureProcessor."""

    @pytest_asyncio.fixture
    async def mock_call_record(self):
        """Create a mock CallRecord for testing."""
        mock = MagicMock()
        mock.id = "test-call-id"
        mock.campaign_id = "test-campaign-id"
        mock.recording = None
        mock.save = AsyncMock()
        return mock

    @pytest_asyncio.fixture
    async def audio_processor(self, mock_call_record):
        """Create an AudioCaptureProcessor instance."""
        from backend.app.domains.patient_feedback.audio_capture_processor import (
            AudioCaptureProcessor,
        )

        on_complete = AsyncMock()
        processor = AudioCaptureProcessor(
            call_record=mock_call_record,
            sample_rate=24000,
            num_channels=1,
            on_recording_complete=on_complete,
        )
        processor.push_frame = AsyncMock()
        return processor

    @pytest.mark.asyncio
    async def test_captures_audio_when_recording(
        self, audio_processor, mock_call_record
    ):
        """Test that audio is captured when recording is enabled."""
        audio_processor.start_recording()

        # Create audio frame
        audio_data = b"\x00\x01\x02\x03" * 100
        frame = AudioRawFrame(audio=audio_data, sample_rate=24000, num_channels=1)

        await audio_processor.process_frame(frame, FrameDirection.DOWNSTREAM)

        # Verify audio was captured
        assert audio_processor.has_audio
        assert len(audio_processor.audio_data) == len(audio_data)

    @pytest.mark.asyncio
    async def test_does_not_capture_before_start(
        self, audio_processor, mock_call_record
    ):
        """Test that audio is not captured before start_recording is called."""
        # Don't call start_recording

        audio_data = b"\x00\x01\x02\x03" * 100
        frame = AudioRawFrame(audio=audio_data, sample_rate=24000, num_channels=1)

        await audio_processor.process_frame(frame, FrameDirection.DOWNSTREAM)

        # Verify no audio was captured
        assert not audio_processor.has_audio

    @pytest.mark.asyncio
    async def test_stop_recording(self, audio_processor, mock_call_record):
        """Test that stop_recording stops audio capture."""
        audio_processor.start_recording()

        # Capture some audio
        frame1 = AudioRawFrame(audio=b"\x00\x01", sample_rate=24000, num_channels=1)
        await audio_processor.process_frame(frame1, FrameDirection.DOWNSTREAM)

        audio_processor.stop_recording()

        # Try to capture more audio
        frame2 = AudioRawFrame(audio=b"\x02\x03", sample_rate=24000, num_channels=1)
        await audio_processor.process_frame(frame2, FrameDirection.DOWNSTREAM)

        # Only first audio should be captured
        assert len(audio_processor.audio_data) == 2

    @pytest.mark.asyncio
    @patch("backend.app.domains.patient_feedback.audio_capture_processor.settings")
    async def test_triggers_upload_on_end_frame(
        self, mock_settings, audio_processor, mock_call_record
    ):
        """Test that recording upload is triggered on EndFrame."""
        mock_settings.recording_enabled = True

        audio_processor.start_recording()

        # Capture some audio
        audio_data = b"\x00\x01\x02\x03"
        frame = AudioRawFrame(audio=audio_data, sample_rate=24000, num_channels=1)
        await audio_processor.process_frame(frame, FrameDirection.DOWNSTREAM)

        # Send EndFrame
        end_frame = EndFrame()
        await audio_processor.process_frame(end_frame, FrameDirection.DOWNSTREAM)

        # Verify upload callback was called
        audio_processor.on_recording_complete.assert_called_once()
        call_args = audio_processor.on_recording_complete.call_args
        assert call_args.kwargs["call_record"] == mock_call_record
        assert call_args.kwargs["audio_data"] == audio_data
        assert call_args.kwargs["sample_rate"] == 24000
        assert call_args.kwargs["num_channels"] == 1

    @pytest.mark.asyncio
    @patch("backend.app.domains.patient_feedback.audio_capture_processor.settings")
    async def test_triggers_upload_on_cancel_frame(
        self, mock_settings, audio_processor, mock_call_record
    ):
        """Test that recording upload is triggered on CancelFrame."""
        mock_settings.recording_enabled = True

        audio_processor.start_recording()

        # Capture some audio
        audio_data = b"\x00\x01\x02\x03"
        frame = AudioRawFrame(audio=audio_data, sample_rate=24000, num_channels=1)
        await audio_processor.process_frame(frame, FrameDirection.DOWNSTREAM)

        # Send CancelFrame
        cancel_frame = CancelFrame()
        await audio_processor.process_frame(cancel_frame, FrameDirection.DOWNSTREAM)

        # Verify upload callback was called
        audio_processor.on_recording_complete.assert_called_once()

    @pytest.mark.asyncio
    @patch("backend.app.domains.patient_feedback.audio_capture_processor.settings")
    async def test_skips_upload_when_disabled(
        self, mock_settings, audio_processor, mock_call_record
    ):
        """Test that upload is skipped when recording is disabled."""
        mock_settings.recording_enabled = False

        audio_processor.start_recording()

        # Capture some audio
        frame = AudioRawFrame(
            audio=b"\x00\x01\x02\x03", sample_rate=24000, num_channels=1
        )
        await audio_processor.process_frame(frame, FrameDirection.DOWNSTREAM)

        # Send EndFrame
        end_frame = EndFrame()
        await audio_processor.process_frame(end_frame, FrameDirection.DOWNSTREAM)

        # Verify upload callback was NOT called
        audio_processor.on_recording_complete.assert_not_called()

    @pytest.mark.asyncio
    async def test_passes_frames_through(self, audio_processor, mock_call_record):
        """Test that all frames are passed through to next processor."""
        audio_processor.start_recording()

        frame = AudioRawFrame(
            audio=b"\x00\x01\x02\x03", sample_rate=24000, num_channels=1
        )
        await audio_processor.process_frame(frame, FrameDirection.DOWNSTREAM)

        # Verify frame was pushed to next processor
        audio_processor.push_frame.assert_called_once_with(
            frame, FrameDirection.DOWNSTREAM
        )

    @pytest.mark.asyncio
    async def test_accumulates_multiple_audio_frames(
        self, audio_processor, mock_call_record
    ):
        """Test that multiple audio frames are accumulated."""
        audio_processor.start_recording()

        frame1 = AudioRawFrame(audio=b"\x00\x01", sample_rate=24000, num_channels=1)
        frame2 = AudioRawFrame(audio=b"\x02\x03", sample_rate=24000, num_channels=1)
        frame3 = AudioRawFrame(audio=b"\x04\x05", sample_rate=24000, num_channels=1)

        await audio_processor.process_frame(frame1, FrameDirection.DOWNSTREAM)
        await audio_processor.process_frame(frame2, FrameDirection.DOWNSTREAM)
        await audio_processor.process_frame(frame3, FrameDirection.DOWNSTREAM)

        # Verify all audio was accumulated
        assert audio_processor.audio_data == b"\x00\x01\x02\x03\x04\x05"

    @pytest.mark.asyncio
    async def test_cleanup_clears_buffer(self, audio_processor, mock_call_record):
        """Test that cleanup clears the audio buffer."""
        audio_processor.start_recording()

        frame = AudioRawFrame(
            audio=b"\x00\x01\x02\x03", sample_rate=24000, num_channels=1
        )
        await audio_processor.process_frame(frame, FrameDirection.DOWNSTREAM)

        await audio_processor.cleanup()

        assert not audio_processor.has_audio
        assert not audio_processor._is_recording
