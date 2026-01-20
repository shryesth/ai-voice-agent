"""
Supervisor - AI Calling Agent Platform Domain.

This domain contains the core logic for the Supervisor AI calling platform,
including:
- Event type configurations for patient feedback collection
- Multi-language prompt management
- Flow management for conversations
- Urgency detection
- Twilio integration
- Voice pipeline orchestration

Architecture:
    Geography
    └── CallQueue (multiple per geo)
        └── Recipients
            └── CallRecords

The unified Patient Feedback Collection flow works for all health event types:
1. GREETING - Greet and identify
2. CONFIRM_IDENTITY - Confirm speaking with correct person
3. CONFIRM_VISIT - Confirm visited facility on date
4. CONFIRM_SERVICE - Event-specific confirmation
5. SIDE_EFFECTS - [Optional] Check for side effects (vaccination)
6. SATISFACTION - [Optional] Collect rating
7. COMPLETION - Thank and end call
"""

from backend.app.domains.supervisor.event_type_config import (
    EventTypeConfig,
    get_event_type_config,
    get_confirmation_message,
    EVENT_TYPE_CONFIGS,
)

__all__ = [
    "EventTypeConfig",
    "get_event_type_config",
    "get_confirmation_message",
    "EVENT_TYPE_CONFIGS",
]
