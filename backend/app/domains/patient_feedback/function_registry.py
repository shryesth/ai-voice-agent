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
        On failure (2 retries): Signal LLM to say goodbye, system ends call
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

            # Return success with clear guidance - LLM will continue to visit confirmation
            await params.result_callback({
                "success": True,
                "message": "Guardian confirmed. Now ask about the visit to the facility."
            })
            return

        # Not confirmed - check retry count
        retry_count += 1
        self.flow_manager.state["guardian_retry_count"] = retry_count

        if retry_count >= MAX_RETRIES:
            # Max retries reached - signal LLM to say goodbye
            logger.info(f"Guardian confirmation failed after {retry_count} retries, signaling goodbye")
            self.flow_manager.state["completed"] = True
            self.flow_manager.state["completion_reason"] = "wrong_person_max_retries"

            # Queue goodbye and EndFrame
            if self.task:
                await self.task.queue_frames([
                    TTSSpeakFrame("I apologize for the confusion. Thank you for your time today. Have a wonderful day!"),
                    EndFrame()
                ])

            # Tell LLM to say goodbye - system will end call automatically
            await params.result_callback({
                "success": False,
                "should_say_goodbye": True,
                "message": "Wrong person confirmed. Say a brief goodbye and the call will end automatically. DO NOT call end_call()."
            })
            return

        # Still have retries - ask to retry with clear guidance
        await params.result_callback({
            "success": False,
            "retry": True,
            "message": "Person not confirmed. Ask 'May I know who I'm speaking with?' This is attempt " + str(retry_count) + " of 2."
        })

    # =========================================================================
    # Stage 2: Confirm Visit Handler
    # =========================================================================
    async def _handle_confirm_visit(self, params: FunctionCallParams) -> None:
        """
        Handle visit confirmation.

        On success/failure: Update state, ALWAYS proceed to service confirmation.
        Never get stuck - move forward regardless of confirmation status.
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

        # Always proceed to service confirmation with clear guidance
        if confirmed:
            await params.result_callback({
                "success": True,
                "proceed_to_next_stage": True,
                "next_stage": "confirm_service",
                "message": "Visit confirmed. Now ask about the specific service received."
            })
        else:
            await params.result_callback({
                "success": False,
                "proceed_to_next_stage": True,
                "next_stage": "confirm_service",
                "message": "Visit could not be confirmed. IMMEDIATELY proceed to ask about the service. DO NOT ask about the visit again."
            })

    # =========================================================================
    # Stage 3: Confirm Service Handler
    # =========================================================================
    async def _handle_confirm_service(self, params: FunctionCallParams) -> None:
        """
        Handle service confirmation.

        Determines next stage based on whether this is a vaccination event.
        Always proceeds forward - never gets stuck.
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

        # Provide clear guidance on next step
        if is_vaccination:
            next_instruction = "Now ask about any side effects from the vaccination."
        else:
            next_instruction = "Now ask for their satisfaction rating on a scale of 1 to 10."

        await params.result_callback({
            "success": True if confirmed else False,
            "proceed_to_next_stage": True,
            "next_stage": next_stage,
            "message": f"Service {'confirmed' if confirmed else 'not confirmed (marked for follow-up)'}. {next_instruction}"
        })

    # =========================================================================
    # Stage 4: Record Side Effects Handler (vaccination only)
    # =========================================================================
    async def _handle_record_side_effects(self, params: FunctionCallParams) -> None:
        """
        Handle side effects recording for vaccination visits.

        Checks for severe symptoms and flags for follow-up if needed.
        Always proceeds to satisfaction rating.
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
            "success": True,
            "proceed_to_next_stage": True,
            "next_stage": "record_satisfaction",
            "message": "Side effects recorded. Now ask for their satisfaction rating on a scale of 1 to 10."
        })

    # =========================================================================
    # Stage 5: Record Satisfaction Handler
    # =========================================================================
    async def _handle_record_satisfaction(self, params: FunctionCallParams) -> None:
        """
        Handle satisfaction rating recording.

        Validates rating is 1-10 and flags low ratings for follow-up.
        Always proceeds to end call.
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

        # Prepare result callback
        result = {
            "success": True,
            "proceed_to_next_stage": True,
            "next_stage": "end_call",
            "message": f"Rating of {rating} recorded. Now thank them warmly and call end_call(reason='complete')."
        }

        await params.result_callback(result)

        # FALLBACK: If LLM doesn't call end_call after this, auto-trigger it after brief delay
        # This prevents calls from staying open indefinitely
        import asyncio
        asyncio.create_task(self._auto_end_call_fallback())

    async def _auto_end_call_fallback(self) -> None:
        """
        Automatic fallback to end call if LLM doesn't call end_call function.

        Waits 10 seconds after record_satisfaction, then checks if end_call
        was called. If not, automatically queues goodbye and EndFrame.
        """
        import asyncio

        # Wait 10 seconds to see if LLM calls end_call
        await asyncio.sleep(10)

        # Check if call already ended
        if self.flow_manager.state.get("completed"):
            logger.debug("Call already ended, skipping fallback")
            return

        # Check if end_call was called
        completed_stages = self.flow_manager.state.get("completed_stages", [])
        if "end_call" in completed_stages:
            logger.debug("end_call already called, skipping fallback")
            return

        logger.warning("LLM did not call end_call after record_satisfaction - triggering automatic disconnect")

        # Mark as completed
        self.flow_manager.state["completed"] = True
        self.flow_manager.state["completion_reason"] = "auto_fallback"
        self.flow_manager.state["current_stage"] = "completed"

        completed_stages.append("end_call")
        self.flow_manager.state["completed_stages"] = completed_stages

        # Build goodbye message
        goodbye_parts = []

        # Only add if not already said
        # Check if AI already said goodbye by looking at recent transcript
        # (We don't want to say goodbye twice)
        # Just queue EndFrame to disconnect

        if self.task:
            logger.info("Auto-fallback: Queuing EndFrame to disconnect call")
            await self.task.queue_frames([
                EndFrame()
            ])
        else:
            logger.error("No task available for auto-fallback EndFrame")

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
        await params.result_callback({"success": True, "call_ended": True})
