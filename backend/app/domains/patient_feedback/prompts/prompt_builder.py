"""
Prompt builder for patient feedback calls.

Combines greeting templates, confirmation messages, and the comprehensive
prompt template to create the full system prompt for the AI agent.
"""

import os
from pathlib import Path
from typing import Optional
import logging

from backend.app.domains.patient_feedback.prompts.greeting_templates import (
    get_greeting_template,
    get_call_greeting,
)
from backend.app.domains.patient_feedback.prompts.confirmation_messages import (
    get_confirmation_message,
)

logger = logging.getLogger(__name__)

# Path to prompt templates
PROMPTS_DIR = Path(__file__).parent


# Language-specific instructions
LANGUAGE_INSTRUCTIONS = {
    "en": "Conduct this conversation in English.",
    "ht": (
        "Conduct this conversation in Haitian Creole (Kreyòl). "
        "Use natural Kreyòl expressions and greetings."
    ),
    "fr": (
        "Conduct this conversation in French. "
        "Use formal French (vouvoiement) unless the caller uses informal speech."
    ),
    "es": (
        "Conduct this conversation in Spanish. "
        "Use formal Spanish (usted) unless the caller uses informal speech."
    ),
}


def load_prompt_template(language: str = "en") -> str:
    """
    Load the comprehensive prompt template for the given language.

    Falls back to English if the requested language template doesn't exist.

    Args:
        language: Language code (en, ht, fr, es)

    Returns:
        Template string with placeholders
    """
    # Try language-specific template first
    template_path = PROMPTS_DIR / language / "comprehensive.txt"
    if not template_path.exists():
        # Fallback to English
        template_path = PROMPTS_DIR / "en" / "comprehensive.txt"

    try:
        return template_path.read_text(encoding="utf-8")
    except Exception as e:
        logger.error(f"Failed to load prompt template: {e}")
        return ""


def build_system_prompt(
    # Patient/contact info
    patient_name: str,
    contact_name: str,
    phone_number: str,
    # Visit info
    facility_name: str,
    visit_date: str,
    # Event info
    event_info: dict,
    # Configuration
    language: str = "en",
    greeting_template: str = "default",
    # Optional child event info
    is_child_event: bool = False,
    child_name: Optional[str] = None,
    guardian_relation: Optional[str] = None,
) -> str:
    """
    Build the complete system prompt for the AI agent.

    Combines:
    - Comprehensive prompt template
    - Greeting template with identity verification
    - Event-specific confirmation message
    - Language instruction

    Args:
        patient_name: Patient's full name
        contact_name: Contact/guardian name being called
        phone_number: Phone number being called
        facility_name: Health facility name
        visit_date: Visit date in human-readable format
        event_info: Dict containing event details (from EventInfo schema)
        language: Language code (en, ht, fr, es)
        greeting_template: Greeting template key
        is_child_event: Whether this is a child health event
        child_name: Child's name (for child events)
        guardian_relation: Guardian's relation to patient

    Returns:
        Complete formatted system prompt
    """
    # Load base template
    template = load_prompt_template(language)
    if not template:
        logger.error("No prompt template available")
        return ""

    # Build call greeting (identity verification question)
    call_greeting = get_call_greeting(
        patient_name=patient_name,
        contact_name=contact_name,
        is_child_event=is_child_event or event_info.get("is_child_event", False),
        child_name=child_name or event_info.get("child_name"),
        guardian_relation=guardian_relation,
    )

    # Build full greeting instruction
    greeting_instruction = get_greeting_template(
        template_key=greeting_template,
        language=language,
        call_greeting=call_greeting,
        facility_name=facility_name,
    )

    # Build confirmation message
    confirmation_message_key = event_info.get("confirmation_message_key", "patient_feedback_default")
    service_name = (
        event_info.get("vaccine_name") or
        event_info.get("service_name") or
        event_info.get("event_type", "health service")
    )

    confirmation_message = get_confirmation_message(
        message_key=confirmation_message_key,
        language=language,
        child_name=child_name or event_info.get("child_name") or patient_name,
        patient_name=patient_name,
        vaccine_name=event_info.get("vaccine_name", service_name),
        service_name=service_name,
        visit_date=visit_date,
        facility_name=facility_name,
    )

    # Build guardian info string
    if is_child_event or event_info.get("is_child_event"):
        if contact_name and contact_name != patient_name:
            guardian_info = f"{contact_name} (guardian of {child_name or patient_name})"
        elif guardian_relation:
            guardian_info = f"{child_name or patient_name}'s {guardian_relation}"
        else:
            guardian_info = f"Guardian of {child_name or patient_name}"
    else:
        guardian_info = contact_name or patient_name

    # Determine if speaking directly to patient or to a guardian
    # Use "you/your" when speaking to patient directly, use patient name when speaking to guardian
    # For child events, we're always speaking to a guardian about the child
    is_child = is_child_event or event_info.get("is_child_event", False)
    effective_patient_name = child_name or event_info.get("child_name") or patient_name

    is_speaking_to_patient = (
        not is_child and  # Child events always involve a guardian
        (
            contact_name == patient_name or
            (not contact_name) or
            event_info.get("contact_type") == "patient"
        )
    )

    if is_speaking_to_patient:
        subject_name = "you"
        possessive = "your"
    else:
        # Speaking to a guardian about the patient (or child)
        subject_name = effective_patient_name
        possessive = f"{effective_patient_name}'s"

    # Get event type for side effects logic
    event_type = event_info.get("event_type", "general")

    # Get language instruction
    language_instruction = LANGUAGE_INSTRUCTIONS.get(language, LANGUAGE_INSTRUCTIONS["en"])

    # Format the template
    try:
        prompt = template.format(
            patient_name=patient_name,
            guardian_info=guardian_info,
            phone_number=phone_number,
            facility_name=facility_name,
            visit_date=visit_date,
            service_name=service_name,
            event_type=event_type,
            subject_name=subject_name,
            possessive=possessive,
            greeting_instruction=greeting_instruction,
            confirmation_message=confirmation_message,
            language_instruction=language_instruction,
        )
        return prompt
    except KeyError as e:
        logger.error(f"Missing template variable: {e}")
        return template


def build_prompt_from_call_record(call_record) -> str:
    """
    Build system prompt from a CallRecord object.

    This is a convenience function that extracts the needed fields
    from a CallRecord and builds the prompt.

    Args:
        call_record: CallRecord document from database

    Returns:
        Complete formatted system prompt
    """
    # Extract event_info from call_record
    event_info = {}
    if hasattr(call_record, 'event_info') and call_record.event_info:
        event_info = call_record.event_info if isinstance(call_record.event_info, dict) else call_record.event_info.model_dump()

    return build_system_prompt(
        patient_name=call_record.patient_name or call_record.contact_name or "Patient",
        contact_name=call_record.contact_name or call_record.patient_name or "Patient",
        phone_number=call_record.contact_phone,
        facility_name=event_info.get("facility_name", "the health facility"),
        visit_date=event_info.get("event_date", "your recent visit"),
        event_info=event_info,
        language=call_record.language or "en",
        greeting_template=getattr(call_record, 'greeting_template', 'default') or 'default',
        is_child_event=event_info.get("is_child_event", False),
        child_name=event_info.get("child_name"),
        guardian_relation=getattr(call_record, 'guardian_relation', None),
    )
