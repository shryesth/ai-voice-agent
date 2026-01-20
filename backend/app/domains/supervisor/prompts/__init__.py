"""
Multi-language prompts for the Supervisor AI Calling Platform.

Supported languages:
- en: English
- ht: Haitian Creole (Kreyòl Ayisyen)
- fr: French (Français)
- es: Spanish (Español)

This module provides:
- Confirmation messages for each event type
- System prompts for the AI caller
- Greeting templates
- Language-specific instructions
"""

from backend.app.domains.supervisor.prompts.confirmation_messages import (
    CONFIRMATION_MESSAGES,
    get_confirmation_message,
)
from backend.app.domains.supervisor.prompts.greeting_templates import (
    GREETING_TEMPLATES,
    get_greeting,
)
from backend.app.domains.supervisor.prompts.system_prompts import (
    get_system_prompt,
    get_language_instruction,
    LANGUAGE_VOICE_MAP,
)

__all__ = [
    "CONFIRMATION_MESSAGES",
    "get_confirmation_message",
    "GREETING_TEMPLATES",
    "get_greeting",
    "get_system_prompt",
    "get_language_instruction",
    "LANGUAGE_VOICE_MAP",
]
