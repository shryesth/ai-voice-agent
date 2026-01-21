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
    # Alias for generic vaccination - used when no specific key provided
    "child_vaccination": (
        "{child_name} came for immunization and received the {vaccine_name}, "
        "is that right?"
    ),
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
    "child_vaccination": (
        "{child_name} te vini pou vaksinasyon epi li te resevwa {vaccine_name}, "
        "èske sa kòrèk?"
    ),
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
    "child_vaccination_penta2": (
        "{child_name} te vini pou vaksinasyon epi li te resevwa dezyèm dòz vaksen Penta a, "
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
    "child_malnutrition_screening": (
        "Pandan vizit sa a, èske travayè sante a te tcheke {child_name} pou malnitrisyon, "
        "pa egzanp, li mezire bra a ak yon tep koulè oswa li tcheke pwa ak wotè timoun nan?"
    ),
    # ===== Prenatal Care =====
    "prenatal_anc": (
        "Ou te vini pou swen anvan akouchman (ANC), èske sa kòrèk?"
    ),
    "prenatal_td_vaccine": (
        "Pandan vizit sa a, èske ou te resevwa vaksen Tetanòs ak Difteria (Td) a?"
    ),
    "prenatal_first_trimester": (
        "Ou te vini pou premye vizit swen anvan akouchman (ANC) ou epi yo te ba ou vitamin "
        "ak sipleman tankou grenn fè ak asid folik, èske sa kòrèk?"
    ),
    # ===== Maternity =====
    "maternity_delivery": (
        "Pandan vizit sa a, èske ou te akouche nan etablisman sante sa a?"
    ),
    # ===== Family Planning =====
    "family_planning": (
        "Ou te vini pou sèvis planifikasyon familyal, èske sa kòrèk?"
    ),
    # ===== Default =====
    "patient_feedback_default": (
        "{patient_name} te vizite {facility_name} nan dat {visit_date}, èske sa kòrèk?"
    ),
    "vaccination_default": (
        "{patient_name} te vini pou {vaccine_name}, èske sa kòrèk?"
    ),
    "service_default": (
        "{patient_name} te vini pou {service_name}, èske sa kòrèk?"
    ),
}


# French (fr) confirmation messages
CONFIRMATION_MESSAGES_FR: Dict[str, str] = {
    # ===== Child Vaccination =====
    "child_vaccination": (
        "{child_name} est venu pour la vaccination et a reçu le {vaccine_name}, "
        "c'est correct?"
    ),
    "child_vaccination_generic": (
        "{child_name} est venu pour la vaccination et a reçu le {vaccine_name}, "
        "c'est correct?"
    ),
    "child_vaccination_bcg": (
        "{child_name} est venu pour la vaccination et a reçu le vaccin BCG, "
        "c'est correct?"
    ),
    "child_vaccination_polio": (
        "{child_name} est venu pour la vaccination et a reçu le vaccin Polio, "
        "c'est correct?"
    ),
    "child_vaccination_penta1": (
        "{child_name} est venu pour la vaccination et a reçu la 1ère dose du vaccin Penta, "
        "c'est correct?"
    ),
    "child_vaccination_penta2": (
        "{child_name} est venu pour la vaccination et a reçu la 2ème dose du vaccin Penta, "
        "c'est correct?"
    ),
    "child_vaccination_penta3": (
        "{child_name} est venu pour la vaccination et a reçu la 3ème dose du vaccin Penta, "
        "c'est correct?"
    ),
    "child_vaccination_rr1": (
        "{child_name} est venu pour la vaccination et a reçu le vaccin rougeole-rubéole, "
        "c'est correct?"
    ),
    # ===== Child Services =====
    "child_deworming": (
        "Lors de cette visite, est-ce que {child_name} a reçu un médicament vermifuge?"
    ),
    "child_vitamin_a": (
        "Lors de cette visite, est-ce que {child_name} a reçu un supplément de Vitamine A?"
    ),
    "child_malnutrition_screening": (
        "Lors de cette visite, est-ce que l'agent de santé a vérifié si {child_name} souffre de malnutrition, "
        "par exemple, en mesurant le bras avec un ruban coloré ou en vérifiant le poids et la taille de l'enfant?"
    ),
    # ===== Prenatal Care =====
    "prenatal_anc": (
        "Vous êtes venue pour des soins prénataux (CPN), c'est correct?"
    ),
    "prenatal_td_vaccine": (
        "Lors de cette visite, avez-vous reçu le vaccin Tétanos et Diphtérie (Td)?"
    ),
    "prenatal_first_trimester": (
        "Vous êtes venue pour votre première visite de soins prénataux (CPN) et on vous a donné des vitamines "
        "et des suppléments comme des comprimés de fer et d'acide folique, c'est correct?"
    ),
    # ===== Maternity =====
    "maternity_delivery": (
        "Lors de cette visite, avez-vous accouché dans cet établissement de santé?"
    ),
    # ===== Family Planning =====
    "family_planning": (
        "Vous êtes venue pour des services de planification familiale, c'est correct?"
    ),
    # ===== Default =====
    "patient_feedback_default": (
        "{patient_name} a visité {facility_name} le {visit_date}, c'est correct?"
    ),
    "vaccination_default": (
        "{patient_name} est venu pour {vaccine_name}, c'est correct?"
    ),
    "service_default": (
        "{patient_name} est venu pour {service_name}, c'est correct?"
    ),
}


# Spanish (es) confirmation messages
CONFIRMATION_MESSAGES_ES: Dict[str, str] = {
    # ===== Child Vaccination =====
    "child_vaccination": (
        "{child_name} vino para vacunación y recibió la {vaccine_name}, "
        "¿es correcto?"
    ),
    "child_vaccination_generic": (
        "{child_name} vino para vacunación y recibió la {vaccine_name}, "
        "¿es correcto?"
    ),
    "child_vaccination_bcg": (
        "{child_name} vino para vacunación y recibió la vacuna BCG, "
        "¿es correcto?"
    ),
    "child_vaccination_polio": (
        "{child_name} vino para vacunación y recibió la vacuna contra la Polio, "
        "¿es correcto?"
    ),
    "child_vaccination_penta1": (
        "{child_name} vino para vacunación y recibió la 1ra dosis de la vacuna Penta, "
        "¿es correcto?"
    ),
    "child_vaccination_penta2": (
        "{child_name} vino para vacunación y recibió la 2da dosis de la vacuna Penta, "
        "¿es correcto?"
    ),
    "child_vaccination_penta3": (
        "{child_name} vino para vacunación y recibió la 3ra dosis de la vacuna Penta, "
        "¿es correcto?"
    ),
    "child_vaccination_rr1": (
        "{child_name} vino para vacunación y recibió la vacuna contra sarampión-rubéola, "
        "¿es correcto?"
    ),
    # ===== Child Services =====
    "child_deworming": (
        "Durante esta visita, ¿recibió {child_name} medicamento antiparasitario?"
    ),
    "child_vitamin_a": (
        "Durante esta visita, ¿recibió {child_name} suplemento de Vitamina A?"
    ),
    "child_malnutrition_screening": (
        "Durante esta visita, ¿el trabajador de salud revisó a {child_name} por desnutrición, "
        "por ejemplo, midiendo el brazo con una cinta de colores o verificando el peso y la altura del niño?"
    ),
    # ===== Prenatal Care =====
    "prenatal_anc": (
        "Usted vino para atención prenatal (APN), ¿es correcto?"
    ),
    "prenatal_td_vaccine": (
        "Durante esta visita, ¿recibió la vacuna de Tétanos y Difteria (Td)?"
    ),
    "prenatal_first_trimester": (
        "Usted vino para su primera visita de atención prenatal (APN) y le dieron vitaminas "
        "y suplementos como tabletas de hierro y ácido fólico, ¿es correcto?"
    ),
    # ===== Maternity =====
    "maternity_delivery": (
        "Durante esta visita, ¿dio a luz en este centro de salud?"
    ),
    # ===== Family Planning =====
    "family_planning": (
        "Usted vino para servicios de planificación familiar, ¿es correcto?"
    ),
    # ===== Default =====
    "patient_feedback_default": (
        "{patient_name} visitó {facility_name} el {visit_date}, ¿es correcto?"
    ),
    "vaccination_default": (
        "{patient_name} vino para {vaccine_name}, ¿es correcto?"
    ),
    "service_default": (
        "{patient_name} vino para {service_name}, ¿es correcto?"
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
