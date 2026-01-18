"""
AudioCaptureProcessor - Captures audio from the Pipecat pipeline for recording.

Intercepts audio frames as they flow through the pipeline and buffers them
for upload to S3/MinIO when the call ends.
"""

import logging
from typing import TYPE_CHECKING, Callable, Optional

from pipecat.processors.frame_processor import FrameProcessor, FrameDirection
from pipecat.frames.frames import (
    Frame,
    AudioRawFrame,
    EndFrame,
    CancelFrame,
)

from backend.app.core.config import settings

if TYPE_CHECKING:
    from backend.app.models.call_record import CallRecord

logger = logging.getLogger(__name__)


class AudioCaptureProcessor(FrameProcessor):
    """
    Captures audio frames from the Pipecat pipeline for recording.

    This processor intercepts AudioRawFrame to build a recording buffer,
    then triggers an upload callback when the call ends (EndFrame/CancelFrame).
    """

    def __init__(
        self,
        call_record: "CallRecord",
        sample_rate: int = 24000,
        num_channels: int = 1,
        on_recording_complete: Optional[Callable] = None,
        **kwargs
    ):
        """
        Initialize the AudioCaptureProcessor.

        Args:
            call_record: CallRecord document to update with recording metadata
            sample_rate: Expected sample rate in Hz (default: 24000)
            num_channels: Number of audio channels (default: 1 for mono)
            on_recording_complete: Async callback when recording is ready
            **kwargs: Additional arguments passed to FrameProcessor
        """
        super().__init__(**kwargs)
        self.call_record = call_record
        self.sample_rate = sample_rate
        self.num_channels = num_channels
        self.on_recording_complete = on_recording_complete

        self._audio_buffer: bytearray = bytearray()
        self._is_recording = False
        self._recording_started = False

    def start_recording(self):
        """Start capturing audio frames."""
        self._is_recording = True
        self._recording_started = True
        logger.info(f"Started recording for call {self.call_record.id}")

    def stop_recording(self):
        """Stop capturing audio frames."""
        self._is_recording = False
        logger.info(
            f"Stopped recording for call {self.call_record.id}: "
            f"{len(self._audio_buffer)} bytes captured"
        )

    @property
    def audio_data(self) -> bytes:
        """Get the captured audio data."""
        return bytes(self._audio_buffer)

    @property
    def has_audio(self) -> bool:
        """Check if any audio has been captured."""
        return len(self._audio_buffer) > 0

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """
        Process frames to capture audio and detect call end.

        Intercepts AudioRawFrame to buffer audio data, and triggers
        recording upload on EndFrame or CancelFrame.

        Args:
            frame: The frame to process
            direction: Frame direction (DOWNSTREAM or UPSTREAM)
        """
        try:
            # Capture audio frames
            if isinstance(frame, AudioRawFrame) and self._is_recording:
                # Buffer the audio data
                self._audio_buffer.extend(frame.audio)

            # Handle call end - upload recording
            elif isinstance(frame, (EndFrame, CancelFrame)):
                await self._handle_call_end()

        except Exception as e:
            logger.error(f"Error in AudioCaptureProcessor: {e}", exc_info=True)

        # Always pass frame through to next processor
        await self.push_frame(frame, direction)

    async def _handle_call_end(self):
        """
        Handle call end - trigger recording upload.

        Called when EndFrame or CancelFrame is received.
        """
        if not settings.recording_enabled:
            logger.debug("Recording disabled, skipping upload")
            return

        if not self._recording_started:
            logger.debug("Recording was never started, skipping upload")
            return

        self.stop_recording()

        if not self.has_audio:
            logger.warning(f"No audio captured for call {self.call_record.id}")
            return

        # Trigger upload callback
        if self.on_recording_complete:
            try:
                await self.on_recording_complete(
                    call_record=self.call_record,
                    audio_data=self.audio_data,
                    sample_rate=self.sample_rate,
                    num_channels=self.num_channels
                )
            except Exception as e:
                logger.error(
                    f"Recording upload failed for call {self.call_record.id}: {e}",
                    exc_info=True
                )
        else:
            logger.warning(
                f"No recording upload callback configured for call {self.call_record.id}"
            )

    async def cleanup(self):
        """Clean up resources."""
        self._audio_buffer.clear()
        self._is_recording = False
