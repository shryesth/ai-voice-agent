"""
Translation Service Module

Provides automatic translation of call transcripts using OpenAI.
"""

from backend.app.services.translation.translation_service import (
    TranslationService,
    get_translation_service,
)

__all__ = ["TranslationService", "get_translation_service"]
