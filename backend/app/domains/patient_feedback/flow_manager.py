"""
Flow manager for patient feedback conversation state.

Provides state management for the 6-stage conversation flow.
Function handling is now done by FunctionRegistry - this class
only manages state and task references.

Stages:
1. confirm_guardian - Verify speaking with correct person
2. confirm_visit - Verify patient visited facility on date
3. confirm_service - Verify specific service was received
4. record_side_effects - Record any side effects (vaccination only)
5. record_satisfaction - Collect 1-10 satisfaction rating
6. end_call - Thank and terminate call
"""

from typing import Any, Dict, Optional


class FlowManager:
    """
    State manager for multi-stage conversation flows.

    Manages conversation state and task references. Function handling
    is delegated to FunctionRegistry.
    """

    def __init__(self):
        """Initialize the flow manager with empty state."""
        self.state: Dict[str, Any] = {
            "current_stage": "confirm_guardian",
            "completed_stages": [],
            "completed": False
        }
        self._initialized: bool = False
        self.task: Any = None  # PipelineTask reference for queuing frames

    async def initialize(self) -> None:
        """Initialize the flow manager and prepare for conversation."""
        self._initialized = True
        self.state["started_at"] = True

    @property
    def is_complete(self) -> bool:
        """Check if the conversation flow has completed."""
        return self.state.get("completed", False)

    @property
    def current_stage(self) -> Optional[str]:
        """Get the name of the current conversation stage."""
        return self.state.get("current_stage")

    def get_conversation_data(self) -> Dict[str, Any]:
        """
        Get collected conversation data for persistence.

        Returns:
            Dictionary with all collected data from the conversation
        """
        return {
            "guardian_confirmed": self.state.get("guardian_confirmed"),
            "visit_confirmed": self.state.get("visit_confirmed"),
            "visit_discrepancy": self.state.get("visit_discrepancy", False),
            "service_confirmed": self.state.get("service_confirmed"),
            "service_not_confirmed_followup": self.state.get("service_not_confirmed_followup", False),
            "has_side_effects": self.state.get("has_side_effects"),
            "side_effects_details": self.state.get("side_effects_details"),
            "severe_side_effects": self.state.get("severe_side_effects", False),
            "satisfaction_rating": self.state.get("satisfaction_rating"),
            "low_satisfaction_followup": self.state.get("low_satisfaction_followup", False),
            "urgency_flagged": self.state.get("urgency_flagged", False),
            "completed": self.state.get("completed", False),
            "completion_reason": self.state.get("completion_reason"),
            "completed_stages": self.state.get("completed_stages", []),
            "current_stage": self.state.get("current_stage")
        }
