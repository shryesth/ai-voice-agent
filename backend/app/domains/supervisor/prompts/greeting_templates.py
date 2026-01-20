"""
Greeting templates for different contact types in all supported languages.

Templates vary based on who we're calling:
- PATIENT: Calling patient directly
- GUARDIAN: Calling parent/guardian (for children)
- CAREGIVER: Calling caregiver
"""

from typing import Dict
from backend.app.models.enums import ContactType


# Greeting templates organized by language and contact type
GREETING_TEMPLATES: Dict[str, Dict[str, str]] = {
    # =========================================================================
    # ENGLISH (en)
    # =========================================================================
    "en": {
        ContactType.PATIENT: "Hello, am I speaking with {contact_name}?",
        ContactType.GUARDIAN: "Hello, am I speaking with the parent or guardian of {patient_name}?",
        ContactType.CAREGIVER: "Hello, am I speaking with the caregiver of {patient_name}?",
        ContactType.NEXT_OF_KIN: "Hello, am I speaking with a family member of {patient_name}?",
        ContactType.UNKNOWN: "Hello, am I speaking with {contact_name}?",
    },

    # =========================================================================
    # HAITIAN CREOLE (ht)
    # =========================================================================
    "ht": {
        ContactType.PATIENT: "Bonjou, èske mwen pale ak {contact_name}?",
        ContactType.GUARDIAN: "Bonjou, èske mwen pale ak paran oswa gadyen {patient_name}?",
        ContactType.CAREGIVER: "Bonjou, èske mwen pale ak moun k ap pran swen {patient_name}?",
        ContactType.NEXT_OF_KIN: "Bonjou, èske mwen pale ak yon manm fanmi {patient_name}?",
        ContactType.UNKNOWN: "Bonjou, èske mwen pale ak {contact_name}?",
    },

    # =========================================================================
    # FRENCH (fr)
    # =========================================================================
    "fr": {
        ContactType.PATIENT: "Bonjour, suis-je en ligne avec {contact_name}?",
        ContactType.GUARDIAN: "Bonjour, suis-je en ligne avec le parent ou tuteur de {patient_name}?",
        ContactType.CAREGIVER: "Bonjour, suis-je en ligne avec la personne qui s'occupe de {patient_name}?",
        ContactType.NEXT_OF_KIN: "Bonjour, suis-je en ligne avec un membre de la famille de {patient_name}?",
        ContactType.UNKNOWN: "Bonjour, suis-je en ligne avec {contact_name}?",
    },

    # =========================================================================
    # SPANISH (es)
    # =========================================================================
    "es": {
        ContactType.PATIENT: "Hola, ¿estoy hablando con {contact_name}?",
        ContactType.GUARDIAN: "Hola, ¿estoy hablando con el padre o tutor de {patient_name}?",
        ContactType.CAREGIVER: "Hola, ¿estoy hablando con la persona que cuida a {patient_name}?",
        ContactType.NEXT_OF_KIN: "Hola, ¿estoy hablando con un familiar de {patient_name}?",
        ContactType.UNKNOWN: "Hola, ¿estoy hablando con {contact_name}?",
    },
}


# Introduction templates (after confirming identity)
INTRODUCTION_TEMPLATES: Dict[str, str] = {
    "en": "I am an AI assistant calling on behalf of the Ministry of Health to follow up on a recent health visit to {facility_name}.",
    "ht": "Mwen se yon asistan AI k ap rele sou non Ministè Sante a pou swiv yon vizit sante resan nan {facility_name}.",
    "fr": "Je suis un assistant IA qui appelle de la part du Ministère de la Santé pour faire le suivi d'une visite de santé récente à {facility_name}.",
    "es": "Soy un asistente de IA que llama en nombre del Ministerio de Salud para dar seguimiento a una visita de salud reciente a {facility_name}.",
}


# Satisfaction question templates
SATISFACTION_TEMPLATES: Dict[str, str] = {
    "en": "On a scale of 1 to 10, where 1 is very poor and 10 is excellent, how would you rate your overall experience at the health facility?",
    "ht": "Sou yon echèl 1 a 10, kote 1 se trè mal epi 10 se ekselan, kijan ou ta evalye eksperyans ou nan etablisman sante a?",
    "fr": "Sur une échelle de 1 à 10, où 1 est très mauvais et 10 est excellent, comment évalueriez-vous votre expérience globale à l'établissement de santé?",
    "es": "En una escala del 1 al 10, donde 1 es muy malo y 10 es excelente, ¿cómo calificaría su experiencia general en el establecimiento de salud?",
}


# Side effects question templates
SIDE_EFFECTS_TEMPLATES: Dict[str, str] = {
    "en": "After the vaccination, did {patient_ref} experience any side effects such as fever, swelling at the injection site, or any other symptoms?",
    "ht": "Apre vaksinasyon an, èske {patient_ref} te gen okenn efè segondè tankou fyèv, anflamasyon nan kote yo te piki a, oswa nenpòt lòt sentòm?",
    "fr": "Après la vaccination, est-ce que {patient_ref} a ressenti des effets secondaires comme de la fièvre, un gonflement au site d'injection, ou d'autres symptômes?",
    "es": "Después de la vacunación, ¿experimentó {patient_ref} algún efecto secundario como fiebre, hinchazón en el sitio de la inyección u otros síntomas?",
}


# Closing templates
CLOSING_TEMPLATES: Dict[str, str] = {
    "en": "Thank you for your time and for helping us improve healthcare services. Have a great day!",
    "ht": "Mèsi pou tan ou ak pou ede nou amelyore sèvis sante yo. Pase yon bèl jounen!",
    "fr": "Merci pour votre temps et pour nous aider à améliorer les services de santé. Bonne journée!",
    "es": "Gracias por su tiempo y por ayudarnos a mejorar los servicios de salud. ¡Que tenga un buen día!",
}


def get_greeting(
    contact_type: ContactType,
    language: str = "en",
    **template_vars,
) -> str:
    """
    Get the localized greeting for a contact type.

    Args:
        contact_type: Type of contact (PATIENT, GUARDIAN, CAREGIVER, etc.)
        language: Language code (en, ht, fr, es)
        **template_vars: Variables for template interpolation
            - contact_name: Name of the person being called
            - patient_name: Name of the patient (for guardian/caregiver)

    Returns:
        Localized greeting with variables interpolated
    """
    # Get templates for language (fallback to English)
    templates = GREETING_TEMPLATES.get(language, GREETING_TEMPLATES.get("en", {}))

    # Get template for contact type
    template = templates.get(contact_type, templates.get(ContactType.UNKNOWN, ""))

    # Provide defaults for template variables
    defaults = {
        "contact_name": "there",
        "patient_name": "the patient",
    }
    defaults.update(template_vars)

    # Interpolate template variables
    try:
        return template.format(**defaults)
    except KeyError:
        return template


def get_introduction(language: str = "en", facility_name: str = None) -> str:
    """Get the introduction message for the specified language."""
    template = INTRODUCTION_TEMPLATES.get(language, INTRODUCTION_TEMPLATES["en"])
    return template.format(facility_name=facility_name or "the health facility")


def get_satisfaction_question(language: str = "en") -> str:
    """Get the satisfaction rating question for the specified language."""
    return SATISFACTION_TEMPLATES.get(language, SATISFACTION_TEMPLATES["en"])


def get_side_effects_question(
    language: str = "en",
    patient_ref: str = None,
) -> str:
    """
    Get the side effects question for the specified language.

    Args:
        language: Language code
        patient_ref: How to refer to the patient ("you", "your child", etc.)
    """
    template = SIDE_EFFECTS_TEMPLATES.get(language, SIDE_EFFECTS_TEMPLATES["en"])

    # Default patient reference based on language
    if patient_ref is None:
        patient_ref = {
            "en": "you or your child",
            "ht": "ou oswa pitit ou",
            "fr": "vous ou votre enfant",
            "es": "usted o su hijo/a",
        }.get(language, "the patient")

    return template.format(patient_ref=patient_ref)


def get_closing(language: str = "en") -> str:
    """Get the closing message for the specified language."""
    return CLOSING_TEMPLATES.get(language, CLOSING_TEMPLATES["en"])
