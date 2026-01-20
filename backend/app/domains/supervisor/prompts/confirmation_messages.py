"""
Confirmation messages for each event type in all supported languages.

Each message key corresponds to an EventTypeConfig.confirmation_message_key.
Messages use Python format strings with these variables:
- {child_name}: Child's name (for child health events)
- {patient_name}: Patient's name
- {vaccine_name}: Vaccine name
- {facility_name}: Name of health facility
- {visit_date}: Date of visit (human-readable)
"""

from typing import Dict

# Confirmation messages organized by language
CONFIRMATION_MESSAGES: Dict[str, Dict[str, str]] = {
    # =========================================================================
    # ENGLISH (en)
    # =========================================================================
    "en": {
        # Child Vaccination
        "child_vaccination_rr1": "{child_name} came for immunization and received the measles-rubella vaccine dose 1, is that right?",
        "child_vaccination_rr2": "{child_name} came for immunization and received the measles-rubella vaccine dose 2, is that right?",
        "child_vaccination_penta1": "{child_name} came for immunization and received the 1st dose of Pentavalent vaccine, is that right?",
        "child_vaccination_penta2": "{child_name} came for immunization and received the 2nd dose of Pentavalent vaccine, is that right?",
        "child_vaccination_penta3": "{child_name} came for immunization and received the 3rd dose of Pentavalent vaccine, is that right?",
        "child_vaccination_bcg": "{child_name} came for immunization and received the BCG vaccine, is that right?",
        "child_vaccination_polio": "{child_name} came for immunization and received the Polio vaccine, is that right?",
        "child_vaccination_rotavirus": "{child_name} came for immunization and received the Rotavirus vaccine, is that right?",
        "child_vaccination_pneumo": "{child_name} came for immunization and received the Pneumococcal vaccine, is that right?",
        "child_vaccination_generic": "{child_name} came for immunization and received a vaccine, is that right?",

        # Child Health
        "child_deworming": "During this visit, did {child_name} receive deworming medicine?",
        "child_vitamin_a": "During this visit, did {child_name} receive Vitamin A supplement?",
        "child_malnutrition": "During this visit, did the health worker check {child_name} for malnutrition?",
        "child_growth_monitoring": "During this visit, did the health worker measure {child_name}'s growth?",

        # Prenatal
        "prenatal_anc": "You came for antenatal care (ANC), is that right?",
        "prenatal_first_trimester": "You came for your first ANC visit and were given iron and folic acid tablets, is that right?",
        "prenatal_td_vaccine": "Did you receive the Tetanus and Diphtheria (Td) vaccine during your visit?",

        # Maternity
        "maternity_delivery": "During this visit, did you give birth at this health facility?",
        "maternity_csection": "Was your delivery performed through a C-section?",

        # Postnatal
        "postnatal_visit": "You came for a postnatal check-up, is that right?",
        "postnatal_within_3_days": "Was this postnatal check-up conducted within three days after giving birth?",

        # Curative
        "curative_morbidity": "You came for a new curative consultation, is that right?",
        "curative_consultation": "You came for a medical consultation, is that right?",

        # Referral
        "referral_institutional": "You were referred to a next level health institution for follow up, is that right?",

        # Family Planning
        "family_planning": "You came for family planning services, is that right?",

        # Generic
        "generic_visit": "You visited the health facility on {visit_date}, is that right?",
    },

    # =========================================================================
    # HAITIAN CREOLE (ht)
    # =========================================================================
    "ht": {
        # Child Vaccination
        "child_vaccination_rr1": "{child_name} te vini pou vaksinasyon epi li te resevwa vaksen woujòl-ribyèl doz 1, èske sa kòrèk?",
        "child_vaccination_rr2": "{child_name} te vini pou vaksinasyon epi li te resevwa vaksen woujòl-ribyèl doz 2, èske sa kòrèk?",
        "child_vaccination_penta1": "{child_name} te vini pou vaksinasyon epi li te resevwa premye doz vaksen Pentavalan, èske sa kòrèk?",
        "child_vaccination_penta2": "{child_name} te vini pou vaksinasyon epi li te resevwa dezyèm doz vaksen Pentavalan, èske sa kòrèk?",
        "child_vaccination_penta3": "{child_name} te vini pou vaksinasyon epi li te resevwa twazyèm doz vaksen Pentavalan, èske sa kòrèk?",
        "child_vaccination_bcg": "{child_name} te vini pou vaksinasyon epi li te resevwa vaksen BCG, èske sa kòrèk?",
        "child_vaccination_polio": "{child_name} te vini pou vaksinasyon epi li te resevwa vaksen Polyo, èske sa kòrèk?",
        "child_vaccination_rotavirus": "{child_name} te vini pou vaksinasyon epi li te resevwa vaksen Rotaviris, èske sa kòrèk?",
        "child_vaccination_pneumo": "{child_name} te vini pou vaksinasyon epi li te resevwa vaksen Pnemokok, èske sa kòrèk?",
        "child_vaccination_generic": "{child_name} te vini pou vaksinasyon epi li te resevwa yon vaksen, èske sa kòrèk?",

        # Child Health
        "child_deworming": "Pandan vizit sa a, èske {child_name} te resevwa medikaman pou vè?",
        "child_vitamin_a": "Pandan vizit sa a, èske {child_name} te resevwa vitamin A?",
        "child_malnutrition": "Pandan vizit sa a, èske ajan sante a te tcheke {child_name} pou malnitrisyon?",
        "child_growth_monitoring": "Pandan vizit sa a, èske ajan sante a te mezire kwasans {child_name}?",

        # Prenatal
        "prenatal_anc": "Ou te vini pou swen anvan akouchman (CPN), èske sa kòrèk?",
        "prenatal_first_trimester": "Ou te vini pou premye vizit CPN ou epi yo te ba ou konprime fè ak asid folik, èske sa kòrèk?",
        "prenatal_td_vaccine": "Èske ou te resevwa vaksen Tetanòs ak Difteryèm (Td) pandan vizit ou a?",

        # Maternity
        "maternity_delivery": "Pandan vizit sa a, èske ou te akouche nan etablisman sante sa a?",
        "maternity_csection": "Èske akouchman ou te fèt pa sezaryèn?",

        # Postnatal
        "postnatal_visit": "Ou te vini pou yon egzamen apre akouchman, èske sa kòrèk?",
        "postnatal_within_3_days": "Èske egzamen apre akouchman sa a te fèt nan twa jou apre ou te fin akouche?",

        # Curative
        "curative_morbidity": "Ou te vini pou yon nouvo konsiltasyon, èske sa kòrèk?",
        "curative_consultation": "Ou te vini pou yon konsiltasyon medikal, èske sa kòrèk?",

        # Referral
        "referral_institutional": "Yo te refere ou nan yon lòt etablisman sante pou swivi, èske sa kòrèk?",

        # Family Planning
        "family_planning": "Ou te vini pou sèvis planifikasyon familyal, èske sa kòrèk?",

        # Generic
        "generic_visit": "Ou te vizite etablisman sante a nan {visit_date}, èske sa kòrèk?",
    },

    # =========================================================================
    # FRENCH (fr)
    # =========================================================================
    "fr": {
        # Child Vaccination
        "child_vaccination_rr1": "{child_name} est venu pour la vaccination et a reçu le vaccin rougeole-rubéole dose 1, est-ce correct?",
        "child_vaccination_rr2": "{child_name} est venu pour la vaccination et a reçu le vaccin rougeole-rubéole dose 2, est-ce correct?",
        "child_vaccination_penta1": "{child_name} est venu pour la vaccination et a reçu la 1ère dose du vaccin Pentavalent, est-ce correct?",
        "child_vaccination_penta2": "{child_name} est venu pour la vaccination et a reçu la 2ème dose du vaccin Pentavalent, est-ce correct?",
        "child_vaccination_penta3": "{child_name} est venu pour la vaccination et a reçu la 3ème dose du vaccin Pentavalent, est-ce correct?",
        "child_vaccination_bcg": "{child_name} est venu pour la vaccination et a reçu le vaccin BCG, est-ce correct?",
        "child_vaccination_polio": "{child_name} est venu pour la vaccination et a reçu le vaccin Polio, est-ce correct?",
        "child_vaccination_rotavirus": "{child_name} est venu pour la vaccination et a reçu le vaccin Rotavirus, est-ce correct?",
        "child_vaccination_pneumo": "{child_name} est venu pour la vaccination et a reçu le vaccin Pneumocoque, est-ce correct?",
        "child_vaccination_generic": "{child_name} est venu pour la vaccination et a reçu un vaccin, est-ce correct?",

        # Child Health
        "child_deworming": "Lors de cette visite, est-ce que {child_name} a reçu un médicament vermifuge?",
        "child_vitamin_a": "Lors de cette visite, est-ce que {child_name} a reçu un supplément de vitamine A?",
        "child_malnutrition": "Lors de cette visite, est-ce que l'agent de santé a vérifié {child_name} pour la malnutrition?",
        "child_growth_monitoring": "Lors de cette visite, est-ce que l'agent de santé a mesuré la croissance de {child_name}?",

        # Prenatal
        "prenatal_anc": "Vous êtes venue pour des soins prénataux (CPN), est-ce correct?",
        "prenatal_first_trimester": "Vous êtes venue pour votre première visite CPN et on vous a donné des comprimés de fer et d'acide folique, est-ce correct?",
        "prenatal_td_vaccine": "Avez-vous reçu le vaccin Tétanos et Diphtérie (Td) lors de votre visite?",

        # Maternity
        "maternity_delivery": "Lors de cette visite, avez-vous accouché dans cet établissement de santé?",
        "maternity_csection": "Votre accouchement a-t-il été réalisé par césarienne?",

        # Postnatal
        "postnatal_visit": "Vous êtes venue pour un examen postnatal, est-ce correct?",
        "postnatal_within_3_days": "Cet examen postnatal a-t-il été effectué dans les trois jours suivant l'accouchement?",

        # Curative
        "curative_morbidity": "Vous êtes venu pour une nouvelle consultation curative, est-ce correct?",
        "curative_consultation": "Vous êtes venu pour une consultation médicale, est-ce correct?",

        # Referral
        "referral_institutional": "Vous avez été référé à un établissement de santé de niveau supérieur pour un suivi, est-ce correct?",

        # Family Planning
        "family_planning": "Vous êtes venu pour des services de planification familiale, est-ce correct?",

        # Generic
        "generic_visit": "Vous avez visité l'établissement de santé le {visit_date}, est-ce correct?",
    },

    # =========================================================================
    # SPANISH (es)
    # =========================================================================
    "es": {
        # Child Vaccination
        "child_vaccination_rr1": "{child_name} vino para vacunación y recibió la vacuna sarampión-rubéola dosis 1, ¿es correcto?",
        "child_vaccination_rr2": "{child_name} vino para vacunación y recibió la vacuna sarampión-rubéola dosis 2, ¿es correcto?",
        "child_vaccination_penta1": "{child_name} vino para vacunación y recibió la 1ra dosis de la vacuna Pentavalente, ¿es correcto?",
        "child_vaccination_penta2": "{child_name} vino para vacunación y recibió la 2da dosis de la vacuna Pentavalente, ¿es correcto?",
        "child_vaccination_penta3": "{child_name} vino para vacunación y recibió la 3ra dosis de la vacuna Pentavalente, ¿es correcto?",
        "child_vaccination_bcg": "{child_name} vino para vacunación y recibió la vacuna BCG, ¿es correcto?",
        "child_vaccination_polio": "{child_name} vino para vacunación y recibió la vacuna Polio, ¿es correcto?",
        "child_vaccination_rotavirus": "{child_name} vino para vacunación y recibió la vacuna Rotavirus, ¿es correcto?",
        "child_vaccination_pneumo": "{child_name} vino para vacunación y recibió la vacuna Neumococo, ¿es correcto?",
        "child_vaccination_generic": "{child_name} vino para vacunación y recibió una vacuna, ¿es correcto?",

        # Child Health
        "child_deworming": "Durante esta visita, ¿recibió {child_name} medicamento antiparasitario?",
        "child_vitamin_a": "Durante esta visita, ¿recibió {child_name} suplemento de vitamina A?",
        "child_malnutrition": "Durante esta visita, ¿el trabajador de salud revisó a {child_name} por desnutrición?",
        "child_growth_monitoring": "Durante esta visita, ¿el trabajador de salud midió el crecimiento de {child_name}?",

        # Prenatal
        "prenatal_anc": "Usted vino para atención prenatal (APN), ¿es correcto?",
        "prenatal_first_trimester": "Usted vino para su primera visita de APN y le dieron tabletas de hierro y ácido fólico, ¿es correcto?",
        "prenatal_td_vaccine": "¿Recibió la vacuna de Tétanos y Difteria (Td) durante su visita?",

        # Maternity
        "maternity_delivery": "Durante esta visita, ¿dio a luz en este establecimiento de salud?",
        "maternity_csection": "¿Su parto fue realizado por cesárea?",

        # Postnatal
        "postnatal_visit": "Usted vino para un chequeo postnatal, ¿es correcto?",
        "postnatal_within_3_days": "¿Este chequeo postnatal fue realizado dentro de los tres días después del parto?",

        # Curative
        "curative_morbidity": "Usted vino para una nueva consulta curativa, ¿es correcto?",
        "curative_consultation": "Usted vino para una consulta médica, ¿es correcto?",

        # Referral
        "referral_institutional": "Usted fue referido a una institución de salud de mayor nivel para seguimiento, ¿es correcto?",

        # Family Planning
        "family_planning": "Usted vino para servicios de planificación familiar, ¿es correcto?",

        # Generic
        "generic_visit": "Usted visitó el establecimiento de salud el {visit_date}, ¿es correcto?",
    },
}


def get_confirmation_message(
    confirmation_message_key: str,
    language: str = "en",
    **template_vars,
) -> str:
    """
    Get the localized confirmation message for an event type.

    Args:
        confirmation_message_key: Key from EventTypeConfig
        language: Language code (en, ht, fr, es)
        **template_vars: Variables for template interpolation

    Returns:
        Localized confirmation message with variables interpolated
    """
    # Get messages for language (fallback to English)
    messages = CONFIRMATION_MESSAGES.get(language, CONFIRMATION_MESSAGES.get("en", {}))

    # Get message for key (fallback to generic)
    message = messages.get(confirmation_message_key, messages.get("generic_visit", ""))

    # Provide defaults for template variables
    defaults = {
        "child_name": "the child",
        "patient_name": "you",
        "vaccine_name": "vaccine",
        "facility_name": "the health facility",
        "visit_date": "your recent visit",
    }
    defaults.update(template_vars)

    # Interpolate template variables
    try:
        return message.format(**defaults)
    except KeyError:
        # If variable missing, return message with placeholders
        return message
