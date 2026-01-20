"""
Event Type Configuration for Patient Feedback Collection.

This module defines how different Clarity event types are handled in the
patient feedback call flow. Each event type maps to:
- A confirmation message key
- Optional side effects stage
- Optional satisfaction collection

All event types use the same unified flow:
1. GREETING → 2. CONFIRM_IDENTITY → 3. CONFIRM_VISIT → 4. CONFIRM_SERVICE →
5. [SIDE_EFFECTS] → 6. [SATISFACTION] → 7. COMPLETION

The event_type from Clarity determines which confirmation message to use.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from backend.app.models.enums import EventCategory


class EventTypeConfig(BaseModel):
    """
    Configuration for how to handle a Clarity event type.

    Maps a Clarity event type to flow behavior.
    """

    # Identity
    clarity_event_type: str = Field(
        ...,
        description="Raw event type from Clarity (e.g., 'Suivi des Enfants')",
    )
    event_category: EventCategory = Field(
        ...,
        description="Our category for this event type",
    )

    # Confirmation message
    confirmation_message_key: str = Field(
        ...,
        description="Key for confirmation message in prompts (e.g., 'child_vaccination_rr1')",
    )

    # Flow options
    requires_side_effects: bool = Field(
        default=False,
        description="Show side effects stage?",
    )
    requires_satisfaction: bool = Field(
        default=True,
        description="Collect satisfaction rating?",
    )
    requires_child_name: bool = Field(
        default=False,
        description="Use child_name in prompts (for child health events)?",
    )

    # Matching rules (to identify this event type from Clarity data)
    vaccine_patterns: List[str] = Field(
        default_factory=list,
        description="Vaccine names to match (case-insensitive)",
    )
    attribute_patterns: Dict[str, str] = Field(
        default_factory=dict,
        description="Attribute values to match (key: regex pattern)",
    )

    # Is this a callable event?
    is_callable: bool = Field(
        default=True,
        description="False for TB, HIV (data only, no calls)",
    )

    # Description for documentation
    description: Optional[str] = Field(
        default=None,
        description="Human-readable description of this event type",
    )


# ============================================================================
# Haiti Event Type Configurations
# ============================================================================

EVENT_TYPE_CONFIGS: List[EventTypeConfig] = [
    # -------------------------------------------------------------------------
    # CHILD VACCINATION Events (requires_side_effects=True)
    # -------------------------------------------------------------------------
    EventTypeConfig(
        clarity_event_type="Suivi des Enfants (moins de 5 ans)",
        event_category=EventCategory.CHILD_VACCINATION,
        confirmation_message_key="child_vaccination_rr1",
        requires_side_effects=True,
        requires_child_name=True,
        vaccine_patterns=["Rougeole rubéole 1", "rougeole-rubéole", "RR1"],
        description="Child vaccination - Measles-Rubella dose 1",
    ),
    EventTypeConfig(
        clarity_event_type="Suivi des Enfants (moins de 5 ans)",
        event_category=EventCategory.CHILD_VACCINATION,
        confirmation_message_key="child_vaccination_rr2",
        requires_side_effects=True,
        requires_child_name=True,
        vaccine_patterns=["Rougeole rubéole 2", "RR2"],
        description="Child vaccination - Measles-Rubella dose 2",
    ),
    EventTypeConfig(
        clarity_event_type="Suivi des Enfants (moins de 5 ans)",
        event_category=EventCategory.CHILD_VACCINATION,
        confirmation_message_key="child_vaccination_penta1",
        requires_side_effects=True,
        requires_child_name=True,
        vaccine_patterns=["Penta 1", "Pentavalent 1", "PENTA1"],
        description="Child vaccination - Pentavalent dose 1",
    ),
    EventTypeConfig(
        clarity_event_type="Suivi des Enfants (moins de 5 ans)",
        event_category=EventCategory.CHILD_VACCINATION,
        confirmation_message_key="child_vaccination_penta2",
        requires_side_effects=True,
        requires_child_name=True,
        vaccine_patterns=["Penta 2", "Pentavalent 2", "PENTA2"],
        description="Child vaccination - Pentavalent dose 2",
    ),
    EventTypeConfig(
        clarity_event_type="Suivi des Enfants (moins de 5 ans)",
        event_category=EventCategory.CHILD_VACCINATION,
        confirmation_message_key="child_vaccination_penta3",
        requires_side_effects=True,
        requires_child_name=True,
        vaccine_patterns=["Penta 3", "Pentavalent 3", "PENTA3"],
        description="Child vaccination - Pentavalent dose 3",
    ),
    EventTypeConfig(
        clarity_event_type="Suivi des Enfants (moins de 5 ans)",
        event_category=EventCategory.CHILD_VACCINATION,
        confirmation_message_key="child_vaccination_bcg",
        requires_side_effects=True,
        requires_child_name=True,
        vaccine_patterns=["BCG"],
        description="Child vaccination - BCG",
    ),
    EventTypeConfig(
        clarity_event_type="Suivi des Enfants (moins de 5 ans)",
        event_category=EventCategory.CHILD_VACCINATION,
        confirmation_message_key="child_vaccination_polio",
        requires_side_effects=True,
        requires_child_name=True,
        vaccine_patterns=["VPO", "Polio", "OPV"],
        description="Child vaccination - Polio",
    ),
    EventTypeConfig(
        clarity_event_type="Suivi des Enfants (moins de 5 ans)",
        event_category=EventCategory.CHILD_VACCINATION,
        confirmation_message_key="child_vaccination_rotavirus",
        requires_side_effects=True,
        requires_child_name=True,
        vaccine_patterns=["Rotavirus", "Rota"],
        description="Child vaccination - Rotavirus",
    ),
    EventTypeConfig(
        clarity_event_type="Suivi des Enfants (moins de 5 ans)",
        event_category=EventCategory.CHILD_VACCINATION,
        confirmation_message_key="child_vaccination_pneumo",
        requires_side_effects=True,
        requires_child_name=True,
        vaccine_patterns=["Pneumo", "PCV"],
        description="Child vaccination - Pneumococcal",
    ),
    EventTypeConfig(
        clarity_event_type="Suivi des Enfants (moins de 5 ans)",
        event_category=EventCategory.CHILD_VACCINATION,
        confirmation_message_key="child_vaccination_generic",
        requires_side_effects=True,
        requires_child_name=True,
        vaccine_patterns=[],  # Default for any unmatched vaccination
        description="Child vaccination - Generic",
    ),

    # -------------------------------------------------------------------------
    # CHILD HEALTH Events (no side effects, requires_child_name=True)
    # -------------------------------------------------------------------------
    EventTypeConfig(
        clarity_event_type="Suivi des Enfants (moins de 5 ans)",
        event_category=EventCategory.CHILD_HEALTH,
        confirmation_message_key="child_deworming",
        requires_side_effects=False,
        requires_child_name=True,
        attribute_patterns={"service_type": "deworming|vermifuge"},
        description="Child health - Deworming",
    ),
    EventTypeConfig(
        clarity_event_type="Suivi des Enfants (moins de 5 ans)",
        event_category=EventCategory.CHILD_HEALTH,
        confirmation_message_key="child_vitamin_a",
        requires_side_effects=False,
        requires_child_name=True,
        attribute_patterns={"service_type": "vitamin.*a|vitamine.*a"},
        description="Child health - Vitamin A supplementation",
    ),
    EventTypeConfig(
        clarity_event_type="Suivi des Enfants (moins de 5 ans)",
        event_category=EventCategory.CHILD_HEALTH,
        confirmation_message_key="child_malnutrition",
        requires_side_effects=False,
        requires_child_name=True,
        attribute_patterns={"service_type": "malnutrition|nutrition"},
        description="Child health - Malnutrition screening",
    ),
    EventTypeConfig(
        clarity_event_type="Suivi des Enfants (moins de 5 ans)",
        event_category=EventCategory.CHILD_HEALTH,
        confirmation_message_key="child_growth_monitoring",
        requires_side_effects=False,
        requires_child_name=True,
        attribute_patterns={"service_type": "growth|croissance"},
        description="Child health - Growth monitoring",
    ),

    # -------------------------------------------------------------------------
    # PRENATAL Events
    # -------------------------------------------------------------------------
    EventTypeConfig(
        clarity_event_type="Prenatal",
        event_category=EventCategory.PRENATAL,
        confirmation_message_key="prenatal_anc",
        requires_side_effects=False,
        requires_child_name=False,
        description="Prenatal - Antenatal care visit",
    ),
    EventTypeConfig(
        clarity_event_type="Prenatal",
        event_category=EventCategory.PRENATAL,
        confirmation_message_key="prenatal_first_trimester",
        requires_side_effects=False,
        requires_child_name=False,
        attribute_patterns={"trimester": "1|first|premier"},
        description="Prenatal - First trimester ANC",
    ),
    EventTypeConfig(
        clarity_event_type="Prenatal",
        event_category=EventCategory.PRENATAL,
        confirmation_message_key="prenatal_td_vaccine",
        requires_side_effects=True,  # TD vaccine may have side effects
        requires_child_name=False,
        vaccine_patterns=["Td", "Tetanus", "Diphtheria"],
        description="Prenatal - Td vaccination",
    ),

    # -------------------------------------------------------------------------
    # MATERNITY Events
    # -------------------------------------------------------------------------
    EventTypeConfig(
        clarity_event_type="Maternité",
        event_category=EventCategory.MATERNITY,
        confirmation_message_key="maternity_delivery",
        requires_side_effects=False,
        requires_child_name=False,
        attribute_patterns={"delivery_type": "normal|vaginal"},
        description="Maternity - Normal delivery",
    ),
    EventTypeConfig(
        clarity_event_type="Maternité",
        event_category=EventCategory.MATERNITY,
        confirmation_message_key="maternity_csection",
        requires_side_effects=False,
        requires_child_name=False,
        attribute_patterns={"delivery_type": "cesarean|csection|c-section"},
        description="Maternity - C-section delivery",
    ),

    # -------------------------------------------------------------------------
    # POSTNATAL Events
    # -------------------------------------------------------------------------
    EventTypeConfig(
        clarity_event_type="Postnatal",
        event_category=EventCategory.POSTNATAL,
        confirmation_message_key="postnatal_visit",
        requires_side_effects=False,
        requires_child_name=False,
        description="Postnatal - Postnatal checkup",
    ),
    EventTypeConfig(
        clarity_event_type="Postnatal",
        event_category=EventCategory.POSTNATAL,
        confirmation_message_key="postnatal_within_3_days",
        requires_side_effects=False,
        requires_child_name=False,
        attribute_patterns={"days_after_birth": "0|1|2|3"},
        description="Postnatal - Visit within 3 days of birth",
    ),

    # -------------------------------------------------------------------------
    # CURATIVE Events
    # -------------------------------------------------------------------------
    EventTypeConfig(
        clarity_event_type="Morbidité",
        event_category=EventCategory.CURATIVE,
        confirmation_message_key="curative_morbidity",
        requires_side_effects=False,
        requires_child_name=False,
        description="Curative - New consultation",
    ),
    EventTypeConfig(
        clarity_event_type="Consultation Nouvelle",
        event_category=EventCategory.CURATIVE,
        confirmation_message_key="curative_consultation",
        requires_side_effects=False,
        requires_child_name=False,
        description="Curative - New consultation",
    ),

    # -------------------------------------------------------------------------
    # REFERRAL Events
    # -------------------------------------------------------------------------
    EventTypeConfig(
        clarity_event_type="Référence Institutionnelle",
        event_category=EventCategory.REFERRAL,
        confirmation_message_key="referral_institutional",
        requires_side_effects=False,
        requires_child_name=False,
        description="Referral - Institutional referral",
    ),

    # -------------------------------------------------------------------------
    # FAMILY PLANNING Events
    # -------------------------------------------------------------------------
    EventTypeConfig(
        clarity_event_type="Planning Familial",
        event_category=EventCategory.FAMILY_PLANNING,
        confirmation_message_key="family_planning",
        requires_side_effects=False,
        requires_child_name=False,
        description="Family Planning - Family planning services",
    ),

    # -------------------------------------------------------------------------
    # NO_CALL Events (data only, no calls made)
    # -------------------------------------------------------------------------
    EventTypeConfig(
        clarity_event_type="Cas de Tuberculose",
        event_category=EventCategory.TB,
        confirmation_message_key="",  # No call made
        requires_side_effects=False,
        requires_child_name=False,
        is_callable=False,
        description="TB - Data only, no calls",
    ),
    EventTypeConfig(
        clarity_event_type="HIV/ARV",
        event_category=EventCategory.HIV,
        confirmation_message_key="",  # No call made
        requires_side_effects=False,
        requires_child_name=False,
        is_callable=False,
        description="HIV - Data only, no calls",
    ),

    # -------------------------------------------------------------------------
    # DEFAULT/OTHER Events
    # -------------------------------------------------------------------------
    EventTypeConfig(
        clarity_event_type="*",  # Wildcard for unmatched events
        event_category=EventCategory.OTHER,
        confirmation_message_key="generic_visit",
        requires_side_effects=False,
        requires_child_name=False,
        description="Generic visit confirmation",
    ),
]


# ============================================================================
# Lookup Functions
# ============================================================================

def get_event_type_config(
    clarity_event_type: str,
    vaccines: List[Dict[str, Any]] = None,
    attributes: Dict[str, Any] = None,
) -> EventTypeConfig:
    """
    Get the event type configuration for a Clarity event.

    Args:
        clarity_event_type: Raw event type from Clarity
        vaccines: List of vaccine info from Clarity
        attributes: Additional attributes from Clarity

    Returns:
        EventTypeConfig for the event, or default OTHER config
    """
    import re

    vaccines = vaccines or []
    attributes = attributes or {}

    # First, try exact match on clarity_event_type
    matching_configs = [
        config for config in EVENT_TYPE_CONFIGS
        if config.clarity_event_type == clarity_event_type or config.clarity_event_type == "*"
    ]

    if not matching_configs:
        # Return default config
        return _get_default_config()

    # For vaccination events, match on vaccine patterns
    vaccine_names = [v.get("name", "").lower() for v in vaccines]

    for config in matching_configs:
        # Skip wildcard unless it's the only option
        if config.clarity_event_type == "*":
            continue

        # Check vaccine patterns
        if config.vaccine_patterns:
            for pattern in config.vaccine_patterns:
                if any(pattern.lower() in name for name in vaccine_names):
                    return config

        # Check attribute patterns
        if config.attribute_patterns:
            all_match = True
            for attr_key, pattern in config.attribute_patterns.items():
                attr_value = str(attributes.get(attr_key, "")).lower()
                if not re.search(pattern.lower(), attr_value):
                    all_match = False
                    break
            if all_match:
                return config

        # If no patterns specified, this is a general match
        if not config.vaccine_patterns and not config.attribute_patterns:
            return config

    # Return wildcard config or default
    wildcard_configs = [c for c in matching_configs if c.clarity_event_type == "*"]
    if wildcard_configs:
        return wildcard_configs[0]

    return _get_default_config()


def _get_default_config() -> EventTypeConfig:
    """Return the default event type config for unknown events."""
    return EventTypeConfig(
        clarity_event_type="unknown",
        event_category=EventCategory.OTHER,
        confirmation_message_key="generic_visit",
        requires_side_effects=False,
        requires_child_name=False,
        description="Unknown event type - using generic confirmation",
    )


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
            - child_name: Child's name
            - patient_name: Patient's name
            - vaccine_name: Vaccine name
            - facility_name: Facility name
            - visit_date: Date of visit

    Returns:
        Localized confirmation message with variables interpolated
    """
    from backend.app.domains.supervisor.prompts.confirmation_messages import (
        CONFIRMATION_MESSAGES,
    )

    # Get messages for language (fallback to English)
    messages = CONFIRMATION_MESSAGES.get(language, CONFIRMATION_MESSAGES.get("en", {}))

    # Get message for key (fallback to generic)
    message = messages.get(confirmation_message_key, messages.get("generic_visit", ""))

    # Interpolate template variables
    try:
        return message.format(**template_vars)
    except KeyError:
        # If variable missing, return message with placeholders
        return message


def is_callable_event(clarity_event_type: str) -> bool:
    """
    Check if an event type should trigger a call.

    Some events like TB and HIV are data-only and should not trigger calls.
    """
    config = get_event_type_config(clarity_event_type)
    return config.is_callable


def get_all_callable_event_types() -> List[str]:
    """Get list of all Clarity event types that should trigger calls."""
    return [
        config.clarity_event_type
        for config in EVENT_TYPE_CONFIGS
        if config.is_callable and config.clarity_event_type != "*"
    ]


def get_skip_event_types() -> List[str]:
    """Get list of Clarity event types that should NOT trigger calls."""
    return [
        config.clarity_event_type
        for config in EVENT_TYPE_CONFIGS
        if not config.is_callable
    ]
