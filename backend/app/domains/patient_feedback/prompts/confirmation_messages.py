"""
Event-specific confirmation messages for patient feedback calls.

Each message key corresponds to an event type and contains the confirmation
question to ask the patient/guardian in different languages.

Supported languages:
- en: English
- ht: Haitian Creole (Kreyol)
- fr: French
- es: Spanish

Template variables:
- {child_name}: Child's name for child health events
- {patient_name}: Patient's name
- {vaccine_name}: Vaccine name for vaccination events
- {service_name}: Service name for non-vaccination events
- {visit_date}: Date of the visit (human-readable format)
- {facility_name}: Name of the health facility
"""
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)


# English (en) confirmation messages
CONFIRMATION_MESSAGES_EN: Dict[str, str] = {
    # ===== Child Vaccination =====
    "child_vaccination_generic": (
        "{child_name} came for immunization and received the {vaccine_name}, "
        "is that right?"
    ),
    "child_vaccination_bcg": (
        "{child_name} came for immunization and received the BCG vaccine, "
        "is that right?"
    ),
    "child_vaccination_polio": (
        "{child_name} came for immunization and received the Polio vaccine, "
        "is that right?"
    ),
    "child_vaccination_penta1": (
        "{child_name} came for immunization and received the 1st dose of Pentavalent vaccine, "
        "is that right?"
    ),
    "child_vaccination_penta2": (
        "{child_name} came for immunization and received the 2nd dose of Pentavalent vaccine, "
        "is that right?"
    ),
    "child_vaccination_penta3": (
        "{child_name} came for immunization and received the 3rd dose of Pentavalent vaccine, "
        "is that right?"
    ),
    "child_vaccination_rr1": (
        "{child_name} came for immunization and received the measles-rubella vaccine, "
        "is that right?"
    ),
    # ===== Child Services =====
    "child_deworming": (
        "During this visit, did {child_name} receive deworming medicine?"
    ),
    "child_vitamin_a": (
        "During this visit, did {child_name} receive Vitamin A supplement?"
    ),
    "child_malnutrition_screening": (
        "During this visit, did the health worker check {child_name} for malnutrition, "
        "for example, by measuring the arm with a colored tape or checking the child's "
        "weight and height?"
    ),
    # ===== Prenatal Care =====
    "prenatal_anc": (
        "You came for antenatal care (ANC), is that right?"
    ),
    "prenatal_td_vaccine": (
        "During this visit, did you receive the Tetanus and Diphtheria (Td) vaccine?"
    ),
    "prenatal_first_trimester": (
        "You came for your first antenatal care (ANC) visit and you were given vitamin "
        "and supplements such as iron and folic acid tablets, is that right?"
    ),
    # ===== Maternity =====
    "maternity_delivery": (
        "During this visit, did you give birth at this health facility?"
    ),
    # ===== Family Planning =====
    "family_planning": (
        "You came for family planning services, is that right?"
    ),
    # ===== General/Default =====
    "patient_feedback_default": (
        "{patient_name} visited {facility_name} on {visit_date}, is that right?"
    ),
    "vaccination_default": (
        "{patient_name} came for {vaccine_name}, is that right?"
    ),
    "service_default": (
        "{patient_name} came for {service_name}, is that right?"
    ),
}


# Haitian Creole (ht) confirmation messages
CONFIRMATION_MESSAGES_HT: Dict[str, str] = {
    # ===== Child Vaccination =====
    "child_vaccination_generic": (
        "{child_name} te vini pou vaksinasyon epi li te resevwa {vaccine_name}, "
        "èske sa kòrèk?"
    ),
    "child_vaccination_bcg": (
        "{child_name} te vini pou vaksinasyon epi li te resevwa vaksen BCG a, "
        "èske sa kòrèk?"
    ),
    "child_vaccination_polio": (
        "{child_name} te vini pou vaksinasyon epi li te resevwa vaksen Polyo a, "
        "èske sa kòrèk?"
    ),
    "child_vaccination_penta1": (
        "{child_name} te vini pou vaksinasyon epi li te resevwa premye dòz vaksen Penta a, "
        "èske sa kòrèk?"
    ),
    "child_vaccination_penta3": (
        "{child_name} te vini pou vaksinasyon epi li te resevwa twazyèm dòz vaksen Penta a, "
        "èske sa kòrèk?"
    ),
    "child_vaccination_rr1": (
        "{child_name} te vini pou vaksinasyon epi li te resevwa vaksen woujòl-ribyèl la, "
        "èske sa kòrèk?"
    ),
    # ===== Child Services =====
    "child_deworming": (
        "Pandan vizit sa a, èske {child_name} te resevwa medikaman kont vè?"
    ),
    "child_vitamin_a": (
        "Pandan vizit sa a, èske {child_name} te resevwa sipleman Vitamin A?"
    ),
    # ===== Default =====
    "patient_feedback_default": (
        "{patient_name} te vizite {facility_name} nan dat {visit_date}, èske sa kòrèk?"
    ),
    "vaccination_default": (
        "{patient_name} te vini pou {vaccine_name}, èske sa kòrèk?"
    ),
}


# French (fr) confirmation messages
CONFIRMATION_MESSAGES_FR: Dict[str, str] = {
    # ===== Child Vaccination =====
    "child_vaccination_generic": (
        "{child_name} est venu pour la vaccination et a reçu le {vaccine_name}, "
        "c'est correct?"
    ),
    "child_vaccination_penta1": (
        "{child_name} est venu pour la vaccination et a reçu la 1ère dose du vaccin Penta, "
        "c'est correct?"
    ),
    "child_vaccination_rr1": (
        "{child_name} est venu pour la vaccination et a reçu le vaccin rougeole-rubéole, "
        "c'est correct?"
    ),
    # ===== Default =====
    "patient_feedback_default": (
        "{patient_name} a visité {facility_name} le {visit_date}, c'est correct?"
    ),
    "vaccination_default": (
        "{patient_name} est venu pour {vaccine_name}, c'est correct?"
    ),
}


# Spanish (es) confirmation messages
CONFIRMATION_MESSAGES_ES: Dict[str, str] = {
    # ===== Child Vaccination =====
    "child_vaccination_generic": (
        "{child_name} vino para vacunación y recibió la {vaccine_name}, "
        "¿es correcto?"
    ),
    "child_vaccination_penta1": (
        "{child_name} vino para vacunación y recibió la 1ra dosis de la vacuna Penta, "
        "¿es correcto?"
    ),
    # ===== Default =====
    "patient_feedback_default": (
        "{patient_name} visitó {facility_name} el {visit_date}, ¿es correcto?"
    ),
    "vaccination_default": (
        "{patient_name} vino para {vaccine_name}, ¿es correcto?"
    ),
}


# All messages by language
CONFIRMATION_MESSAGES: Dict[str, Dict[str, str]] = {
    "en": CONFIRMATION_MESSAGES_EN,
    "ht": CONFIRMATION_MESSAGES_HT,
    "fr": CONFIRMATION_MESSAGES_FR,
    "es": CONFIRMATION_MESSAGES_ES,
}


def get_confirmation_message(
    message_key: str,
    language: str,
    **format_kwargs: Any,
) -> str:
    """
    Get confirmation message for event type.

    Args:
        message_key: Key from event_info.confirmation_message_key
        language: Language code (en, ht, fr, es)
        **format_kwargs: Values to format into message:
            - child_name: Child's name for child events
            - patient_name: Patient's name
            - vaccine_name: Vaccine name for vaccination events
            - service_name: Service name for non-vaccination events
            - visit_date: Visit date (human-readable)
            - facility_name: Health facility name

    Returns:
        Formatted confirmation message

    Examples:
        >>> get_confirmation_message("child_vaccination_penta1", "en", child_name="Jean")
        "Jean came for immunization and received the 1st dose of Pentavalent vaccine, is that right?"
    """
    # Get messages for the requested language, fallback to English
    lang_messages = CONFIRMATION_MESSAGES.get(language, CONFIRMATION_MESSAGES_EN)

    # Get the template, fallback to default
    template = lang_messages.get(
        message_key,
        lang_messages.get("patient_feedback_default", CONFIRMATION_MESSAGES_EN.get("patient_feedback_default", ""))
    )

    if not template:
        logger.warning(
            f"No confirmation message found for key '{message_key}' in language '{language}'"
        )
        return ""

    # Format the template with provided values
    try:
        return template.format(**format_kwargs)
    except KeyError as e:
        logger.warning(
            f"Missing format key {e} for message '{message_key}' in language '{language}'. "
            f"Available keys: {list(format_kwargs.keys())}"
        )
        # Return template with placeholders if formatting fails
        return template


def get_available_languages() -> list:
    """Get list of available languages for confirmation messages."""
    return list(CONFIRMATION_MESSAGES.keys())


def get_available_message_keys() -> list:
    """Get list of available message keys."""
    return list(CONFIRMATION_MESSAGES_EN.keys())
