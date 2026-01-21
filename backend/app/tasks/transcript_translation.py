"""
Celery task for translating call transcripts to English.

Triggered after non-English calls complete.
Uses OpenAI gpt-4o-mini for translation with retry logic.
"""

import logging

from beanie import PydanticObjectId

from backend.app.celery_app import celery_app, get_worker_event_loop
from backend.app.core.config import settings
from backend.app.models.call_record import CallRecord, EnglishTranslation
from backend.app.services.translation_service import get_translation_service

logger = logging.getLogger(__name__)

# Translation task configuration
TRANSLATION_MAX_RETRIES = 3
TRANSLATION_RETRY_DELAY = 60  # seconds


@celery_app.task(
    name="translate_transcript",
    bind=True,
    max_retries=TRANSLATION_MAX_RETRIES,
    default_retry_delay=TRANSLATION_RETRY_DELAY,
    rate_limit="10/m",  # Rate limit: 10 per minute
    time_limit=120,     # 2 minute timeout
    soft_time_limit=90,
)
def translate_transcript(self, call_record_id: str):
    """
    Translate transcript from source language to English.

    Args:
        call_record_id: CallRecord ID to translate

    Returns:
        Dict with translation status
    """
    logger.info(f"Starting transcript translation for call: {call_record_id}")

    try:
        loop = get_worker_event_loop()

        # Get call record
        call_record = loop.run_until_complete(
            CallRecord.get(PydanticObjectId(call_record_id))
        )

        if not call_record:
            logger.error(f"CallRecord not found: {call_record_id}")
            return {"status": "error", "message": "Call record not found"}

        # Skip if already translated
        if (
            call_record.english_translation
            and call_record.english_translation.status == "completed"
        ):
            logger.info(f"Transcript already translated: {call_record_id}")
            return {"status": "skipped", "message": "Already translated"}

        # Skip if English
        if call_record.language == "en":
            logger.info(f"Skipping English call: {call_record_id}")
            return {"status": "skipped", "message": "English call"}

        # Check if translation is enabled
        if not getattr(settings, "translation_enabled", True):
            logger.info(f"Translation disabled, skipping: {call_record_id}")
            return {"status": "skipped", "message": "Translation disabled"}

        # Update status to in_progress
        if not call_record.english_translation:
            call_record.english_translation = EnglishTranslation(
                status="in_progress",
                source_language=call_record.language,
                attempts=1,
            )
        else:
            call_record.english_translation.status = "in_progress"
            call_record.english_translation.attempts += 1
        loop.run_until_complete(call_record.save())

        # Perform translation
        translation_service = get_translation_service()
        success = loop.run_until_complete(
            translation_service.translate_transcript(call_record)
        )

        if success:
            logger.info(f"Translation completed for call: {call_record_id}")

            # Reload to get updated record
            call_record = loop.run_until_complete(
                CallRecord.get(PydanticObjectId(call_record_id))
            )

            message_count = 0
            if call_record.english_translation:
                message_count = len(call_record.english_translation.messages)

            return {
                "status": "success",
                "call_record_id": call_record_id,
                "message_count": message_count,
            }
        else:
            raise Exception("Translation failed")

    except Exception as e:
        logger.error(
            f"Translation error for call {call_record_id}: {e}",
            exc_info=True
        )

        # Update error status
        try:
            loop = get_worker_event_loop()
            call_record = loop.run_until_complete(
                CallRecord.get(PydanticObjectId(call_record_id))
            )
            if call_record and call_record.english_translation:
                call_record.english_translation.status = "failed"
                call_record.english_translation.error = str(e)
                loop.run_until_complete(call_record.save())
        except Exception as update_error:
            logger.error(f"Failed to update error status: {update_error}")

        # Retry with exponential backoff if retries remain
        if self.request.retries < TRANSLATION_MAX_RETRIES:
            raise self.retry(exc=e)

        return {"status": "failed", "error": str(e)}
