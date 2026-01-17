"""
6-stage conversation flow state machine for patient feedback calls.

This module implements the conversation flow using pipecat-flows FlowManager pattern
with NodeConfig functions for each stage. Based on Pipecat v0.0.99 architecture.

Stages:
1. Greeting - Initial welcome and audio check
2. Language Selection - Choose preferred language (en, es, fr, ht)
3. Patient Verification - Confirm caller is patient/guardian/authorized helper
4. Feedback Collection - Structured feedback questions (satisfaction, concerns, side effects)
5. Urgency Detection - Scan for keywords indicating medical emergencies
6. Call Completion - Thank caller and end conversation
"""

from backend.app.domains.patient_feedback.flow_manager import (
    FlowArgs, FlowManager, FlowResult, NodeConfig, FlowsFunctionSchema
)
from pydantic import BaseModel
from typing import List


# FlowResult base classes for typed returns
class GreetingResult(FlowResult):
    """Result from greeting stage"""
    acknowledged: bool


class LanguageResult(FlowResult):
    """Result from language selection stage"""
    language: str


class VerificationResult(FlowResult):
    """Result from patient verification stage"""
    verified: bool
    is_patient: bool


class FeedbackResult(FlowResult):
    """Result from feedback collection stage"""
    satisfaction_rating: int
    specific_concerns: str
    side_effects: str
    experience_quality: str


class UrgencyResult(FlowResult):
    """Result from urgency detection stage"""
    flagged: bool
    keywords: List[str]


class CompletionResult(FlowResult):
    """Result from call completion stage"""
    reason: str


# Stage 1: Greeting Node
def create_greeting_node() -> NodeConfig:
    """Create greeting node for conversation flow"""
    async def greeting_handler(args: FlowArgs, flow_manager: FlowManager):
        acknowledged = args.get("acknowledged", False)
        flow_manager.state["greeted"] = acknowledged
        return GreetingResult(acknowledged=acknowledged), create_language_selection_node()

    return NodeConfig(
        name="greeting",
        role_messages=[
            {"role": "system", "content": "You are a friendly healthcare assistant conducting a patient feedback call."}
        ],
        task_messages=[
            {"role": "system", "content": "Greet the patient warmly and ask if they can hear you clearly. Wait for positive acknowledgment before proceeding."}
        ],
        functions=[
            FlowsFunctionSchema(
                name="acknowledge_greeting",
                description="Patient has acknowledged the greeting and can hear clearly",
                properties={
                    "acknowledged": {
                        "type": "boolean",
                        "description": "Whether patient responded positively to greeting"
                    }
                },
                required=["acknowledged"],
                handler=greeting_handler
            )
        ]
    )


# Stage 2: Language Selection Node
def create_language_selection_node() -> NodeConfig:
    """Create language selection node"""
    async def language_handler(args: FlowArgs, flow_manager: FlowManager):
        language = args.get("language", "en")
        flow_manager.state["language"] = language
        return LanguageResult(language=language), create_verification_node()

    return NodeConfig(
        name="language_selection",
        role_messages=[
            {"role": "system", "content": "You are a multilingual healthcare assistant conducting a patient feedback call."}
        ],
        task_messages=[
            {"role": "system", "content": "Ask the patient which language they prefer for this call: English, Spanish, French, or Haitian Creole. Wait for their selection."}
        ],
        functions=[
            FlowsFunctionSchema(
                name="select_language",
                description="Patient has selected their preferred language for the conversation",
                properties={
                    "language": {
                        "type": "string",
                        "enum": ["en", "es", "fr", "ht"],
                        "description": "Language code: en=English, es=Spanish, fr=French, ht=Haitian Creole"
                    }
                },
                required=["language"],
                handler=language_handler
            )
        ]
    )


# Stage 3: Patient Verification Node
def create_verification_node() -> NodeConfig:
    """Create patient verification node"""
    async def verify_handler(args: FlowArgs, flow_manager: FlowManager):
        is_patient = args.get("is_appropriate_person", False)

        if not is_patient:
            flow_manager.state["wrong_person"] = True
            return VerificationResult(verified=False, is_patient=False), create_completion_node("wrong_person")

        flow_manager.state["verified"] = True
        return VerificationResult(verified=True, is_patient=True), create_feedback_node()

    return NodeConfig(
        name="patient_verification",
        role_messages=[
            {"role": "system", "content": "You are a healthcare assistant verifying patient identity for a feedback call."}
        ],
        task_messages=[
            {"role": "system", "content": "Confirm whether the person on the call is the patient themselves, or an authorized representative (guardian, family member, or authorized helper). If they are NOT authorized to provide feedback, politely explain and end the call."}
        ],
        functions=[
            FlowsFunctionSchema(
                name="verify_patient_identity",
                description="Caller has confirmed whether they are authorized to provide patient feedback",
                properties={
                    "is_appropriate_person": {
                        "type": "boolean",
                        "description": "True if caller is the patient, guardian, or authorized representative. False if wrong person."
                    }
                },
                required=["is_appropriate_person"],
                handler=verify_handler
            )
        ]
    )


# Stage 4: Feedback Collection Node
def create_feedback_node() -> NodeConfig:
    """Create feedback collection node"""
    async def feedback_handler(args: FlowArgs, flow_manager: FlowManager):
        # Store structured feedback
        flow_manager.state["feedback"] = {
            "satisfaction": args.get("satisfaction_rating"),
            "concerns": args.get("specific_concerns", ""),
            "side_effects": args.get("side_effects", ""),
            "experience": args.get("experience_quality", "")
        }

        # Proceed to urgency detection
        return FeedbackResult(
            satisfaction_rating=args.get("satisfaction_rating"),
            specific_concerns=args.get("specific_concerns", ""),
            side_effects=args.get("side_effects", ""),
            experience_quality=args.get("experience_quality", "")
        ), create_urgency_detection_node()

    return NodeConfig(
        name="feedback_collection",
        role_messages=[
            {"role": "system", "content": "You are a compassionate healthcare assistant collecting patient feedback."}
        ],
        task_messages=[
            {"role": "system", "content": "Ask the patient: (1) On a scale of 1-10, how satisfied are they with their care? (2) Do they have any specific concerns? (3) Are they experiencing any side effects? (4) How would they describe their overall experience? Listen carefully and record their responses."}
        ],
        functions=[
            FlowsFunctionSchema(
                name="record_feedback",
                description="Patient has provided complete feedback responses",
                properties={
                    "satisfaction_rating": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 10,
                        "description": "Satisfaction rating from 1 (very dissatisfied) to 10 (very satisfied)"
                    },
                    "specific_concerns": {
                        "type": "string",
                        "description": "Any specific concerns the patient mentioned (empty string if none)"
                    },
                    "side_effects": {
                        "type": "string",
                        "description": "Any side effects the patient reported (empty string if none)"
                    },
                    "experience_quality": {
                        "type": "string",
                        "description": "Patient's description of their overall experience"
                    }
                },
                required=["satisfaction_rating", "specific_concerns", "side_effects", "experience_quality"],
                handler=feedback_handler
            )
        ]
    )


# Stage 5: Urgency Detection Node
def create_urgency_detection_node() -> NodeConfig:
    """Create urgency detection node"""
    async def urgency_handler(args: FlowArgs, flow_manager: FlowManager):
        urgency_keywords_found = args.get("urgent_keywords", [])

        if urgency_keywords_found:
            flow_manager.state["urgency_flagged"] = True
            flow_manager.state["urgency_keywords"] = urgency_keywords_found

        return UrgencyResult(flagged=bool(urgency_keywords_found), keywords=urgency_keywords_found), create_completion_node("success")

    return NodeConfig(
        name="urgency_detection",
        role_messages=[
            {"role": "system", "content": "You are a healthcare assistant trained to identify urgent medical concerns from patient responses."}
        ],
        task_messages=[
            {"role": "system", "content": "Review the patient's feedback carefully. Ask if there is anything urgent they need help with immediately. Listen for keywords indicating emergencies: 'hospital', 'severe pain', 'can't breathe', 'emergency', 'ambulance', 'bleeding', 'chest pain', 'dizzy', 'fainted'. If detected, acknowledge urgently and escalate."}
        ],
        functions=[
            FlowsFunctionSchema(
                name="detect_urgency",
                description="Urgency assessment complete - flag any urgent keywords found in patient's responses",
                properties={
                    "urgent_keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of urgent keywords detected (e.g., 'hospital', 'severe', 'emergency'). Empty array if none found."
                    }
                },
                required=["urgent_keywords"],
                handler=urgency_handler
            )
        ]
    )


# Stage 6: Call Completion Node
def create_completion_node(reason: str) -> NodeConfig:
    """Create call completion node"""
    async def completion_handler(args: FlowArgs, flow_manager: FlowManager):
        flow_manager.state["completed"] = True
        flow_manager.state["completion_reason"] = reason
        return CompletionResult(reason=reason), None  # No next node - conversation ends

    # Customize goodbye message based on reason
    goodbye_messages = {
        "success": "Thank you for your time and valuable feedback. We've recorded your responses and will follow up if needed. Goodbye!",
        "wrong_person": "Thank you for your time. Since you're not the patient or authorized representative, we'll contact the patient directly. Goodbye!",
        "error": "We've encountered a technical issue. We'll try calling again later. Thank you for your patience. Goodbye!"
    }

    return NodeConfig(
        name="call_completion",
        role_messages=[
            {"role": "system", "content": "You are a polite healthcare assistant concluding a patient feedback call."}
        ],
        task_messages=[
            {"role": "system", "content": f"{goodbye_messages.get(reason, goodbye_messages['success'])} Say goodbye warmly and end the call."}
        ],
        functions=[
            FlowsFunctionSchema(
                name="end_call",
                description="Call has been concluded and goodbye message delivered",
                properties={
                    "acknowledged": {
                        "type": "boolean",
                        "description": "Always true when call is ending"
                    }
                },
                required=["acknowledged"],
                handler=completion_handler
            )
        ]
    )
