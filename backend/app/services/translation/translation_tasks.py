"""
Celery Tasks for Transcript Translation

Async tasks for translating non-English call transcripts to English.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict

from backend.app.services.queue.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="translate_transcript",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,  # Max 10 minutes between retries
    max_retries=3,
    rate_limit="10/m",  # Limit to 10 translations per minute
)
def translate_transcript(self, call_sid: str) -> Dict[str, Any]:
    """
    Translate a transcript from its original language to English.

    Args:
        call_sid: The call SID of the transcript to translate

    Returns:
        Dict with translation status and statistics
    """
    logger.info(f"Starting translation for call: {call_sid}")

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            result = loop.run_until_complete(
                _translate_transcript_async(call_sid, self.request.retries)
            )
        finally:
            loop.close()

        return result

    except Exception as e:
        logger.error(f"Translation task failed for {call_sid}: {e}")

        # Update status to failed if max retries exceeded
        if self.request.retries >= self.max_retries:
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(
                        _mark_translation_failed(call_sid, str(e), self.request.retries + 1)
                    )
                finally:
                    loop.close()
            except Exception as update_error:
                logger.error(f"Failed to update translation status: {update_error}")

        raise  # Re-raise to trigger retry


async def _translate_transcript_async(call_sid: str, attempt: int) -> Dict[str, Any]:
    """Async implementation of transcript translation"""
    from backend.app.infrastructure.storage.transcript_repository import (
        get_transcript_repository,
    )
    from backend.app.services.translation.translation_service import (
        get_translation_service,
    )

    repo = get_transcript_repository()
    service = get_translation_service()

    # Fetch transcript
    transcript = await repo.get_transcript(call_sid)
    if not transcript:
        logger.error(f"Transcript not found for call: {call_sid}")
        return {"error": "Transcript not found", "call_sid": call_sid}

    # Check if already translated
    translation = transcript.get("translation", {})
    if translation.get("status") == "completed":
        logger.info(f"Transcript already translated for call: {call_sid}")
        return {"status": "already_completed", "call_sid": call_sid}

    # Get source language
    metadata = transcript.get("metadata", {})
    source_language = metadata.get("language", "en")

    if source_language == "en":
        logger.info(f"Transcript is already in English: {call_sid}")
        return {"status": "not_needed", "call_sid": call_sid, "reason": "already_english"}

    # Update status to in_progress
    await repo.update_translation_status(
        call_sid=call_sid,
        status="in_progress",
        attempt_count=attempt + 1,
    )

    # Get original messages
    transcript_data = transcript.get("transcript", {})
    messages = transcript_data.get("messages", [])

    if not messages:
        logger.warning(f"No messages to translate for call: {call_sid}")
        await repo.update_translation_status(
            call_sid=call_sid,
            status="completed",
            translated_messages=[],
            translated_at=datetime.utcnow(),
        )
        return {"status": "completed", "call_sid": call_sid, "messages_count": 0}

    # Translate messages
    logger.info(f"Translating {len(messages)} messages from {source_language} to en")

    translated_messages = await service.translate_batch(
        messages=messages,
        source_language=source_language,
        target_language="en",
    )

    # Save translated messages
    await repo.update_translation_status(
        call_sid=call_sid,
        status="completed",
        translated_messages=translated_messages,
        translated_at=datetime.utcnow(),
    )

    logger.info(f"Translation completed for call: {call_sid}")

    return {
        "status": "completed",
        "call_sid": call_sid,
        "messages_count": len(translated_messages),
        "source_language": source_language,
        "target_language": "en",
    }


async def _mark_translation_failed(call_sid: str, error: str, attempts: int):
    """Mark translation as failed in database"""
    from backend.app.infrastructure.storage.transcript_repository import (
        get_transcript_repository,
    )

    repo = get_transcript_repository()
    await repo.update_translation_status(
        call_sid=call_sid,
        status="failed",
        error_message=error,
        attempt_count=attempts,
    )
