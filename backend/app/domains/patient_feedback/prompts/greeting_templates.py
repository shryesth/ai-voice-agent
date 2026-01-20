"""
Greeting templates for patient feedback calls.

Each template is keyed by name and contains translations for all supported languages.
Templates use {call_greeting} for the identity verification question and can include
other variables like {facility_name}.

Template Keys:
- "default": Ministry of Health AI survey greeting (recommended for feedback calls)
- "facility": Health facility identification greeting

Supported Languages:
- en: English
- ht: Haitian Creole (Kreyol)
- fr: French
- es: Spanish

Template Variables:
- {call_greeting}: Identity verification question
- {facility_name}: Health facility name
"""
from typing import Dict, Any, List
import logging

logger = logging.getLogger(__name__)


GREETING_TEMPLATES: Dict[str, Dict[str, str]] = {
    # Default: Ministry of Health AI Assistant survey greeting
    "default": {
        "en": (
            "Hello, I am an AI Assistant calling on behalf of Ministry of Health. "
            "We're conducting a short survey to help improve the quality of health services in your area. "
            "{call_greeting}"
        ),
        "ht": (
            "Bonjou, mwen se yon Asistan AI k ap rele sou non Ministè Sante Piblik. "
            "N ap fè yon ti sondaj pou ede amelyore kalite sèvis sante nan zòn ou an. "
            "{call_greeting}"
        ),
        "fr": (
            "Bonjour, je suis un Assistant IA qui appelle de la part du Ministère de la Santé. "
            "Nous menons une courte enquête pour améliorer la qualité des services de santé dans votre région. "
            "{call_greeting}"
        ),
        "es": (
            "Hola, soy un Asistente de IA llamando en nombre del Ministerio de Salud. "
            "Estamos realizando una breve encuesta para mejorar la calidad de los servicios de salud en su área. "
            "{call_greeting}"
        ),
    },
    # Facility greeting: Health facility identification
    "facility": {
        "en": (
            "Hello, I'm calling from {facility_name} healthcare services. "
            "{call_greeting}"
        ),
        "ht": (
            "Bonjou, m ap rele nan non sèvis sante {facility_name}. "
            "{call_greeting}"
        ),
        "fr": (
            "Bonjour, j'appelle de la part des services de santé de {facility_name}. "
            "{call_greeting}"
        ),
        "es": (
            "Hola, estoy llamando de los servicios de salud de {facility_name}. "
            "{call_greeting}"
        ),
    },
}


def get_call_greeting(
    patient_name: str,
    contact_name: str,
    is_child_event: bool = False,
    child_name: str = None,
    guardian_relation: str = None,
) -> str:
    """
    Get appropriate identity verification greeting for the call.

    Args:
        patient_name: Patient's full name
        contact_name: Contact/guardian name being called
        is_child_event: Whether this is a child health event
        child_name: Child's name (for child events)
        guardian_relation: Guardian's relation to patient

    Returns:
        Identity verification question string
    """
    if is_child_event:
        # Child event - ask for guardian/caregiver
        if contact_name and contact_name != patient_name:
            return f"Am I speaking with {contact_name}?"
        elif guardian_relation:
            name = child_name or patient_name
            return f"Am I speaking with {name}'s {guardian_relation.lower()}?"
        else:
            name = child_name or patient_name
            return f"Am I speaking with {name}'s guardian or caregiver?"
    else:
        # Adult event - ask for patient directly
        name = contact_name or patient_name
        return f"Am I speaking with {name}?"


def get_greeting_template(
    template_key: str,
    language: str,
    **format_kwargs: Any,
) -> str:
    """
    Get formatted greeting template for the given key and language.

    Args:
        template_key: Template identifier (e.g., "default", "facility")
        language: Language code (en, ht, fr, es)
        **format_kwargs: Variables to format into template:
            - call_greeting: Identity verification question
            - facility_name: Health facility name

    Returns:
        Formatted greeting instruction string

    Examples:
        >>> get_greeting_template("default", "en", call_greeting="Am I speaking with Marie?")
        "Hello, I am an AI Assistant calling on behalf of Ministry of Health..."
    """
    # Get templates for requested key, fallback to default
    templates = GREETING_TEMPLATES.get(template_key, GREETING_TEMPLATES["default"])

    # Get template for requested language, fallback to English
    template = templates.get(language, templates.get("en", ""))

    if not template:
        logger.warning(
            f"No greeting template found for key '{template_key}' in language '{language}'"
        )
        return ""

    # Format with provided values
    try:
        return template.format(**format_kwargs)
    except KeyError as e:
        logger.warning(
            f"Missing format key {e} for greeting template '{template_key}' in '{language}'. "
            f"Available keys: {list(format_kwargs.keys())}"
        )
        return template


def get_available_greeting_templates() -> List[str]:
    """Get list of available greeting template keys."""
    return list(GREETING_TEMPLATES.keys())


def get_available_languages() -> List[str]:
    """Get list of available languages for greeting templates."""
    return list(GREETING_TEMPLATES["default"].keys())
