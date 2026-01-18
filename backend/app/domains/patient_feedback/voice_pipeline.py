"""
Pipecat v0.0.99 voice pipeline implementation for patient feedback calls.

This module creates and runs the complete voice pipeline with:
1. TwilioFrameSerializer - Handles ALL µ-law ↔ PCM audio conversion
2. FastAPIWebsocketTransport - WebSocket communication with Twilio
3. LLMContextAggregatorPair - User/Assistant turn management with VAD strategies
4. OpenAIRealtimeLLMService - gpt-4o-realtime for conversational AI
5. FlowManager - 6-stage conversation state machine

Based on architecture from plan.md (Pipecat v0.0.99 patterns).
"""

import os
from datetime import datetime
from fastapi import WebSocket
import logging

from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineTask, PipelineParams
from pipecat.frames.frames import LLMRunFrame
from pipecat.services.openai.realtime.llm import OpenAIRealtimeLLMService
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContext,
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
    LLMAssistantAggregatorParams
)
from pipecat.processors.aggregators.llm_context import NOT_GIVEN
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketTransport,
    FastAPIWebsocketParams
)
from pipecat.serializers.twilio import TwilioFrameSerializer
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.turns.user_turn_strategies import UserTurnStrategies
from pipecat.turns.user_start import VADUserTurnStartStrategy
from pipecat.turns.user_stop import TranscriptionUserTurnStopStrategy
from pipecat.turns.mute import (
    MuteUntilFirstBotCompleteUserMuteStrategy,
    FunctionCallUserMuteStrategy
)

from backend.app.domains.patient_feedback.flow_manager import FlowManager
from backend.app.domains.patient_feedback.conversation_flow import create_greeting_node
from backend.app.core.config import settings

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
    call_data: dict
) -> dict:
    """
    Creates and runs the complete Pipecat v0.0.99 voice pipeline.

    Architecture:
    1. TwilioFrameSerializer: Handles ALL µ-law ↔ PCM audio conversion
    2. FastAPIWebsocketTransport: WebSocket communication with Twilio
    3. LLMContextAggregatorPair: User/Assistant turn management with VAD strategies
    4. OpenAIRealtimeLLMService: gpt-4o-realtime for conversational AI
    5. FlowManager: 6-stage conversation state machine

    Args:
        websocket: FastAPI WebSocket connection from Twilio
        call_record_id: MongoDB ObjectId for CallRecord persistence
        call_data: Dict with call_sid, stream_sid, campaign_id, patient_phone, language

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
            sample_rate=16000,         # OpenAI Realtime API sample rate
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
            vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=0.2)),
            serializer=serializer  # TwilioFrameSerializer handles µ-law ↔ PCM
        )
    )

    # 3. Initialize OpenAI Realtime LLM Service with language-specific voice
    voice = LANGUAGE_VOICE_MAP.get(call_data.get("language", "en"), "alloy")
    llm_service = OpenAIRealtimeLLMService(
        api_key=settings.openai_api_key,
        model=settings.openai_model,
        voice=voice
    )

    # 4. Create LLMContext with initial system message
    language = call_data.get("language", "en")
    context = LLMContext(
        messages=[
            {
                "role": "system",
                "content": f"You are a healthcare assistant conducting a patient feedback call in {language} language."
            }
        ],
        tools=NOT_GIVEN  # Tools populated dynamically by FlowManager
    )

    # 5. Create Context Aggregators with user turn/mute strategies
    context_aggregator = LLMContextAggregatorPair(
        context=context,
        user_params=LLMUserAggregatorParams(
            user_turn_strategies=UserTurnStrategies(
                start=[VADUserTurnStartStrategy()],           # Detect speech start via VAD
                stop=[TranscriptionUserTurnStopStrategy()]     # Detect speech end via transcription
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

    # 6. Initialize FlowManager with starting node
    flow_manager = FlowManager(
        initial_node=create_greeting_node(),
        context=context
    )

    # 7. Register FlowManager functions with LLM service
    # FlowManager dynamically provides functions based on current conversation stage
    for function_schema in flow_manager.get_current_function_schemas():
        llm_service.register_function(
            function_schema.name,
            function_schema.handler
        )

    # 8. Build Pipeline (order matters!)
    pipeline = Pipeline([
        transport.input(),        # 1. Twilio audio input (µ-law 8kHz → PCM 16kHz via serializer)
        user_aggregator,          # 2. User turn aggregation (VAD + transcription strategies)
        llm_service,              # 3. OpenAI Realtime processing (with FlowManager functions)
        transport.output(),       # 4. Twilio audio output (PCM 16kHz → µ-law 8kHz via serializer)
        assistant_aggregator      # 5. Assistant turn aggregation (after output for logging)
    ])

    # 9. Create Pipeline Task
    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True
        )
        # NOTE: allow_interruptions parameter removed in v0.0.99
        # Interruption handling now managed by user_mute_strategies
    )

    # 10. Initialize FlowManager state
    await flow_manager.initialize()

    # 11. Queue initial LLMRunFrame to start conversation
    await task.queue_frame(LLMRunFrame())

    # 12. Run Pipeline (blocks until call completes or error)
    runner = PipelineRunner()
    try:
        logger.info(f"Starting pipeline for call {call_record_id}")
        await runner.run(task)
        logger.info(f"Pipeline completed for call {call_record_id}")
    except Exception as e:
        logger.error(f"Pipeline error for call {call_record_id}: {e}", exc_info=True)
        flow_manager.state["error"] = str(e)
        flow_manager.state["completed"] = False

    # 13. Return final conversation state for persistence
    return flow_manager.state
