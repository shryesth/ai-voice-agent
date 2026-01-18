"""
Unit tests for TranscriptProcessor.

Tests the real-time transcript capture from Pipecat pipeline frames.
"""

import pytest
import pytest_asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from pipecat.frames.frames import TranscriptionFrame, TextFrame, Frame
from pipecat.processors.frame_processor import FrameDirection


class TestTranscriptProcessor:
    """Tests for TranscriptProcessor."""

    @pytest_asyncio.fixture
    async def mock_call_record(self):
        """Create a mock CallRecord for testing."""
        mock = MagicMock()
        mock.id = "test-call-id"
        mock.transcript = []
        mock.updated_at = None
        mock.save = AsyncMock()
        return mock

    @pytest_asyncio.fixture
    async def transcript_processor(self, mock_call_record):
        """Create a TranscriptProcessor instance."""
        from backend.app.domains.patient_feedback.transcript_processor import (
            TranscriptProcessor,
        )

        processor = TranscriptProcessor(call_record=mock_call_record)
        processor.push_frame = AsyncMock()
        return processor

    @pytest.mark.asyncio
    async def test_captures_user_transcription(
        self, transcript_processor, mock_call_record
    ):
        """Test that TranscriptionFrame from user is captured."""
        # Create a TranscriptionFrame (user speech)
        frame = TranscriptionFrame(
            text="Hello, this is the patient speaking",
            user_id="user-123",
            timestamp="2026-01-19T10:00:00Z",
        )

        # Process the frame
        await transcript_processor.process_frame(frame, FrameDirection.DOWNSTREAM)

        # Verify transcript was captured
        assert len(mock_call_record.transcript) == 1
        turn = mock_call_record.transcript[0]
        assert turn.speaker == "patient"
        assert turn.text == "Hello, this is the patient speaking"
        assert mock_call_record.save.called

    @pytest.mark.asyncio
    async def test_captures_ai_text_response(
        self, transcript_processor, mock_call_record
    ):
        """Test that TextFrame from AI is captured."""
        # Create a TextFrame (AI response)
        frame = TextFrame(text="Hello! How can I help you today?")

        # Process the frame
        await transcript_processor.process_frame(frame, FrameDirection.DOWNSTREAM)

        # Verify transcript was captured
        assert len(mock_call_record.transcript) == 1
        turn = mock_call_record.transcript[0]
        assert turn.speaker == "ai"
        assert turn.text == "Hello! How can I help you today?"
        assert mock_call_record.save.called

    @pytest.mark.asyncio
    async def test_ignores_empty_text(self, transcript_processor, mock_call_record):
        """Test that empty text frames are ignored."""
        # Create frames with empty text
        frame1 = TextFrame(text="")
        frame2 = TextFrame(text="   ")

        # Process the frames
        await transcript_processor.process_frame(frame1, FrameDirection.DOWNSTREAM)
        await transcript_processor.process_frame(frame2, FrameDirection.DOWNSTREAM)

        # Verify no transcript entries were added
        assert len(mock_call_record.transcript) == 0

    @pytest.mark.asyncio
    async def test_passes_frames_through(self, transcript_processor, mock_call_record):
        """Test that all frames are passed through to next processor."""
        frame = TextFrame(text="Test message")

        await transcript_processor.process_frame(frame, FrameDirection.DOWNSTREAM)

        # Verify frame was pushed to next processor
        transcript_processor.push_frame.assert_called_once_with(
            frame, FrameDirection.DOWNSTREAM
        )

    @pytest.mark.asyncio
    async def test_handles_non_transcript_frames(
        self, transcript_processor, mock_call_record
    ):
        """Test that non-transcript frames are passed through without capture."""
        # Create a generic frame
        frame = Frame()

        await transcript_processor.process_frame(frame, FrameDirection.DOWNSTREAM)

        # Verify no transcript entries were added
        assert len(mock_call_record.transcript) == 0
        # But frame was still passed through
        transcript_processor.push_frame.assert_called_once()

    @pytest.mark.asyncio
    async def test_multiple_turns_captured(
        self, transcript_processor, mock_call_record
    ):
        """Test that multiple conversation turns are captured in order."""
        frames = [
            TextFrame(text="Hello, how are you?"),
            TranscriptionFrame(text="I'm doing well", user_id="user-1", timestamp="t1"),
            TextFrame(text="Glad to hear that"),
        ]

        for frame in frames:
            await transcript_processor.process_frame(frame, FrameDirection.DOWNSTREAM)

        # Verify all turns were captured
        assert len(mock_call_record.transcript) == 3
        assert mock_call_record.transcript[0].speaker == "ai"
        assert mock_call_record.transcript[1].speaker == "patient"
        assert mock_call_record.transcript[2].speaker == "ai"
