"""
Pipecat v0.0.100 voice pipeline implementation for patient feedback calls.

This module creates and runs the complete voice pipeline with:
1. TwilioFrameSerializer - Handles ALL µ-law ↔ PCM audio conversion
2. FastAPIWebsocketTransport - WebSocket communication with Twilio
3. LLMContextAggregatorPair - User/Assistant turn management with VAD strategies
4. OpenAIRealtimeLLMService - gpt-4o-realtime for conversational AI
5. FlowManager - 6-stage conversation state machine

Based on architecture from plan.md (Pipecat v0.0.100 patterns).
"""

import asyncio
import os
from datetime import datetime, timezone
from fastapi import WebSocket
import logging

from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineTask, PipelineParams
from pipecat.frames.frames import LLMRunFrame, EndFrame, TTSSpeakFrame
from pipecat.services.openai.realtime.llm import OpenAIRealtimeLLMService
from pipecat.services.openai.realtime.events import (
    SessionProperties,
    AudioConfiguration,
    AudioInput,
    InputAudioTranscription,
    TurnDetection,  # Changed from SemanticTurnDetection
    InputAudioNoiseReduction
)
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContext,
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
    LLMAssistantAggregatorParams
)
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketTransport,
    FastAPIWebsocketParams
)
from pipecat.serializers.twilio import TwilioFrameSerializer
# Using OpenAI server-side VAD with transcription-based turn detection
from pipecat.turns.user_turn_strategies import UserTurnStrategies
from pipecat.turns.user_start import TranscriptionUserTurnStartStrategy
from pipecat.turns.user_stop import TranscriptionUserTurnStopStrategy
# pipecat.turns.mute is deprecated in 0.0.100, use pipecat.turns.user_mute
from pipecat.turns.user_mute import (
    MuteUntilFirstBotCompleteUserMuteStrategy,
    FunctionCallUserMuteStrategy
)

from backend.app.domains.patient_feedback.flow_manager import FlowManager
from backend.app.domains.patient_feedback.function_registry import FunctionRegistry
from backend.app.domains.patient_feedback.prompts.prompt_builder import build_prompt_from_call_record
from backend.app.core.config import settings
from backend.app.models.call_record import CallRecord

logger = logging.getLogger(__name__)


# Language-specific voice mapping
LANGUAGE_VOICE_MAP = {
    "en": "alloy",   # English: neutral voice
    "es": "nova",    # Spanish: warm voice
    "fr": "alloy",   # French: neutral voice
    "ht": "echo"     # Haitian Creole: clear voice
}


async def create_voice_pipeline(
    websocket: WebSocket,
    call_record_id: str,
    call_data: dict,
    call_record: CallRecord
) -> dict:
    """
    Creates and runs the complete Pipecat v0.0.99 voice pipeline.

    Architecture:
    1. TwilioFrameSerializer: Handles ALL µ-law ↔ PCM audio conversion
    2. FastAPIWebsocketTransport: WebSocket communication with Twilio
    3. LLMContextAggregatorPair: User/Assistant turn management with VAD strategies
    4. OpenAIRealtimeLLMService: gpt-4o-realtime for conversational AI
    5. FlowManager: 6-stage conversation state machine
    6. Aggregator Event Handlers: Turn-based transcript capture to MongoDB
       (on_user_turn_stopped, on_assistant_turn_stopped)

    Args:
        websocket: FastAPI WebSocket connection from Twilio
        call_record_id: MongoDB ObjectId for CallRecord persistence
        call_data: Dict with call_sid, stream_sid, campaign_id, patient_phone, language
        call_record: CallRecord document for real-time transcript updates

    Returns:
        Final conversation state (dict) for CallRecord persistence
    """

    logger.info(f"Creating voice pipeline for call {call_record_id}")

    # 1. Initialize TwilioFrameSerializer (handles ALL audio conversion)
    serializer = TwilioFrameSerializer(
        stream_sid=call_data["stream_sid"],
        call_sid=call_data["call_sid"],
        account_sid=settings.twilio_account_sid,
        auth_token=settings.twilio_auth_token,
        params=TwilioFrameSerializer.InputParams(
            twilio_sample_rate=8000,  # Twilio µ-law sample rate
            sample_rate=24000,         # OpenAI Realtime API sample rate (updated to 24kHz)
            auto_hang_up=True
        )
    )

    # 2. Initialize Transport with serializer
    transport = FastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            # vad_analyzer removed - using server-side VAD instead
            serializer=serializer  # TwilioFrameSerializer handles µ-law ↔ PCM
        )
    )

    # 3. Initialize OpenAI Realtime LLM Service with language-specific voice
    voice = LANGUAGE_VOICE_MAP.get(call_data.get("language", "en"), "alloy")
    
    # Configure session properties with input audio transcription enabled
    # This is CRITICAL for capturing user messages - OpenAI Realtime needs explicit transcription config
    session_properties = SessionProperties(
        audio=AudioConfiguration(
            input=AudioInput(
                transcription=InputAudioTranscription(),  # Enable transcription for user audio
                turn_detection=TurnDetection(type="server_vad"),  # Use server-side VAD
                noise_reduction=InputAudioNoiseReduction(type="near_field")  # Near-field noise reduction
            )
        )
    )
    
    llm_service = OpenAIRealtimeLLMService(
        api_key=settings.openai_api_key,
        model=settings.openai_realtime_model,
        voice=voice,
        session_properties=session_properties  # REQUIRED for user transcription!
    )

    # 4. Create FlowManager first (for state management)
    flow_manager = FlowManager()

    # 4a. Pass event_info to FlowManager state for side effects branching
    event_info = {}
    if hasattr(call_record, 'event_info') and call_record.event_info:
        event_info = call_record.event_info if isinstance(call_record.event_info, dict) else call_record.event_info.model_dump()
    flow_manager.state["event_info"] = event_info

    # 4b. Create FunctionRegistry with all 6 conversation functions
    function_registry = FunctionRegistry(flow_manager, call_record)

    # 4c. Create LLMContext with system prompt and ALL tools upfront
    # This uses the greeting templates, confirmation messages, and comprehensive prompt
    system_prompt = build_prompt_from_call_record(call_record)
    logger.info(f"Built system prompt for call {call_record_id} with event_info: {call_record.event_info is not None}")

    context = LLMContext(
        messages=[
            {
                "role": "system",
                "content": system_prompt
            }
        ],
        tools=function_registry.get_all_tools()  # ALL 6 functions available from start
    )

    # 5. Create Context Aggregators with user turn/mute strategies
    context_aggregator = LLMContextAggregatorPair(
        context=context,
        user_params=LLMUserAggregatorParams(
            user_turn_strategies=UserTurnStrategies(
                start=[TranscriptionUserTurnStartStrategy()],  # Detect turn start from transcription frames
                stop=[TranscriptionUserTurnStopStrategy()]     # Detect turn end via transcription complete
            ),
            user_mute_strategies=[
                MuteUntilFirstBotCompleteUserMuteStrategy(),  # Wait for bot's first response
                FunctionCallUserMuteStrategy()                # Mute during function execution
            ]
        ),
        assistant_params=LLMAssistantAggregatorParams()
    )

    user_aggregator = context_aggregator.user()
    assistant_aggregator = context_aggregator.assistant()

    # 6. Register aggregator event handlers for transcript capture
    # Following Pipecat 0.0.99 best practices for turn-based transcript capture
    @user_aggregator.event_handler("on_user_turn_stopped")
    async def on_user_turn_stopped(aggregator, strategy, message):
        """Capture user message when they finish speaking"""
        try:
            logger.debug(f"🎤 User turn stopped event fired. Message type: {type(message)}, Content: '{message.content if hasattr(message, 'content') else 'NO CONTENT ATTR'}'")
            
            # message is a UserTurnStoppedMessage with .content and .timestamp
            if hasattr(message, 'content') and message.content and message.content.strip():
                from backend.app.models.call_record import ConversationTurn
                turn = ConversationTurn(
                    speaker="patient",
                    text=message.content.strip(),
                    timestamp=datetime.now(timezone.utc),
                    language=call_data.get("language")
                )
                call_record.transcript.append(turn)
                call_record.updated_at = datetime.now(timezone.utc)
                await call_record.save()
                logger.info(f"📝 [patient]: {message.content[:50]}...")
            else:
                logger.warning(f"⚠️ User turn stopped but content is empty or missing")
        except Exception as e:
            logger.error(f"Error capturing user transcript: {e}", exc_info=True)

    @assistant_aggregator.event_handler("on_assistant_turn_stopped")
    async def on_assistant_turn_stopped(aggregator, message):
        """Capture assistant message when it finishes responding"""
        try:
            logger.debug(f"🤖 Assistant turn stopped event fired. Message type: {type(message)}, Content: '{message.content if hasattr(message, 'content') else 'NO CONTENT ATTR'}'")
            
            # message is an AssistantTurnStoppedMessage with .content and .timestamp
            if hasattr(message, 'content') and message.content and message.content.strip():
                from backend.app.models.call_record import ConversationTurn
                turn = ConversationTurn(
                    speaker="ai",
                    text=message.content.strip(),
                    timestamp=datetime.now(timezone.utc)
                )
                call_record.transcript.append(turn)
                call_record.updated_at = datetime.now(timezone.utc)
                await call_record.save()
                logger.info(f"📝 [ai]: {message.content[:50]}...")
            else:
                logger.warning(f"⚠️ Assistant turn stopped but content is empty or missing")
        except Exception as e:
            logger.error(f"Error capturing assistant transcript: {e}", exc_info=True)

    # 7. Register ALL function handlers with LLM service upfront
    # This ensures all 6 functions are available throughout the conversation
    function_registry.register_with_llm(llm_service)

    # 9. Build Pipeline (order matters!)
    # Note: Transcript capture now handled by aggregator event handlers (on_user_turn_stopped, on_assistant_turn_stopped)
    pipeline = Pipeline([
        transport.input(),        # 1. Twilio audio input (µ-law 8kHz → PCM 16kHz via serializer)
        user_aggregator,          # 2. User turn aggregation (VAD + transcription strategies)
        llm_service,              # 3. OpenAI Realtime processing (with FlowManager functions)
        transport.output(),       # 4. Twilio audio output (PCM 16kHz → µ-law 8kHz via serializer)
        assistant_aggregator      # 5. Assistant turn aggregation (fires transcript event handlers)
    ])

    # 10. Create Pipeline Task
    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=24000,  # OpenAI Realtime API sample rate (updated to 24kHz)
            audio_out_sample_rate=8000,  # Twilio transport expects 8kHz
            enable_metrics=True,
            enable_usage_metrics=True
        )
        # NOTE: allow_interruptions parameter removed in v0.0.99
        # Interruption handling now managed by user_mute_strategies
    )

    # 11. Link task to FlowManager and FunctionRegistry so handlers can queue EndFrame
    flow_manager.task = task
    function_registry.set_task(task)

    # 12. Initialize FlowManager state
    await flow_manager.initialize()

    # 13. Queue initial LLMRunFrame to start conversation
    await task.queue_frame(LLMRunFrame())

    # 14. Run Pipeline with max call duration timeout
    # (blocks until EndFrame received, timeout, or error)
    runner = PipelineRunner()
    max_duration = settings.max_call_duration_seconds

    try:
        logger.info(f"Starting pipeline for call {call_record_id} (max duration: {max_duration}s)")
        async with asyncio.timeout(max_duration):
            await runner.run(task)
        logger.info(f"Pipeline completed for call {call_record_id}")
    except asyncio.TimeoutError:
        logger.warning(f"Call {call_record_id} exceeded max duration ({max_duration}s), terminating gracefully")
        flow_manager.state["completion_reason"] = "max_duration_timeout"
        flow_manager.state["completed"] = True
        # Queue goodbye message and EndFrame to terminate call gracefully
        try:
            await task.queue_frames([
                TTSSpeakFrame("I apologize, but we need to end our call now. Thank you for your time. Goodbye!"),
                EndFrame()
            ])
            # Give a moment for the goodbye to be spoken
            await asyncio.sleep(3)
        except Exception as tts_error:
            logger.error(f"Error queuing timeout goodbye for call {call_record_id}: {tts_error}")
    except Exception as e:
        logger.error(f"Pipeline error for call {call_record_id}: {e}", exc_info=True)
        flow_manager.state["error"] = str(e)
        flow_manager.state["completed"] = False

    # 15. Ensure state has minimum required keys before returning
    if "completed_stages" not in flow_manager.state:
        flow_manager.state["completed_stages"] = []
        logger.warning(f"completed_stages was missing from state for call {call_record_id}, initialized to empty list")

    if "current_stage" not in flow_manager.state:
        flow_manager.state["current_stage"] = None
        logger.warning(f"current_stage was missing from state for call {call_record_id}, initialized to None")

    # 16. Return final conversation state for persistence
    logger.info(f"Voice pipeline returning state for call {call_record_id}: "
                f"current_stage={flow_manager.state.get('current_stage')}, "
                f"completed_stages={flow_manager.state.get('completed_stages')}, "
                f"completed={flow_manager.state.get('completed')}")
    logger.debug(f"Full pipeline state: {flow_manager.state}")
    return flow_manager.state
