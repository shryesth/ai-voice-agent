"""
Function registry for patient feedback voice pipeline.

Registers all 6 conversation functions upfront with Pipecat-compatible handlers.
Uses correct FunctionCallParams signature and calls result_callback() to trigger
LLM continuation.

Functions:
1. confirm_guardian - Verify speaking with correct person
2. confirm_visit - Verify patient visited facility on date
3. confirm_service - Verify specific service was received
4. record_side_effects - Record any side effects (vaccination only)
5. record_satisfaction - Collect 1-10 satisfaction rating
6. end_call - Thank and terminate call with EndFrame
"""

from typing import Any, Dict, List, Optional
from pipecat.services.llm_service import FunctionCallParams
from pipecat.frames.frames import EndFrame, TTSSpeakFrame
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
import logging

logger = logging.getLogger(__name__)

# Maximum retry attempts before graceful exit
MAX_RETRIES = 2


class FunctionRegistry:
    """
    Registry of all conversation functions for patient feedback calls.

    Provides:
    - All function definitions in OpenAI tool format
    - Pipecat-compatible handlers with correct signature
    - State management through FlowManager reference
    - EndFrame queuing for call termination
    """

    def __init__(self, flow_manager: Any, call_record: Any):
        """
        Initialize the function registry.

        Args:
            flow_manager: FlowManager instance for state management
            call_record: CallRecord document for context
        """
        self.flow_manager = flow_manager
        self.call_record = call_record
        self.task = None  # PipelineTask reference, set after task creation

    def set_task(self, task: Any) -> None:
        """Set the PipelineTask reference for queuing frames."""
        self.task = task

    def get_all_tools(self) -> ToolsSchema:
        """
        Get all function definitions as Pipecat ToolsSchema.

        Returns:
            ToolsSchema with all 6 FunctionSchema definitions
        """
        function_schemas = [
            FunctionSchema(
                name="confirm_guardian",
                description="Confirm whether you are speaking with the correct guardian, patient, or authorized representative. Call this after verifying identity.",
                properties={
                    "confirmed": {
                        "type": "boolean",
                        "description": "True if speaking with the correct person (patient, guardian, or authorized representative)"
                    }
                },
                required=["confirmed"]
            ),
            FunctionSchema(
                name="confirm_visit",
                description="Confirm whether the patient visited the healthcare facility on the specified date. Call this after asking about the visit.",
                properties={
                    "confirmed": {
                        "type": "boolean",
                        "description": "True if the patient confirms visiting the facility"
                    }
                },
                required=["confirmed"]
            ),
            FunctionSchema(
                name="confirm_service",
                description="Confirm whether the patient received the specific health service (e.g., vaccination, checkup). Call this after asking about the service.",
                properties={
                    "confirmed": {
                        "type": "boolean",
                        "description": "True if the patient confirms receiving the service"
                    }
                },
                required=["confirmed"]
            ),
            FunctionSchema(
                name="record_side_effects",
                description="Record whether the patient experienced any side effects after vaccination and collect details. Only use for vaccination visits.",
                properties={
                    "has_side_effects": {
                        "type": "boolean",
                        "description": "True if the patient reports any side effects"
                    },
                    "details": {
                        "type": "string",
                        "description": "Description of the side effects (empty string if none)"
                    }
                },
                required=["has_side_effects", "details"]
            ),
            FunctionSchema(
                name="record_satisfaction",
                description="Record the patient's satisfaction rating on a scale of 1-10. Call this after asking for their rating.",
                properties={
                    "rating": {
                        "type": "integer",
                        "description": "Satisfaction rating from 1 (very dissatisfied) to 10 (very satisfied)"
                    }
                },
                required=["rating"]
            ),
            FunctionSchema(
                name="end_call",
                description="End the call after thanking the patient. Call this when the conversation is complete or needs to end early.",
                properties={
                    "reason": {
                        "type": "string",
                        "description": "Reason for ending the call (e.g., 'complete', 'wrong_person', 'declined', 'max_retries')"
                    }
                },
                required=["reason"]
            )
        ]

        return ToolsSchema(standard_tools=function_schemas)

    def register_with_llm(self, llm_service: Any) -> None:
        """
        Register all function handlers with the LLM service.

        Args:
            llm_service: OpenAIRealtimeLLMService instance
        """
        llm_service.register_function("confirm_guardian", self._handle_confirm_guardian)
        llm_service.register_function("confirm_visit", self._handle_confirm_visit)
        llm_service.register_function("confirm_service", self._handle_confirm_service)
        llm_service.register_function("record_side_effects", self._handle_record_side_effects)
        llm_service.register_function("record_satisfaction", self._handle_record_satisfaction)
        llm_service.register_function("end_call", self._handle_end_call)

        logger.info("Registered all 6 conversation functions with LLM service")

    # =========================================================================
    # Stage 1: Confirm Guardian Handler
    # =========================================================================
    async def _handle_confirm_guardian(self, params: FunctionCallParams) -> None:
        """
        Handle guardian confirmation.

        On success: Update state, result_callback triggers LLM to continue to visit confirmation
        On failure (2 retries): End call gracefully
        """
        confirmed = params.arguments.get("confirmed", False)
        retry_count = self.flow_manager.state.get("guardian_retry_count", 0)

        logger.info(f"confirm_guardian called: confirmed={confirmed}, retry_count={retry_count}")

        # Store in conversation state
        self.flow_manager.state["guardian_confirmed"] = confirmed

        if confirmed:
            # Guardian confirmed - update state for next stage
            self.flow_manager.state["current_stage"] = "confirm_visit"
            completed_stages = self.flow_manager.state.get("completed_stages", [])
            if "confirm_guardian" not in completed_stages:
                completed_stages.append("confirm_guardian")
            self.flow_manager.state["completed_stages"] = completed_stages

            # Return success - LLM will continue to visit confirmation
            await params.result_callback({
                "status": "confirmed",
                "message": "Guardian identity confirmed. Proceed to visit confirmation.",
                "next_stage": "confirm_visit"
            })
            return

        # Not confirmed - check retry count
        retry_count += 1
        self.flow_manager.state["guardian_retry_count"] = retry_count

        if retry_count >= MAX_RETRIES:
            # Max retries reached - end call gracefully
            logger.info(f"Guardian confirmation failed after {retry_count} retries, ending call")
            self.flow_manager.state["completed"] = True
            self.flow_manager.state["completion_reason"] = "wrong_person_max_retries"

            # Queue goodbye and EndFrame
            if self.task:
                await self.task.queue_frames([
                    TTSSpeakFrame("I apologize for the confusion. Thank you for your time today. Have a wonderful day!"),
                    EndFrame()
                ])

            await params.result_callback({
                "status": "failed",
                "message": "Max retries reached. Call ending.",
                "reason": "wrong_person_max_retries"
            })
            return

        # Still have retries - ask to retry
        await params.result_callback({
            "status": "retry",
            "message": f"Not confirmed. Please verify identity again. Retry {retry_count}/{MAX_RETRIES}.",
            "retries_remaining": MAX_RETRIES - retry_count
        })

    # =========================================================================
    # Stage 2: Confirm Visit Handler
    # =========================================================================
    async def _handle_confirm_visit(self, params: FunctionCallParams) -> None:
        """
        Handle visit confirmation.

        On success/failure: Update state, proceed to service confirmation.
        """
        confirmed = params.arguments.get("confirmed", False)
        retry_count = self.flow_manager.state.get("visit_retry_count", 0)

        logger.info(f"confirm_visit called: confirmed={confirmed}, retry_count={retry_count}")

        # Store in conversation state
        self.flow_manager.state["visit_confirmed"] = confirmed
        self.flow_manager.state["current_stage"] = "confirm_service"

        completed_stages = self.flow_manager.state.get("completed_stages", [])
        if "confirm_visit" not in completed_stages:
            completed_stages.append("confirm_visit")
        self.flow_manager.state["completed_stages"] = completed_stages

        if not confirmed:
            retry_count += 1
            self.flow_manager.state["visit_retry_count"] = retry_count
            if retry_count >= MAX_RETRIES:
                self.flow_manager.state["visit_discrepancy"] = True
                logger.info("Visit not confirmed after max retries, proceeding with discrepancy noted")

        # Always proceed to service confirmation
        await params.result_callback({
            "status": "confirmed" if confirmed else "not_confirmed",
            "message": "Visit confirmation recorded. Proceed to service confirmation.",
            "next_stage": "confirm_service",
            "discrepancy_noted": self.flow_manager.state.get("visit_discrepancy", False)
        })

    # =========================================================================
    # Stage 3: Confirm Service Handler
    # =========================================================================
    async def _handle_confirm_service(self, params: FunctionCallParams) -> None:
        """
        Handle service confirmation.

        Determines next stage based on whether this is a vaccination event.
        """
        confirmed = params.arguments.get("confirmed", False)

        logger.info(f"confirm_service called: confirmed={confirmed}")

        # Store in conversation state
        self.flow_manager.state["service_confirmed"] = confirmed

        completed_stages = self.flow_manager.state.get("completed_stages", [])
        if "confirm_service" not in completed_stages:
            completed_stages.append("confirm_service")
        self.flow_manager.state["completed_stages"] = completed_stages

        # Check if this is a vaccination event (requires side effects check)
        event_info = self.flow_manager.state.get("event_info", {})
        is_vaccination = (
            event_info.get("event_type") in ["vaccination", "immunization"] or
            event_info.get("vaccine_name") is not None or
            event_info.get("is_vaccination", False)
        )

        # Determine next stage
        next_stage = "record_side_effects" if is_vaccination else "record_satisfaction"
        self.flow_manager.state["current_stage"] = next_stage

        if not confirmed:
            self.flow_manager.state["service_not_confirmed_followup"] = True
            logger.info("Service not confirmed, marked for follow-up")

        await params.result_callback({
            "status": "confirmed" if confirmed else "not_confirmed",
            "message": f"Service confirmation recorded. Proceed to {next_stage}.",
            "next_stage": next_stage,
            "is_vaccination": is_vaccination
        })

    # =========================================================================
    # Stage 4: Record Side Effects Handler (vaccination only)
    # =========================================================================
    async def _handle_record_side_effects(self, params: FunctionCallParams) -> None:
        """
        Handle side effects recording for vaccination visits.

        Checks for severe symptoms and flags for follow-up if needed.
        """
        has_side_effects = params.arguments.get("has_side_effects", False)
        details = params.arguments.get("details", "")

        logger.info(f"record_side_effects called: has_side_effects={has_side_effects}, details={details[:50] if details else 'none'}")

        # Store in conversation state
        self.flow_manager.state["has_side_effects"] = has_side_effects
        self.flow_manager.state["side_effects_details"] = details
        self.flow_manager.state["current_stage"] = "record_satisfaction"

        completed_stages = self.flow_manager.state.get("completed_stages", [])
        if "record_side_effects" not in completed_stages:
            completed_stages.append("record_side_effects")
        self.flow_manager.state["completed_stages"] = completed_stages

        # Check for severe side effects
        severe_keywords = ["high fever", "difficulty breathing", "allergic", "severe", "emergency", "hospital", "swelling", "rash"]
        is_severe = any(keyword in details.lower() for keyword in severe_keywords) if details else False

        if is_severe:
            self.flow_manager.state["severe_side_effects"] = True
            self.flow_manager.state["urgency_flagged"] = True
            logger.warning(f"Severe side effects detected: {details}")

        await params.result_callback({
            "status": "recorded",
            "message": "Side effects recorded. Proceed to satisfaction rating.",
            "next_stage": "record_satisfaction",
            "severe": is_severe
        })

    # =========================================================================
    # Stage 5: Record Satisfaction Handler
    # =========================================================================
    async def _handle_record_satisfaction(self, params: FunctionCallParams) -> None:
        """
        Handle satisfaction rating recording.

        Validates rating is 1-10 and flags low ratings for follow-up.
        """
        rating = params.arguments.get("rating", 5)

        logger.info(f"record_satisfaction called: rating={rating}")

        # Validate rating is in range 1-10
        rating = max(1, min(10, rating))

        # Store in conversation state
        self.flow_manager.state["satisfaction_rating"] = rating
        self.flow_manager.state["current_stage"] = "end_call"

        completed_stages = self.flow_manager.state.get("completed_stages", [])
        if "record_satisfaction" not in completed_stages:
            completed_stages.append("record_satisfaction")
        self.flow_manager.state["completed_stages"] = completed_stages

        # Note low satisfaction for follow-up
        if rating <= 3:
            self.flow_manager.state["low_satisfaction_followup"] = True
            logger.info(f"Low satisfaction rating ({rating}), marked for follow-up")

        await params.result_callback({
            "status": "recorded",
            "message": "Satisfaction rating recorded. Proceed to end the call.",
            "next_stage": "end_call",
            "rating": rating,
            "needs_followup": rating <= 3
        })

    # =========================================================================
    # Stage 6: End Call Handler
    # =========================================================================
    async def _handle_end_call(self, params: FunctionCallParams) -> None:
        """
        Handle call termination.

        Queues goodbye message via TTSSpeakFrame and EndFrame to disconnect.
        """
        reason = params.arguments.get("reason", "complete")

        logger.info(f"end_call called: reason={reason}")

        # Mark conversation as completed
        self.flow_manager.state["completed"] = True
        self.flow_manager.state["completion_reason"] = reason
        self.flow_manager.state["current_stage"] = "completed"

        completed_stages = self.flow_manager.state.get("completed_stages", [])
        if "end_call" not in completed_stages:
            completed_stages.append("end_call")
        self.flow_manager.state["completed_stages"] = completed_stages

        # Build appropriate goodbye message based on state
        goodbye_parts = ["Thank you so much for taking the time to speak with us today."]

        if self.flow_manager.state.get("service_not_confirmed_followup"):
            goodbye_parts.append("Someone from our team will follow up with you soon.")

        if self.flow_manager.state.get("severe_side_effects"):
            goodbye_parts.append("A healthcare professional will contact you soon regarding the side effects you mentioned.")

        if self.flow_manager.state.get("low_satisfaction_followup"):
            goodbye_parts.append("We appreciate your honest feedback and will work to improve.")

        goodbye_parts.append("Take care and have a wonderful day!")
        goodbye_message = " ".join(goodbye_parts)

        # Queue goodbye message and EndFrame to terminate call
        if self.task:
            logger.info("Queuing goodbye message and EndFrame to disconnect call")
            await self.task.queue_frames([
                TTSSpeakFrame(goodbye_message),
                EndFrame()
            ])
        else:
            logger.warning("No task available to queue EndFrame - call may not disconnect properly")

        # Return result (triggers LLM acknowledgment before disconnect)
        await params.result_callback({
            "status": "ended",
            "message": "Call ending. Goodbye message queued.",
            "reason": reason
        })
