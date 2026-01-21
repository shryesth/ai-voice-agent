"""
7-stage conversation flow for supervisor calls (Ministry of Health verification).

This module implements the conversation flow using Pipecat FlowManager pattern
with NodeConfig functions for each stage. Based on Pipecat v0.0.99 architecture.

Stages:
1. Greeting - Warmly greet and confirm speaking with correct person
2. Introduction - Explain purpose and ask for a few minutes
3. Confirm Visit - Verify visited specific facility on date
4. Confirm Service - Verify exact service received
5. Side Effects - Ask about side effects (vaccination only)
6. Satisfaction Rating - Collect 1-10 rating and concerns
7. Closing - Thank and end call professionally
"""

from pipecat_flows import (
    FlowArgs,
    FlowManager,
    FlowResult,
    NodeConfig,
    FlowsFunctionSchema,
)
from typing import List, Optional
from pipecat.frames.frames import EndFrame, TTSSpeakFrame


# FlowResult base classes for typed returns
class GreetingResult(FlowResult):
    """Result from greeting stage"""
    person_confirmed: bool


class IntroductionResult(FlowResult):
    """Result from introduction stage"""
    time_given: bool


class VisitConfirmationResult(FlowResult):
    """Result from visit confirmation stage"""
    visit_confirmed: bool
    discrepancy_noted: bool


class ServiceConfirmationResult(FlowResult):
    """Result from service confirmation stage"""
    service_confirmed: bool


class SideEffectsResult(FlowResult):
    """Result from side effects stage"""
    has_side_effects: bool
    details: str
    severe: bool


class SatisfactionResult(FlowResult):
    """Result from satisfaction stage"""
    rating: int
    feedback: str


class ClosingResult(FlowResult):
    """Result from closing stage"""
    reason: str


# ============================================================================
# Stage 1: Greeting Node
# ============================================================================

def create_greeting_node() -> NodeConfig:
    """
    Initial greeting and person confirmation.
    
    Goal: Greet warmly and confirm speaking with the correct person.
    """
    
    async def greeting_handler(args: FlowArgs, flow_manager: FlowManager):
        person_confirmed = args.get("person_confirmed", False)
        
        if not person_confirmed:
            flow_manager.state["wrong_person"] = True
            flow_manager.state["completed"] = True
            flow_manager.state["completion_reason"] = "wrong_person"
            
            # End call immediately for wrong person
            if flow_manager.task:
                goodbye_message = "I apologize for the confusion. I'll end this call now. Thank you."
                await flow_manager.task.queue_frames([
                    TTSSpeakFrame(goodbye_message),
                    EndFrame()
                ])
            
            return GreetingResult(person_confirmed=False), None  # No next node
        
        flow_manager.state["person_confirmed"] = True
        flow_manager.state["completed_stages"].append("greeting")
        flow_manager.state["current_stage"] = "introduction"
        
        return GreetingResult(person_confirmed=True), create_introduction_node()
    
    return NodeConfig(
        name="greeting",
        role_messages=[
            {"role": "system", "content": "You are a friendly and professional assistant calling on behalf of the Ministry of Health."}
        ],
        task_messages=[
            {"role": "system", "content": "Greet the person warmly. Ask if you are speaking with the correct person by name. If they confirm, proceed to introduction. If they say you have the wrong person, politely apologize and end the call."}
        ],
        functions=[
            FlowsFunctionSchema(
                name="confirm_person",
                description="The person has confirmed whether they are the correct person",
                properties={
                    "person_confirmed": {
                        "type": "boolean",
                        "description": "True if speaking with correct person, False if wrong person"
                    }
                },
                required=["person_confirmed"],
                handler=greeting_handler
            )
        ]
    )


# ============================================================================
# Stage 2: Introduction Node
# ============================================================================

def create_introduction_node() -> NodeConfig:
    """
    Explain purpose and request time.
    
    Goal: Tell them you're calling from Ministry of Health about a recent health visit
          and ask if they have a few minutes.
    """
    
    async def introduction_handler(args: FlowArgs, flow_manager: FlowManager):
        time_given = args.get("time_given", False)
        
        if not time_given:
            flow_manager.state["declined_call"] = True
            flow_manager.state["completed"] = True
            flow_manager.state["completion_reason"] = "declined"
            
            # End call politely
            if flow_manager.task:
                goodbye_message = "I understand. Thank you for your time. Have a great day!"
                await flow_manager.task.queue_frames([
                    TTSSpeakFrame(goodbye_message),
                    EndFrame()
                ])
            
            return IntroductionResult(time_given=False), None  # No next node
        
        flow_manager.state["time_given"] = True
        flow_manager.state["completed_stages"].append("introduction")
        flow_manager.state["current_stage"] = "confirm_visit"
        
        return IntroductionResult(time_given=True), create_confirm_visit_node()
    
    return NodeConfig(
        name="introduction",
        role_messages=[
            {"role": "system", "content": "You are representing the Ministry of Health for a health visit verification call."}
        ],
        task_messages=[
            {"role": "system", "content": "Explain that you're calling from the Ministry of Health about a recent health visit. Ask if they have a few minutes to answer some questions. If they decline, thank them politely and end the call."}
        ],
        functions=[
            FlowsFunctionSchema(
                name="confirm_availability",
                description="The person has indicated whether they have time to talk",
                properties={
                    "time_given": {
                        "type": "boolean",
                        "description": "True if they agree to talk, False if they decline"
                    }
                },
                required=["time_given"],
                handler=introduction_handler
            )
        ]
    )


# ============================================================================
# Stage 3: Confirm Visit Node
# ============================================================================

def create_confirm_visit_node() -> NodeConfig:
    """
    Verify the health facility visit.
    
    Goal: Ask if they visited the specific health facility on the date mentioned.
    """
    
    async def visit_handler(args: FlowArgs, flow_manager: FlowManager):
        visit_confirmed = args.get("visit_confirmed", False)
        discrepancy_noted = args.get("discrepancy_noted", False)
        
        flow_manager.state["visit_confirmed"] = visit_confirmed
        flow_manager.state["visit_discrepancy"] = discrepancy_noted
        flow_manager.state["completed_stages"].append("confirm_visit")
        flow_manager.state["current_stage"] = "confirm_service"
        
        # If discrepancy, flag for follow-up but continue
        if discrepancy_noted:
            flow_manager.state["human_callback_requested"] = True
        
        return VisitConfirmationResult(
            visit_confirmed=visit_confirmed,
            discrepancy_noted=discrepancy_noted
        ), create_confirm_service_node()
    
    return NodeConfig(
        name="confirm_visit",
        role_messages=[
            {"role": "system", "content": "You are verifying a health facility visit for the Ministry of Health."}
        ],
        task_messages=[
            {"role": "system", "content": "Ask if they visited the specific health facility on the date mentioned. If they confirm, proceed. If they say the information is wrong, note the discrepancy and politely move forward without pushing."}
        ],
        functions=[
            FlowsFunctionSchema(
                name="record_visit_response",
                description="The person has responded about the health facility visit",
                properties={
                    "visit_confirmed": {
                        "type": "boolean",
                        "description": "True if they confirm the visit, False if they deny or don't remember"
                    },
                    "discrepancy_noted": {
                        "type": "boolean",
                        "description": "True if there's a discrepancy in the information"
                    }
                },
                required=["visit_confirmed", "discrepancy_noted"],
                handler=visit_handler
            )
        ]
    )


# ============================================================================
# Stage 4: Confirm Service Node
# ============================================================================

def create_confirm_service_node() -> NodeConfig:
    """
    Verify the specific service received.
    
    Goal: Ask the confirmation question specific to their visit type to verify
          the exact service they received.
    """
    
    async def service_handler(args: FlowArgs, flow_manager: FlowManager):
        service_confirmed = args.get("service_confirmed", False)
        
        flow_manager.state["service_confirmed"] = service_confirmed
        flow_manager.state["completed_stages"].append("confirm_service")
        
        # Check if side effects stage is needed (vaccination visits)
        requires_side_effects = flow_manager.state.get("requires_side_effects", False)
        
        if requires_side_effects:
            flow_manager.state["current_stage"] = "side_effects"
            next_node = create_side_effects_node()
        else:
            flow_manager.state["current_stage"] = "satisfaction"
            next_node = create_satisfaction_node()
        
        # If service not confirmed, flag for follow-up
        if not service_confirmed:
            flow_manager.state["service_not_confirmed_followup"] = True
        
        return ServiceConfirmationResult(service_confirmed=service_confirmed), next_node
    
    return NodeConfig(
        name="confirm_service",
        role_messages=[
            {"role": "system", "content": "You are confirming the specific health service received."}
        ],
        task_messages=[
            {"role": "system", "content": "Ask the specific confirmation question for their visit type to verify the exact service they received. Record their response accurately."}
        ],
        functions=[
            FlowsFunctionSchema(
                name="record_service_response",
                description="The person has confirmed whether they received the specific service",
                properties={
                    "service_confirmed": {
                        "type": "boolean",
                        "description": "True if they confirm receiving the service, False otherwise"
                    }
                },
                required=["service_confirmed"],
                handler=service_handler
            )
        ]
    )


# ============================================================================
# Stage 5: Side Effects Node (Optional)
# ============================================================================

def create_side_effects_node() -> NodeConfig:
    """
    Ask about side effects (vaccination visits only).
    
    Goal: Ask if they experienced any side effects and record details.
          Flag severe symptoms as urgent.
    """
    
    async def side_effects_handler(args: FlowArgs, flow_manager: FlowManager):
        has_side_effects = args.get("has_side_effects", False)
        details = args.get("details", "")
        severe = args.get("severe", False)
        
        flow_manager.state["has_side_effects"] = has_side_effects
        flow_manager.state["side_effects_details"] = details
        flow_manager.state["severe_side_effects"] = severe
        flow_manager.state["completed_stages"].append("side_effects")
        flow_manager.state["current_stage"] = "satisfaction"
        
        # Flag severe side effects as urgent
        if severe:
            flow_manager.state["urgency_flagged"] = True
        
        return SideEffectsResult(
            has_side_effects=has_side_effects,
            details=details,
            severe=severe
        ), create_satisfaction_node()
    
    return NodeConfig(
        name="side_effects",
        role_messages=[
            {"role": "system", "content": "You are collecting information about side effects from a vaccination."}
        ],
        task_messages=[
            {"role": "system", "content": "Ask if they experienced any side effects from the vaccination. If yes, ask them to describe the symptoms. Note if symptoms sound severe (e.g., difficulty breathing, severe allergic reaction, high fever). If severe, recommend they contact their healthcare provider immediately."}
        ],
        functions=[
            FlowsFunctionSchema(
                name="record_side_effects",
                description="The person has responded about side effects",
                properties={
                    "has_side_effects": {
                        "type": "boolean",
                        "description": "True if they experienced side effects, False if none"
                    },
                    "details": {
                        "type": "string",
                        "description": "Description of side effects if any, empty string if none"
                    },
                    "severe": {
                        "type": "boolean",
                        "description": "True if symptoms sound severe and require urgent medical attention"
                    }
                },
                required=["has_side_effects", "details", "severe"],
                handler=side_effects_handler
            )
        ]
    )


# ============================================================================
# Stage 6: Satisfaction Rating Node
# ============================================================================

def create_satisfaction_node() -> NodeConfig:
    """
    Collect satisfaction rating and feedback.
    
    Goal: Ask for a rating from 1 to 10 and any specific concerns or feedback.
    """
    
    async def satisfaction_handler(args: FlowArgs, flow_manager: FlowManager):
        rating = args.get("rating", 5)
        feedback = args.get("feedback", "")
        
        flow_manager.state["satisfaction_rating"] = rating
        flow_manager.state["satisfaction_feedback"] = feedback
        flow_manager.state["completed_stages"].append("satisfaction")
        flow_manager.state["current_stage"] = "closing"
        
        # Flag low satisfaction for follow-up
        if rating < 5:
            flow_manager.state["low_satisfaction_followup"] = True
        
        return SatisfactionResult(rating=rating, feedback=feedback), create_closing_node()
    
    return NodeConfig(
        name="satisfaction",
        role_messages=[
            {"role": "system", "content": "You are collecting patient satisfaction feedback for the Ministry of Health."}
        ],
        task_messages=[
            {"role": "system", "content": "Ask them to rate their experience from 1 to 10, where 1 is very poor and 10 is excellent. Then ask if they have any specific concerns or feedback they'd like to share."}
        ],
        functions=[
            FlowsFunctionSchema(
                name="record_satisfaction",
                description="The person has provided their satisfaction rating and feedback",
                properties={
                    "rating": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 10,
                        "description": "Satisfaction rating from 1 (very poor) to 10 (excellent)"
                    },
                    "feedback": {
                        "type": "string",
                        "description": "Any specific concerns or feedback, empty string if none"
                    }
                },
                required=["rating", "feedback"],
                handler=satisfaction_handler
            )
        ]
    )


# ============================================================================
# Stage 7: Closing Node
# ============================================================================

def create_closing_node() -> NodeConfig:
    """
    Thank the caller and end the conversation professionally.
    
    Goal: Express gratitude, wish them good health, and end the call.
    """
    
    async def closing_handler(args: FlowArgs, flow_manager: FlowManager):
        reason = args.get("reason", "complete")
        
        flow_manager.state["completed"] = True
        flow_manager.state["completion_reason"] = reason
        flow_manager.state["completed_stages"].append("closing")
        
        # Build personalized goodbye message
        goodbye_parts = ["Thank you very much for your time and valuable feedback."]
        
        if flow_manager.state.get("human_callback_requested"):
            goodbye_parts.append("Someone from our team will follow up with you soon.")
        
        if flow_manager.state.get("severe_side_effects"):
            goodbye_parts.append("Please contact your healthcare provider if your symptoms worsen.")
        
        if flow_manager.state.get("low_satisfaction_followup"):
            goodbye_parts.append("We appreciate your honest feedback and will work to improve.")
        
        goodbye_parts.append("Wishing you good health. Have a wonderful day!")
        goodbye_message = " ".join(goodbye_parts)
        
        # Queue goodbye message and EndFrame to terminate call
        if flow_manager.task:
            await flow_manager.task.queue_frames([
                TTSSpeakFrame(goodbye_message),
                EndFrame()
            ])
        
        return ClosingResult(reason=reason), None  # No next node - conversation ends
    
    return NodeConfig(
        name="closing",
        role_messages=[
            {"role": "system", "content": "You are concluding a patient feedback call for the Ministry of Health."}
        ],
        task_messages=[
            {"role": "system", "content": "Thank the person for their time, wish them good health, and end the call professionally. Make sure they know their feedback is valued."}
        ],
        functions=[
            FlowsFunctionSchema(
                name="end_call",
                description="Ready to end the call after thanking the person",
                properties={
                    "reason": {
                        "type": "string",
                        "description": "Reason for ending call (complete, declined, wrong_person, error)"
                    }
                },
                required=["reason"],
                handler=closing_handler
            )
        ]
    )
