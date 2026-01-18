"""
TranscriptProcessor - Captures conversation transcript in real-time.

Intercepts TranscriptionFrame (user speech) and TextFrame (AI responses)
as they flow through the Pipecat pipeline and saves them to CallRecord.
"""

from datetime import datetime
import logging
from typing import TYPE_CHECKING

from pipecat.processors.frame_processor import FrameProcessor, FrameDirection
from pipecat.frames.frames import Frame, TranscriptionFrame, TextFrame

if TYPE_CHECKING:
    from backend.app.models.call_record import CallRecord

logger = logging.getLogger(__name__)


class TranscriptProcessor(FrameProcessor):
    """
    Captures transcript frames and saves to CallRecord in real-time.

    This processor intercepts:
    - TranscriptionFrame: User speech transcription from OpenAI Realtime
    - TextFrame: AI/assistant text responses

    The processor passes all frames through unchanged while capturing
    transcript data for persistence.
    """

    def __init__(self, call_record: "CallRecord", **kwargs):
        """
        Initialize the TranscriptProcessor.

        Args:
            call_record: CallRecord document to save transcript turns to
            **kwargs: Additional arguments passed to FrameProcessor
        """
        super().__init__(**kwargs)
        self.call_record = call_record
        self._pending_save = False

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """
        Process frames to capture transcript entries.

        Intercepts TranscriptionFrame and TextFrame to build the conversation
        transcript, then passes all frames through to the next processor.

        Args:
            frame: The frame to process
            direction: Frame direction (DOWNSTREAM or UPSTREAM)
        """
        # Let base class handle StartFrame and other system frames
        await super().process_frame(frame, direction)

        from backend.app.models.call_record import ConversationTurn

        try:
            if isinstance(frame, TranscriptionFrame):
                # User transcription from OpenAI Realtime
                if frame.text and frame.text.strip():
                    turn = ConversationTurn(
                        speaker="patient",
                        text=frame.text.strip(),
                        timestamp=datetime.utcnow(),
                        language=str(frame.language) if frame.language else None
                    )
                    self.call_record.transcript.append(turn)
                    await self._save_call_record()
                    logger.debug(f"Transcript [patient]: {frame.text[:50]}...")

            elif isinstance(frame, TextFrame) and not isinstance(frame, TranscriptionFrame):
                # AI response text (TextFrame but not TranscriptionFrame subclass)
                if frame.text and frame.text.strip():
                    turn = ConversationTurn(
                        speaker="ai",
                        text=frame.text.strip(),
                        timestamp=datetime.utcnow()
                    )
                    self.call_record.transcript.append(turn)
                    await self._save_call_record()
                    logger.debug(f"Transcript [ai]: {frame.text[:50]}...")

        except Exception as e:
            logger.error(f"Error capturing transcript: {e}", exc_info=True)

        # Always pass frame through to next processor
        await self.push_frame(frame, direction)

    async def _save_call_record(self):
        """
        Save the call record with updated transcript.

        Uses a flag to prevent concurrent saves and handles errors gracefully.
        """
        if self._pending_save:
            return

        try:
            self._pending_save = True
            self.call_record.updated_at = datetime.utcnow()
            await self.call_record.save()
        except Exception as e:
            logger.error(f"Error saving call record transcript: {e}", exc_info=True)
        finally:
            self._pending_save = False
