"""
Prompt templates for patient feedback calls.
"""

from backend.app.domains.patient_feedback.prompts.greeting_templates import (
    get_greeting_template,
    get_call_greeting,
    get_available_greeting_templates,
)
from backend.app.domains.patient_feedback.prompts.confirmation_messages import (
    get_confirmation_message,
    get_available_message_keys,
)

__all__ = [
    "get_greeting_template",
    "get_call_greeting",
    "get_available_greeting_templates",
    "get_confirmation_message",
    "get_available_message_keys",
]
