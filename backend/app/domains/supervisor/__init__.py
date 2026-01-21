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
2. INTRODUCTION - Explain purpose and ask for time
3. CONFIRM_VISIT - Confirm visited facility on date
4. CONFIRM_SERVICE - Event-specific confirmation
5. SIDE_EFFECTS - [Optional] Check for side effects (vaccination)
6. SATISFACTION - [Optional] Collect rating
7. CLOSING - Thank and end call
"""

from backend.app.domains.supervisor.event_type_config import (
    EventTypeConfig,
    get_event_type_config,
    get_confirmation_message,
    EVENT_TYPE_CONFIGS,
)
from pipecat_flows import (
    FlowManager,
    FlowResult,
    NodeConfig,
    FlowsFunctionSchema,
    FlowArgs,
)
from backend.app.domains.supervisor.conversation_flow import (
    create_greeting_node,
    create_introduction_node,
    create_confirm_visit_node,
    create_confirm_service_node,
    create_side_effects_node,
    create_satisfaction_node,
    create_closing_node,
    GreetingResult,
    IntroductionResult,
    VisitConfirmationResult,
    ServiceConfirmationResult,
    SideEffectsResult,
    SatisfactionResult,
    ClosingResult,
)

__all__ = [
    # Event type configuration
    "EventTypeConfig",
    "get_event_type_config",
    "get_confirmation_message",
    "EVENT_TYPE_CONFIGS",
    # Flow management
    "FlowManager",
    "FlowResult",
    "NodeConfig",
    "FlowsFunctionSchema",
    "FlowArgs",
    # Flow nodes
    "create_greeting_node",
    "create_introduction_node",
    "create_confirm_visit_node",
    "create_confirm_service_node",
    "create_side_effects_node",
    "create_satisfaction_node",
    "create_closing_node",
    # Flow result types
    "GreetingResult",
    "IntroductionResult",
    "VisitConfirmationResult",
    "ServiceConfirmationResult",
    "SideEffectsResult",
    "SatisfactionResult",
    "ClosingResult",
]

