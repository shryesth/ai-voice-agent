"""
Translation Service for translating call transcripts to English.

Uses OpenAI gpt-4o-mini for efficient batch translation of non-English transcripts.
Implements marker-based batching for single API call efficiency.
"""

import logging
import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING, List, Optional

from openai import AsyncOpenAI

from backend.app.core.config import settings
from backend.app.models.call_record import (
    ConversationTurn,
    EnglishTranslation,
    TranslatedMessage,
)

if TYPE_CHECKING:
    from backend.app.models.call_record import CallRecord

logger = logging.getLogger(__name__)

# Language code to name mapping
LANGUAGE_NAMES = {
    "en": "English",
    "ht": "Haitian Creole",
    "fr": "French",
    "es": "Spanish",
}


class TranslationService:
    """
    Service for translating call transcripts using OpenAI.

    Uses batch processing with message markers for efficient translation.
    """

    def __init__(self):
        """Initialize with OpenAI client."""
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = settings.translation_model

    async def translate_transcript(self, call_record: "CallRecord") -> bool:
        """
        Translate transcript from source language to English.

        Uses batch processing: combines all messages with markers
        [MSG_0], [MSG_1], etc. for a single API call.

        Args:
            call_record: CallRecord with transcript to translate

        Returns:
            True if translation successful, False otherwise
        """
        call_id = str(call_record.id)
        source_language = call_record.language

        # Skip if English
        if source_language == "en":
            logger.info(f"Skipping translation for English call: {call_id}")
            return True

        # Get messages to translate
        messages_to_translate = [
            turn for turn in call_record.transcript
            if turn.text and turn.text.strip()
        ]

        if not messages_to_translate:
            logger.info(f"No messages to translate for call: {call_id}")
            # Mark as completed with empty messages
            call_record.english_translation = EnglishTranslation(
                status="completed",
                source_language=source_language,
                messages=[],
                completed_at=datetime.now(timezone.utc),
                attempts=1,
            )
            await call_record.save()
            return True

        try:
            # Build batched prompt with markers
            batched_text = self._build_batch_prompt(messages_to_translate)

            # Call OpenAI API
            translated_batch = await self._call_openai(
                batched_text,
                source_language=source_language,
            )

            # Parse response and extract individual translations
            translated_messages = self._parse_batch_response(
                translated_batch,
                messages_to_translate,
            )

            # Update call record with translation
            attempts = 1
            if call_record.english_translation:
                attempts = call_record.english_translation.attempts + 1

            call_record.english_translation = EnglishTranslation(
                status="completed",
                source_language=source_language,
                messages=translated_messages,
                completed_at=datetime.now(timezone.utc),
                attempts=attempts,
                error=None,
            )
            call_record.updated_at = datetime.now(timezone.utc)
            await call_record.save()

            logger.info(
                f"Translation completed for call {call_id}: "
                f"{len(translated_messages)} messages translated"
            )
            return True

        except Exception as e:
            logger.error(
                f"Translation failed for call {call_id}: {e}",
                exc_info=True
            )

            # Update error status
            attempts = 1
            if call_record.english_translation:
                attempts = call_record.english_translation.attempts + 1

            call_record.english_translation = EnglishTranslation(
                status="failed",
                source_language=source_language,
                messages=[],
                completed_at=None,
                attempts=attempts,
                error=str(e),
            )
            call_record.updated_at = datetime.now(timezone.utc)
            await call_record.save()

            return False

    def _build_batch_prompt(self, messages: List[ConversationTurn]) -> str:
        """
        Build batched prompt with markers for efficient translation.

        Each message is prefixed with [MSG_N] marker to preserve boundaries.

        Args:
            messages: List of conversation turns to translate

        Returns:
            Batched text with markers
        """
        lines = []
        for i, msg in enumerate(messages):
            # Include speaker for context
            speaker_label = "AI" if msg.speaker == "ai" else "Patient"
            lines.append(f"[MSG_{i}] ({speaker_label}): {msg.text}")
        return "\n".join(lines)

    async def _call_openai(
        self,
        text: str,
        source_language: str,
    ) -> str:
        """
        Call OpenAI API for translation.

        Args:
            text: Batched text with markers
            source_language: Source language code

        Returns:
            Translated text with preserved markers
        """
        source_name = LANGUAGE_NAMES.get(source_language, source_language)

        system_prompt = f"""You are a medical transcript translator. Translate the following conversation from {source_name} to English.

IMPORTANT RULES:
1. Preserve the message markers [MSG_N] exactly as they appear
2. Keep the speaker labels (AI): and (Patient): in the output
3. Maintain medical terminology accuracy
4. Keep the translation natural and conversational
5. Preserve the meaning and tone of the original

Translate each message while keeping the exact format:
[MSG_N] (Speaker): translated text"""

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            temperature=0.3,
            max_tokens=4096,
        )

        return response.choices[0].message.content

    def _parse_batch_response(
        self,
        translated_batch: str,
        original_messages: List[ConversationTurn],
    ) -> List[TranslatedMessage]:
        """
        Parse batch response and extract individual translations.

        Matches markers to reconstruct individual translated messages.

        Args:
            translated_batch: Translated text with markers
            original_messages: Original conversation turns

        Returns:
            List of TranslatedMessage objects
        """
        translated_messages = []

        # Parse translations by marker
        # Pattern: [MSG_N] (Speaker): text
        pattern = r"\[MSG_(\d+)\]\s*\([^)]+\):\s*(.+?)(?=\[MSG_|\Z)"
        matches = re.findall(pattern, translated_batch, re.DOTALL)

        # Build lookup from matches
        translations_by_index = {}
        for match in matches:
            idx = int(match[0])
            text = match[1].strip()
            translations_by_index[idx] = text

        # Create TranslatedMessage objects
        for i, original in enumerate(original_messages):
            english_text = translations_by_index.get(i, original.text)

            translated_messages.append(
                TranslatedMessage(
                    speaker=original.speaker,
                    original_text=original.text,
                    english_text=english_text,
                    timestamp=original.timestamp,
                )
            )

            # Warn if translation not found
            if i not in translations_by_index:
                logger.warning(
                    f"Translation marker [MSG_{i}] not found in response, "
                    f"using original text"
                )

        return translated_messages


# Singleton instance
_translation_service: Optional[TranslationService] = None


def get_translation_service() -> TranslationService:
    """Get or create TranslationService singleton."""
    global _translation_service
    if _translation_service is None:
        _translation_service = TranslationService()
    return _translation_service
