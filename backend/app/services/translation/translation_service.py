"""
Translation Service using OpenAI Chat Completion API

Provides translation of transcript messages from source language to English.
"""

import logging
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI

from config import config

logger = logging.getLogger(__name__)

# Language code to full name mapping
LANGUAGE_NAMES = {
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "ht": "Haitian Creole",
}


class TranslationService:
    """Service for translating transcript messages using OpenAI"""

    def __init__(self):
        self.client = AsyncOpenAI(api_key=config.openai.api_key)
        self.model = config.openai.model

    async def translate_batch(
        self,
        messages: List[Dict[str, Any]],
        source_language: str,
        target_language: str = "en",
    ) -> List[Dict[str, Any]]:
        """
        Translate a list of transcript messages efficiently.

        Combines multiple messages into a single API call for efficiency,
        using markers to preserve message boundaries.

        Args:
            messages: List of message dicts with role/content/timestamp
            source_language: Source language code (e.g., 'fr', 'es', 'ht')
            target_language: Target language code (default: 'en')

        Returns:
            List of translated messages with same structure
        """
        if not messages:
            return []

        source_name = LANGUAGE_NAMES.get(source_language, source_language)
        target_name = LANGUAGE_NAMES.get(target_language, target_language)

        # Build combined text with message markers
        message_parts = []
        for i, msg in enumerate(messages):
            content = msg.get("content", "").strip()
            if content:
                message_parts.append(f"[MSG_{i}] {content}")

        if not message_parts:
            # No content to translate, return original structure
            return [
                {
                    "role": msg.get("role"),
                    "content": "",
                    "timestamp": msg.get("timestamp"),
                }
                for msg in messages
            ]

        combined_text = "\n".join(message_parts)

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": f"""You are a professional translator. Translate the following {source_name} conversation to {target_name}.

The text contains multiple messages marked with [MSG_X] markers.
Preserve these markers in your output and translate each message separately.
Return ONLY the translations with their markers, no explanations or additional text.""",
                    },
                    {"role": "user", "content": combined_text},
                ],
                temperature=0.3,  # Low temperature for consistent translations
                max_tokens=4000,
            )

            translated_text = (response.choices[0].message.content or "").strip()

            # Parse translated text back into individual messages
            translated = []
            for i, msg in enumerate(messages):
                marker = f"[MSG_{i}]"
                next_marker = f"[MSG_{i + 1}]"

                # Find content between markers
                start = translated_text.find(marker)
                if start == -1:
                    # Marker not found, preserve original with warning
                    logger.warning(f"Translation marker {marker} not found, using original")
                    translated.append(
                        {
                            "role": msg.get("role"),
                            "content": msg.get("content", ""),
                            "timestamp": msg.get("timestamp"),
                        }
                    )
                    continue

                start += len(marker)
                end = translated_text.find(next_marker, start)
                if end == -1:
                    end = len(translated_text)

                translated_content = translated_text[start:end].strip()

                translated.append(
                    {
                        "role": msg.get("role"),
                        "content": translated_content,
                        "timestamp": msg.get("timestamp"),
                    }
                )

            logger.info(f"Translated {len(translated)} messages from {source_name} to {target_name}")
            return translated

        except Exception as e:
            logger.error(f"Batch translation failed: {e}")
            raise

    async def translate_single(
        self,
        content: str,
        source_language: str,
        target_language: str = "en",
    ) -> str:
        """
        Translate a single text content.

        Args:
            content: Text to translate
            source_language: Source language code
            target_language: Target language code (default: 'en')

        Returns:
            Translated text
        """
        if not content.strip():
            return ""

        source_name = LANGUAGE_NAMES.get(source_language, source_language)
        target_name = LANGUAGE_NAMES.get(target_language, target_language)

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": f"You are a professional translator. Translate the following {source_name} text to {target_name}. Preserve the meaning and tone. Return ONLY the translation, no explanations.",
                    },
                    {"role": "user", "content": content},
                ],
                temperature=0.3,
                max_tokens=1000,
            )

            return (response.choices[0].message.content or "").strip()

        except Exception as e:
            logger.error(f"Single translation failed: {e}")
            raise


# Global service instance
_translation_service: Optional[TranslationService] = None


def get_translation_service() -> TranslationService:
    """Get global translation service instance"""
    global _translation_service
    if _translation_service is None:
        _translation_service = TranslationService()
    return _translation_service
