# Implementation Plan: Patient Feedback Collection API

**Branch**: `001-patient-feedback-api` | **Date**: 2026-01-18 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-patient-feedback-api/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

Build a FastAPI-based REST API server for AI-powered patient feedback collection via voice calls. The system enables admins to create geographies and campaigns, initiate test calls, and execute bulk patient feedback campaigns using Twilio for telephony and OpenAI Realtime Model for conversational AI. Core features include role-based authentication (Admin/User), campaign queue processing with Celery/Redis, multilingual support (English, Spanish, French, Haitian Creole), intelligent retry logic, and comprehensive observability with Prometheus/OpenTelemetry-compatible metrics.

## Technical Context

**Language/Version**: Python 3.12.12

**Primary Dependencies**:
- FastAPI 0.128.0 (REST API framework)
- Beanie 2.0.1 (MongoDB ODM with Pydantic integration)
- Pipecat-ai 0.0.99 + pipecat-ai[silero] (voice pipeline orchestration)
- Celery + Redis (async task queue for campaign processing)
- Twilio (outbound calling, WebSocket media streaming)
- OpenAI Realtime API (conversational AI, function calling)
- Pytest 9.0.2 (testing framework)
- HTTPX 0.28.1 (async HTTP client for testing/integrations)

**Storage**: MongoDB 8.0.17 (campaigns, call records, user accounts, queue state)

**Testing**: pytest with async support (pytest-asyncio), contract tests for API endpoints, integration tests for voice pipeline

**Target Platform**: Linux server (Docker containers)

**Deployment**:
- Containerized deployment using Docker
- Production: CapRover apps (multi-container orchestration)
- Each service runs in isolated container: API server, Celery worker, Celery beat scheduler
- Docker Compose for local development

**Project Type**: Single backend API (REST)

**Performance Goals**:
- API health check: <500ms response
- Campaign creation: <30s
- Test call initiation: <10s response
- Voice call completion: <10 minutes per call
- Campaign queue: 10 concurrent calls without degradation
- Metrics endpoint: <1s response

**Constraints**:
- Call duration: max 10 minutes timeout
- Concurrency: max 10 simultaneous calls per campaign (configurable)
- Retry attempts: max 3 per call before Dead Letter Queue
- Token validity: 24 hours
- Carrier compliance: 1 call/2 seconds per number

**Scale/Scope**:
- Target: 100+ campaigns, 10K+ calls/day
- 4 languages supported (English, Spanish, French, Haitian Creole)
- Multi-geography support with independent retention policies

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### I. Specification-Driven Development
✅ **PASS** - Comprehensive spec.md with 5 user stories, 52 functional requirements, 24 success criteria, clarifications session completed

### II. Test-First Development (TDD)
✅ **PASS** - Testing strategy defined (pytest, contract tests, integration tests); TDD workflow will be followed in implementation phase

### III. Independent User Story Implementation
✅ **PASS** - User stories are prioritized (P1, P2, P3) and independently testable:
- US1 (P1): API Server & Auth → independently deployable
- US2 (P2): Geography/Campaign setup → builds on US1 but independently testable
- US3 (P2): Test calls → requires campaigns but independently testable
- US4 (P1): Voice feedback collection → core feature, independently testable
- US5 (P3): Campaign queuing → requires campaigns but independently testable

### IV. FastAPI Architectural Standards
✅ **PASS** - Clean architecture planned:
- Models: Beanie ODM models (Pydantic-based)
- Services: Business logic (auth, campaigns, voice pipeline, queue management)
- API: FastAPI routes under `/api/v1/`
- Tests: contract/, integration/, unit/ organized by type

### V. Voice Agent Domain Excellence
✅ **PASS** - Voice pipeline design follows best practices:
- Pipecat framework for orchestration (proven from reference repo)
- OpenAI Realtime Model for conversational AI
- Twilio WebSocket for audio streaming
- 6-stage conversation flow with state tracking
- Observability: structured logging, metrics, OpenTelemetry

### Testing Discipline
✅ **PASS** - Contract tests for all API endpoints, integration tests for voice pipeline, pytest with async support

### Code Quality
✅ **PASS** - Python 3.12.12 type hints, error handling strategy defined (user/system/transient errors), logging without sensitive data exposure

### Dependencies & Package Management
✅ **PASS** - Python 3.12.12, FastAPI, Beanie (not SQLAlchemy as constitution suggests, but Beanie is MongoDB ODM compatible with Pydantic), pytest, versions pinned

**Result**: All constitution gates PASS. No violations requiring justification.

## Project Structure

### Documentation (this feature)

```text
specs/[###-feature]/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
backend/
├── app/
│   ├── models/                    # Beanie ODM models
│   │   ├── user.py               # User model with role enum
│   │   ├── geography.py          # Geography with retention policy
│   │   ├── campaign.py           # Campaign with queue config
│   │   ├── call_record.py        # CallRecord with transcript
│   │   └── queue_entry.py        # QueueEntry with retry logic
│   │
│   ├── schemas/                   # Pydantic request/response schemas
│   │   ├── auth.py               # LoginRequest, LoginResponse
│   │   ├── geography.py          # GeographyCreate, GeographyResponse
│   │   ├── campaign.py           # CampaignCreate, CampaignResponse
│   │   ├── call.py               # TestCallRequest, CallRecordResponse
│   │   └── queue.py              # QueueEntryResponse, DLQResponse
│   │
│   ├── services/                  # Business logic layer
│   │   ├── auth_service.py       # Authentication & JWT handling
│   │   ├── geography_service.py  # Geography CRUD operations
│   │   ├── campaign_service.py   # Campaign state machine & CRUD
│   │   ├── call_service.py       # Test calls, call record queries
│   │   └── queue_service.py      # Queue management, retry logic
│   │
│   ├── api/v1/                    # FastAPI route handlers
│   │   ├── auth.py               # POST /login, GET /me
│   │   ├── health.py             # GET /health, /health/ready, /metrics
│   │   ├── geographies.py        # Geography CRUD endpoints
│   │   ├── campaigns.py          # Campaign CRUD + state control
│   │   ├── calls.py              # Test calls, call records
│   │   └── queue.py              # Queue monitoring, DLQ management
│   │
│   ├── tasks/                     # Celery tasks
│   │   ├── queue_processor.py    # Process campaign queues (every 30s)
│   │   ├── voice_call.py         # Initiate patient call (Pipecat)
│   │   └── retry_handler.py      # Retry logic, DLQ routing
│   │
│   ├── core/                      # Shared utilities
│   │   ├── config.py             # Pydantic Settings (env vars)
│   │   ├── security.py           # JWT, password hashing
│   │   ├── database.py           # Beanie initialization
│   │   ├── redis.py              # Redis client
│   │   └── logging.py            # Structured logging setup
│   │
│   ├── domains/patient_feedback/  # Voice-specific logic
│   │   ├── voice_pipeline.py     # Pipecat orchestration
│   │   ├── conversation_flow.py  # 6-stage state machine
│   │   ├── urgency_detector.py   # Keyword detection
│   │   └── twilio_integration.py # Twilio API calls, webhooks
│   │
│   ├── main.py                    # FastAPI app factory
│   └── celery_app.py              # Celery app configuration
│
tests/
├── contract/                      # API contract tests
│   ├── test_auth.py              # Auth endpoints
│   ├── test_health.py            # Health & metrics
│   ├── test_geographies.py       # Geography CRUD
│   ├── test_campaigns.py         # Campaign management
│   ├── test_calls.py             # Call endpoints
│   └── test_queue.py             # Queue & DLQ
│
├── integration/                   # Integration tests
│   ├── test_voice_pipeline.py    # Pipecat + Twilio + OpenAI
│   ├── test_queue_processor.py   # Queue scheduler
│   └── test_retry_logic.py       # Retry strategy
│
└── unit/                          # Unit tests
    ├── test_services/            # Service layer tests
    ├── test_models/              # Model validation tests
    └── test_tasks/               # Celery task tests

docker/
├── Dockerfile.api                 # API server container
├── Dockerfile.worker              # Celery worker container
└── Dockerfile.beat                # Celery beat container

scripts/
├── create_admin.py               # Seed admin user
├── migrate_db.py                 # Database migrations
└── backup_db.sh                  # MongoDB backup script

docker-compose.dev.yml            # Local development
docker-compose.production.yml     # Production deployment
captain-definition.json           # CapRover deployment config
requirements.txt                  # Python dependencies
pytest.ini                        # Pytest configuration
.env.example                      # Environment variable template
```

**Structure Decision**: Single backend API project (Option 1 variant). No frontend or mobile app required for MVP. Clean architecture with 4 layers: API → Services → Domain → Infrastructure (Models). Celery tasks separated for async processing. Docker multi-container deployment (API/Worker/Beat).

---

## Voice Pipeline Architecture (Pipecat v0.0.99)

**Purpose**: Production-ready design for implementing the 6-stage patient feedback conversation flow using Pipecat v0.0.99 with OpenAI Realtime API and Twilio WebSocket integration.

**Key Architectural Principle**: TwilioFrameSerializer handles ALL audio conversion (µ-law ↔ PCM, 8kHz ↔ 16kHz) automatically. Pipeline only processes PCM 16kHz audio.

**Reference Implementation**: Based on [pipecat-examples/twilio-chatbot/outbound](https://github.com/pipecat-ai/pipecat-examples/tree/main/twilio-chatbot/outbound)

---

### Module Imports (v0.0.99 Verified)

```python
# Core pipeline components
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineTask

# Frames
from pipecat.frames.frames import (
    LLMRunFrame,
    EndFrame,
    CancelFrame,
    AudioRawFrame,
    InputAudioRawFrame
)

# LLM service and context management
from pipecat.services.openai.realtime.llm import OpenAIRealtimeLLMService
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContext,
    LLMContextAggregatorPair
)

# Transport layer (FastAPI WebSocket for Twilio)
from pipecat.transports.fastapi_websocket import (
    FastAPIWebsocketTransport,
    FastAPIWebsocketParams
)

# Twilio serializer (HANDLES ALL AUDIO CONVERSION)
from pipecat.serializers.twilio import TwilioFrameSerializer

# VAD (Voice Activity Detection)
from pipecat.vad.silero import SileroVADAnalyzer
from pipecat.vad.vad_analyzer import VADParams

# Flow management (separate library: pipecat-flows)
from pipecat_flows import FlowManager, FlowArgs, FlowResult
from pipecat_flows.function_schema import FlowsFunctionSchema
from pipecat_flows.types import NodeConfig

# FastAPI for WebSocket server
from fastapi import FastAPI, WebSocket
from fastapi.responses import JSONResponse
```

---

### Audio Conversion Architecture (TwilioFrameSerializer)

**CRITICAL**: TwilioFrameSerializer is Pipecat's built-in solution that handles all audio format conversion automatically. No manual audio processing code needed.

**What TwilioFrameSerializer Does:**

```
┌─────────────────────────────────────────────────────────────┐
│ INCOMING: Twilio → Pipeline                                 │
│                                                              │
│ Twilio Phone (µ-law 8kHz)                                  │
│     │                                                        │
│     ├─ WebSocket: base64-encoded µ-law chunks              │
│     │                                                        │
│     ▼                                                        │
│ TwilioFrameSerializer.deserialize():                        │
│     ├─ base64.b64decode()                                  │
│     ├─ audioop.ulaw2lin() → PCM 16-bit                    │
│     ├─ SOXR resample (8kHz → 16kHz)                       │
│     └─ InputAudioRawFrame(sample_rate=16000)              │
│              │                                              │
│              ▼                                              │
│ Pipeline processes PCM 16kHz                                │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ OUTGOING: Pipeline → Twilio                                 │
│                                                              │
│ Pipeline outputs PCM 16kHz                                  │
│     │                                                        │
│     ├─ AudioRawFrame(sample_rate=16000)                    │
│     │                                                        │
│     ▼                                                        │
│ TwilioFrameSerializer.serialize():                          │
│     ├─ SOXR resample (16kHz → 8kHz)                       │
│     ├─ audioop.lin2ulaw() → µ-law                         │
│     ├─ base64.b64encode()                                  │
│     └─ Twilio media event JSON                             │
│              │                                              │
│              ▼                                              │
│ Twilio Phone (µ-law 8kHz)                                  │
└─────────────────────────────────────────────────────────────┘
```

**Serializer Configuration:**

```python
# Create TwilioFrameSerializer - handles ALL audio conversion
serializer = TwilioFrameSerializer(
    stream_sid=call_data["stream_id"],          # From Twilio WebSocket "start" event
    call_sid=call_data["call_id"],              # For call termination via REST API
    account_sid=os.getenv("TWILIO_ACCOUNT_SID"),
    auth_token=os.getenv("TWILIO_AUTH_TOKEN"),
    params=TwilioFrameSerializer.InputParams(
        twilio_sample_rate=8000,                # Twilio's µ-law sample rate
        sample_rate=16000,                      # Pipeline/OpenAI Realtime sample rate
        auto_hang_up=True                       # Auto terminate call on EndFrame
    )
)
```

---

### Transport and LLM Service Setup

**1. FastAPI WebSocket Transport with Twilio Serializer:**

```python
# Configure transport with serializer
transport = FastAPIWebsocketTransport(
    websocket=websocket,
    params=FastAPIWebsocketParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
        add_wav_header=False,                   # Raw audio, no WAV headers
        vad_enabled=True,
        vad_analyzer=SileroVADAnalyzer(
            params=VADParams(stop_secs=0.2)     # 200ms silence = turn stop
        ),
        vad_audio_passthrough=True,
        serializer=serializer                    # Twilio serializer handles µ-law ↔ PCM
    )
)
```

**2. OpenAI Realtime LLM Service:**

```python
# Initialize OpenAI Realtime service
llm_service = OpenAIRealtimeLLMService(
    api_key=os.getenv("OPENAI_API_KEY"),
    model="gpt-4o-realtime-preview-2024-12-17"
)

# Note: Configuration is done via LLMContext messages, not session_properties
```

**3. LLM Context and Aggregators:**

```python
# Create context with system instructions
context = LLMContext(
    messages=[
        {
            "role": "system",
            "content": (
                "You are a healthcare assistant conducting patient feedback surveys. "
                "Keep responses concise and conversational, suitable for speech synthesis. "
                "Collect structured feedback about patient satisfaction, concerns, and side effects."
            )
        }
    ],
    tools=[]  # Functions registered separately via FlowManager
)

# Create context aggregators
context_aggregator = LLMContextAggregatorPair(context=context)
user_aggregator = context_aggregator.user()
assistant_aggregator = context_aggregator.assistant()
```

---

### 6-Stage Conversation Flow (FlowManager Pattern)

**Reference**: Based on [pipecat-flows patient_intake.py](https://github.com/pipecat-ai/pipecat-flows/blob/main/examples/patient_intake.py)

**Flow Architecture**: Each conversation stage = NodeConfig with function handlers that return (FlowResult, NextNode)

**FlowResult Base Classes (Required):**

```python
from pipecat_flows import FlowResult

class GreetingResult(FlowResult):
    acknowledged: bool

class LanguageResult(FlowResult):
    language: str

class VerificationResult(FlowResult):
    verified: bool
    is_patient: bool

class FeedbackResult(FlowResult):
    satisfaction_rating: int
    specific_concerns: str
    side_effects: str
    experience_quality: str

class UrgencyResult(FlowResult):
    flagged: bool
    keywords: list[str]

class CompletionResult(FlowResult):
    reason: str
```

---

**Stage 1: Greeting Node**

```python
def create_greeting_node() -> NodeConfig:
    """Initial greeting and audio confirmation."""

    async def greeting_handler(args: FlowArgs, flow_manager: FlowManager):
        # Extract function arguments
        acknowledged = args.get("acknowledged", False)

        # Store in persistent flow state
        flow_manager.state["greeted"] = acknowledged
        flow_manager.state["greeting_timestamp"] = datetime.utcnow().isoformat()

        # Return result and next node
        return GreetingResult(acknowledged=acknowledged), create_language_selection_node()

    return NodeConfig(
        name="greeting",
        role_messages=[{
            "role": "system",
            "content": "You are a friendly healthcare assistant conducting patient feedback surveys."
        }],
        task_messages=[{
            "role": "system",
            "content": (
                "Greet the patient warmly. Introduce yourself as calling from their healthcare provider "
                "to collect brief feedback. Confirm they can hear you clearly."
            )
        }],
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
    async def language_handler(args: FlowArgs, flow_manager: FlowManager):
        language = args.get("language", "en")
        flow_manager.state["language"] = language

        # Update LLM voice based on language
        # Spanish: "nova", French: "alloy", Haitian Creole: "echo"
        # Note: Voice switching handled by multilingual support layer

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
    async def feedback_handler(args: FlowArgs, flow_manager: FlowManager):
        # Store structured feedback
        flow_manager.state["feedback"] = {
            "satisfaction": args.get("satisfaction_rating"),
            "concerns": args.get("specific_concerns", ""),
            "side_effects": args.get("side_effects", ""),
            "experience": args.get("experience_quality", "")
        }

        # Proceed to urgency detection (which will scan transcript for keywords)
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
    async def completion_handler(args: FlowArgs, flow_manager: FlowManager):
        flow_manager.state["completed"] = True
        flow_manager.state["completion_reason"] = reason

        # Note: CallRecord persistence is handled by Celery task after pipeline completes
        # The final state (flow_manager.state) will be returned from create_voice_pipeline()

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
```

### Pipeline Assembly

**Complete Pipeline Construction (v0.0.99 Pattern):**

```python
async def create_voice_pipeline(websocket: WebSocket, call_record_id: str, call_data: dict):
    """
    Creates and runs the complete voice pipeline for a patient feedback call.

    Args:
        websocket: FastAPI WebSocket connection from Twilio
        call_record_id: MongoDB ObjectId for CallRecord persistence
        call_data: Dict with campaign_id, patient_phone, language, etc.

    Returns:
        Final conversation state (flow_manager.state) for CallRecord persistence
    """

    # 1. Initialize TwilioFrameSerializer (handles ALL audio conversion)
    serializer = TwilioFrameSerializer(
        stream_sid=call_data["stream_id"],
        call_sid=call_data["call_id"],
        account_sid=os.getenv("TWILIO_ACCOUNT_SID"),
        auth_token=os.getenv("TWILIO_AUTH_TOKEN"),
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
            vad_enabled=True,
            vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=0.2)),
            vad_audio_passthrough=True,
            serializer=serializer  # TwilioFrameSerializer handles µ-law ↔ PCM
        )
    )

    # 3. Initialize OpenAI Realtime LLM Service
    llm_service = OpenAIRealtimeLLMService(
        api_key=os.getenv("OPENAI_API_KEY"),
        model="gpt-4o-realtime-preview-2024-12-17",
        voice=call_data.get("voice", "alloy")  # Language-specific voice
    )

    # 4. Create LLMContext with initial system message
    context = LLMContext(
        messages=[
            {"role": "system", "content": f"You are a healthcare assistant conducting a patient feedback call in {call_data['language']} language."}
        ],
        tools=[]  # Tools populated dynamically by FlowManager
    )

    # 5. Create Context Aggregators with user turn/mute strategies
    context_aggregator = LLMContextAggregatorPair(
        context=context,
        user_turn_strategies=[
            VADUserTurnStartStrategy(),           # Detect speech start via VAD
            TranscriptionUserTurnStopStrategy()   # Detect speech end via transcription
        ],
        user_mute_strategies=[
            MuteUntilFirstBotCompleteUserMuteStrategy(),  # Wait for bot's first response
            FunctionCallUserMuteStrategy()                # Mute during function execution
        ]
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
        llm_service.register_function(function_schema)

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
        await runner.run(task)
    except Exception as e:
        logger.error(f"Pipeline error for call {call_record_id}: {e}")
        flow_manager.state["error"] = str(e)
        flow_manager.state["completed"] = False

    # 13. Return final conversation state for persistence
    return flow_manager.state
```

### Turn Detection & Interruption Handling

**User Turn Strategies (v0.0.99 Replaces `turn_analyzer`):**

```python
# Start detection strategies
user_turn_start_strategies = [
    VADUserTurnStartStrategy(),  # Voice Activity Detection triggers turn start
    # OR
    TranscriptionUserTurnStartStrategy(),  # Wait for transcription confidence
    # OR
    MinWordsUserTurnStartStrategy(min_words=3)  # Require minimum words
]

# Stop detection strategies
user_turn_stop_strategies = [
    TranscriptionUserTurnStopStrategy(),  # Transcription ends = turn complete
    # OR
    TurnAnalyzerUserTurnStopStrategy(  # Custom turn analyzer logic
        turn_analyzer=custom_analyzer
    )
]

# Apply to context aggregator
context_aggregator = LLMContextAggregatorPair(
    context=context,
    user_turn_strategies=user_turn_start_strategies + user_turn_stop_strategies
)
```

**User Mute Strategies (v0.0.99 Replaces `allow_interruptions`):**

```python
# Mute strategies control when user audio is processed
user_mute_strategies = [
    # Wait for bot's first complete response before accepting user input
    MuteUntilFirstBotCompleteUserMuteStrategy(),

    # Mute user during function call execution
    FunctionCallUserMuteStrategy(),

    # Allow interruption after first speech
    FirstSpeechUserMuteStrategy()
]

context_aggregator = LLMContextAggregatorPair(
    context=context,
    user_turn_strategies=[...],
    user_mute_strategies=user_mute_strategies  # NEW parameter
)
```

### Event Handling & Transcript Logging

**Transport Event Handlers (v0.0.99 Pattern):**

```python
# Set up event handlers for transcript logging and call lifecycle management
async def setup_event_handlers(transport, call_record):
    """
    Registers event handlers for WebSocket lifecycle and transcript logging.

    Important: Event handlers use @transport.event_handler() decorator, NOT
    @context_aggregator decorators which were from older Pipecat versions.
    """

    @transport.event_handler("on_client_connected")
    async def on_connected(transport, client_data):
        """Called when Twilio WebSocket connects"""
        logger.info(f"Call connected: {call_record.call_tracking.call_sid}")
        call_record.call_tracking.started_at = datetime.utcnow()
        await call_record.save()

    @transport.event_handler("on_client_disconnected")
    async def on_disconnected(transport, client_data):
        """Called when Twilio WebSocket disconnects"""
        logger.info(f"Call disconnected: {call_record.call_tracking.call_sid}")
        call_record.call_tracking.ended_at = datetime.utcnow()
        call_record.call_tracking.duration_seconds = (
            call_record.call_tracking.ended_at - call_record.call_tracking.started_at
        ).total_seconds()
        await call_record.save()

    # Note: Transcript logging happens via context aggregator frame processors
    # See TranscriptLogger class below

class TranscriptLogger:
    """
    Custom frame processor for logging conversation transcript in real-time.

    Processes transcription frames from user_aggregator and assistant_aggregator
    to build conversation history.
    """

    def __init__(self, call_record):
        self.call_record = call_record

    async def process_frame(self, frame, direction):
        """Process frames to capture transcript entries"""
        from pipecat.frames.frames import TranscriptionFrame, TextFrame

        if isinstance(frame, TranscriptionFrame):
            # User transcription (from user_aggregator)
            transcript_entry = ConversationTurn(
                speaker="patient",
                text=frame.text,
                timestamp=datetime.utcnow(),
                language=frame.language
            )
            self.call_record.transcript.append(transcript_entry)
            await self.call_record.save()

            logger.info(f"User: {frame.text}", extra={
                "call_sid": self.call_record.call_tracking.call_sid
            })

        elif isinstance(frame, TextFrame):
            # Assistant text (from assistant_aggregator)
            transcript_entry = ConversationTurn(
                speaker="ai",
                text=frame.text,
                timestamp=datetime.utcnow()
            )
            self.call_record.transcript.append(transcript_entry)
            await self.call_record.save()

            logger.info(f"AI: {frame.text}", extra={
                "call_sid": self.call_record.call_tracking.call_sid
            })

        return frame  # Pass frame through to next processor

# Usage in pipeline:
# pipeline = Pipeline([
#     transport.input(),
#     user_aggregator,
#     TranscriptLogger(call_record),  # Insert after user_aggregator
#     llm_service,
#     transport.output(),
#     assistant_aggregator,
#     TranscriptLogger(call_record)   # Insert after assistant_aggregator
# ])
```

### Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    Twilio Phone Call                            │
│                    (Patient answers)                            │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│         FastAPIWebsocketTransport + TwilioFrameSerializer       │
│         - Serializer handles ALL audio conversion:             │
│           • Incoming: µ-law 8kHz → PCM 16kHz (audioop + SOXR)  │
│           • Outgoing: PCM 16kHz → µ-law 8kHz (SOXR + audioop)  │
│         - WebSocket handles Twilio Media Stream protocol       │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│         LLMContextAggregatorPair.user() (user_aggregator)       │
│         - VADUserTurnStartStrategy: Detect speech start        │
│         - TranscriptionUserTurnStopStrategy: Detect speech end │
│         - user_mute_strategies: Control when to process audio  │
│         - Output: Transcribed user text                       │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│         OpenAI Realtime LLM Service                             │
│         - Model: gpt-4o-realtime-preview-2024-12-17            │
│         - Input: Patient speech transcription                   │
│         - Processing: Function calling (FlowManager nodes)     │
│         - Output: AI response text + TTS audio                 │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│         FlowManager (6-stage conversation state machine)        │
│         1. Greeting → 2. Language → 3. Verification →          │
│         4. Feedback → 5. Urgency → 6. Completion               │
│         - Each stage = NodeConfig with:                        │
│           • role_messages: System identity                     │
│           • task_messages: Stage-specific instructions         │
│           • functions: FlowsFunctionSchema handlers            │
│         - Dynamic transitions based on patient responses       │
│         - State persisted in flow_manager.state               │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│         LLMContextAggregatorPair.assistant() (assistant_agg)    │
│         - Aggregates AI response text and audio frames         │
│         - Passes audio to transport for playback              │
│         - Logs assistant transcript                           │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│         CallRecord Persistence (after pipeline completes)       │
│         - conversation_state: FlowManager.state                │
│         - transcript: List[ConversationTurn] (patient + AI)    │
│         - feedback: FeedbackData (structured responses)        │
│         - urgency_flagged: Bool (keyword detection)            │
│         - call_tracking: Twilio metadata (call_sid, duration)  │
└─────────────────────────────────────────────────────────────────┘
```

### Urgency Detection Integration

**Real-time Keyword Monitoring:**

```python
# Urgency detector integrated as middleware
from backend.app.domains.patient_feedback.urgency_detector import UrgencyDetector

urgency_detector = UrgencyDetector(
    keywords=["hospital", "severe", "can't breathe", "emergency", "ambulance", "911"]
)

@context_aggregator.user.on_user_turn_stopped
async def check_urgency(turn):
    detected_keywords = urgency_detector.scan(turn.transcription)

    if detected_keywords:
        # Flag call record immediately
        call_record.urgency_flagged = True
        call_record.urgency_keywords_detected.extend(detected_keywords)

        # Update flow state to trigger urgency node
        flow_manager.state["urgency_detected"] = True

        logger.warning(f"Urgency keywords detected: {detected_keywords}", extra={
            "call_sid": call_record.call_tracking.call_sid,
            "keywords": detected_keywords
        })
```

### Multilingual Support Configuration

**Language-Specific Voice Selection:**

```python
LANGUAGE_VOICE_MAP = {
    "en": "alloy",   # English: neutral voice
    "es": "nova",    # Spanish: warm voice
    "fr": "alloy",   # French: neutral voice
    "ht": "echo"     # Haitian Creole: clear voice
}

async def create_language_specific_llm_service(language: str) -> OpenAIRealtimeLLMService:
    """
    Creates LLM service with language-specific voice configuration.

    Note: Voice is set at service initialization, not dynamically updated.
    For mid-call language switching, you would need to recreate the LLM service
    and swap pipeline processors (not recommended - better to set language at call start).
    """
    voice = LANGUAGE_VOICE_MAP.get(language, "alloy")

    llm_service = OpenAIRealtimeLLMService(
        api_key=os.getenv("OPENAI_API_KEY"),
        model="gpt-4o-realtime-preview-2024-12-17",
        voice=voice  # Set voice based on language preference
    )

    return llm_service

# System prompts for different languages
def get_system_prompt_for_language(language: str) -> str:
    """Returns language-specific system prompt"""
    prompts = {
        "en": "You are a healthcare assistant conducting a patient feedback call in English.",
        "es": "Eres un asistente de atención médica realizando una llamada de retroalimentación del paciente en español.",
        "fr": "Vous êtes un assistant de soins de santé effectuant un appel de retour d'information patient en français.",
        "ht": "Ou se yon asistan swen sante k ap fè yon apèl opinyon pasyan an kreyòl ayisyen."
    }
    return prompts.get(language, prompts["en"])

# Usage: Language is set when creating the pipeline based on campaign config
# call_data["language"] comes from Campaign.config.language_preference
```

### Error Handling & Retry Logic

**Transient Failure Recovery:**

```python
try:
    result = await runner.run(task)
except ConnectionError as e:
    # Network failure mid-call
    call_record.call_tracking.outcome = CallOutcome.NETWORK_FAILURE
    call_record.error_message = str(e)

    # Save partial transcript
    await call_record.save()

    # Schedule retry via QueueEntry
    queue_entry.state = QueueState.RETRYING
    queue_entry.last_failure_reason = FailureReason.NETWORK_FAILURE
    queue_entry.next_retry_at = datetime.utcnow() + timedelta(minutes=15)
    await queue_entry.save()
except TimeoutError:
    # Call exceeded 10 minute limit
    call_record.call_tracking.outcome = CallOutcome.TIMEOUT
    await call_record.save()
```

### Testing Strategy

**Integration Test Pattern:**

```python
# tests/integration/test_voice_pipeline.py
@pytest.mark.asyncio
async def test_full_conversation_flow():
    # Mock Twilio WebSocket
    mock_websocket = create_mock_twilio_websocket()

    # Create test CallRecord
    call_record = CallRecord(
        campaign_id=test_campaign.id,
        patient_phone="+12025551234",
        language="en"
    )

    # Run pipeline
    final_state = await create_voice_pipeline(mock_websocket, call_record.id)

    # Verify all 6 stages completed
    assert "greeted" in final_state
    assert "verified" in final_state
    assert "feedback" in final_state
    assert final_state["completed"] is True

    # Verify CallRecord persisted
    saved_record = await CallRecord.get(call_record.id)
    assert len(saved_record.transcript) > 0
    assert saved_record.conversation_state.current_stage == ConversationStage.CALL_COMPLETION
```

### Complete Working Example

**Full FastAPI Endpoint with Pipecat v0.0.99 Pipeline:**

```python
# backend/app/api/routes/webhooks.py
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from backend.app.domains.patient_feedback.voice_pipeline import create_voice_pipeline
from backend.app.models.call import CallRecord
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

@router.websocket("/api/v1/webhooks/twilio/media")
async def twilio_media_stream(websocket: WebSocket):
    """
    Twilio Media Stream WebSocket endpoint for voice calls.

    Twilio connects to this endpoint when outbound call is answered.
    The WebSocket receives µ-law 8kHz audio and sends back synthesized audio.
    """
    await websocket.accept()

    try:
        # 1. Receive Twilio "start" event with call metadata
        start_message = await websocket.receive_json()

        if start_message.get("event") != "start":
            logger.error("Expected 'start' event from Twilio")
            await websocket.close()
            return

        # Extract call metadata
        call_sid = start_message["start"]["callSid"]
        stream_sid = start_message["start"]["streamSid"]
        custom_parameters = start_message["start"].get("customParameters", {})

        campaign_id = custom_parameters.get("campaign_id")
        patient_phone = custom_parameters.get("patient_phone")
        language = custom_parameters.get("language", "en")

        logger.info(f"Twilio media stream started: {call_sid}")

        # 2. Create CallRecord in database
        call_record = CallRecord(
            campaign_id=campaign_id,
            patient_phone=patient_phone,
            language=language,
            call_tracking={
                "call_sid": call_sid,
                "stream_sid": stream_sid,
                "status": "in-progress"
            }
        )
        await call_record.save()

        # 3. Prepare call_data for pipeline
        call_data = {
            "call_id": call_sid,
            "stream_id": stream_sid,
            "campaign_id": campaign_id,
            "patient_phone": patient_phone,
            "language": language
        }

        # 4. Run Pipecat voice pipeline (blocks until call completes)
        final_state = await create_voice_pipeline(
            websocket=websocket,
            call_record_id=str(call_record.id),
            call_data=call_data
        )

        # 5. Update CallRecord with final conversation state
        call_record.conversation_state = final_state
        call_record.call_tracking["status"] = "completed"

        # Extract structured feedback from flow state
        if "feedback" in final_state:
            call_record.feedback = final_state["feedback"]

        # Check urgency flag
        if final_state.get("urgency_flagged"):
            call_record.urgency_flagged = True
            call_record.urgency_keywords_detected = final_state.get("urgency_keywords", [])

        await call_record.save()

        logger.info(f"Call completed successfully: {call_sid}")

    except WebSocketDisconnect:
        logger.info(f"Twilio WebSocket disconnected: {call_sid}")
    except Exception as e:
        logger.error(f"Error in voice pipeline: {e}", exc_info=True)
        # Update CallRecord with error state
        if call_record:
            call_record.call_tracking["status"] = "failed"
            call_record.call_tracking["error"] = str(e)
            await call_record.save()
    finally:
        try:
            await websocket.close()
        except:
            pass


# backend/app/domains/patient_feedback/voice_pipeline.py
"""
Pipecat v0.0.99 voice pipeline implementation for patient feedback calls.
"""
import os
from datetime import datetime
from fastapi import WebSocket

from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineTask, PipelineParams
from pipecat.frames.frames import LLMRunFrame
from pipecat.services.openai.realtime.llm import OpenAIRealtimeLLMService
from pipecat.processors.aggregators.llm_response_universal import LLMContext, LLMContextAggregatorPair
from pipecat.transports.fastapi_websocket import FastAPIWebsocketTransport, FastAPIWebsocketParams
from pipecat.serializers.twilio import TwilioFrameSerializer
from pipecat.vad.silero import SileroVADAnalyzer
from pipecat.vad.vad_analyzer import VADParams
from pipecat.strategies.user_turn import VADUserTurnStartStrategy, TranscriptionUserTurnStopStrategy
from pipecat.strategies.user_mute import MuteUntilFirstBotCompleteUserMuteStrategy, FunctionCallUserMuteStrategy

from pipecat_flows import FlowManager
from backend.app.domains.patient_feedback.conversation_flows import create_greeting_node
from backend.app.models.call import CallRecord

import logging

logger = logging.getLogger(__name__)


async def create_voice_pipeline(websocket: WebSocket, call_record_id: str, call_data: dict):
    """
    Creates and runs the complete Pipecat v0.0.99 voice pipeline.

    Architecture:
    1. TwilioFrameSerializer: Handles ALL µ-law ↔ PCM audio conversion
    2. FastAPIWebsocketTransport: WebSocket communication with Twilio
    3. LLMContextAggregatorPair: User/Assistant turn management with VAD strategies
    4. OpenAIRealtimeLLMService: gpt-4o-realtime for conversational AI
    5. FlowManager: 6-stage conversation state machine

    Returns:
        Final conversation state (dict) for CallRecord persistence
    """

    # Initialize serializer (handles ALL audio conversion)
    serializer = TwilioFrameSerializer(
        stream_sid=call_data["stream_id"],
        call_sid=call_data["call_id"],
        account_sid=os.getenv("TWILIO_ACCOUNT_SID"),
        auth_token=os.getenv("TWILIO_AUTH_TOKEN"),
        params=TwilioFrameSerializer.InputParams(
            twilio_sample_rate=8000,
            sample_rate=16000,
            auto_hang_up=True
        )
    )

    # Initialize transport
    transport = FastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            vad_enabled=True,
            vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=0.2)),
            vad_audio_passthrough=True,
            serializer=serializer
        )
    )

    # Initialize LLM service with language-specific voice
    voice_map = {"en": "alloy", "es": "nova", "fr": "alloy", "ht": "echo"}
    llm_service = OpenAIRealtimeLLMService(
        api_key=os.getenv("OPENAI_API_KEY"),
        model="gpt-4o-realtime-preview-2024-12-17",
        voice=voice_map.get(call_data["language"], "alloy")
    )

    # Create context
    context = LLMContext(
        messages=[
            {"role": "system", "content": f"Healthcare assistant conducting patient feedback call in {call_data['language']}."}
        ],
        tools=[]
    )

    # Create aggregators with strategies
    context_aggregator = LLMContextAggregatorPair(
        context=context,
        user_turn_strategies=[
            VADUserTurnStartStrategy(),
            TranscriptionUserTurnStopStrategy()
        ],
        user_mute_strategies=[
            MuteUntilFirstBotCompleteUserMuteStrategy(),
            FunctionCallUserMuteStrategy()
        ]
    )

    # Initialize FlowManager
    flow_manager = FlowManager(
        initial_node=create_greeting_node(),
        context=context
    )

    # Register functions
    for func_schema in flow_manager.get_current_function_schemas():
        llm_service.register_function(func_schema)

    # Build pipeline
    pipeline = Pipeline([
        transport.input(),
        context_aggregator.user(),
        llm_service,
        transport.output(),
        context_aggregator.assistant()
    ])

    # Create task
    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True
        )
    )

    # Run pipeline
    await flow_manager.initialize()
    await task.queue_frame(LLMRunFrame())

    runner = PipelineRunner()
    try:
        await runner.run(task)
    except Exception as e:
        logger.error(f"Pipeline error: {e}")
        flow_manager.state["error"] = str(e)

    return flow_manager.state
```

**Key Implementation Points:**

1. **TwilioFrameSerializer is THE complete solution**: No manual audio conversion code needed
2. **FlowManager provides dynamic functions**: Functions change per conversation stage
3. **Voice is set at LLM service creation**: Based on language preference from campaign config
4. **Pipeline order matters**: `transport.input() → user_agg → llm → transport.output() → assistant_agg`
5. **Event handlers use @transport.event_handler()**: Not old aggregator decorators
6. **State persistence happens after pipeline completes**: `flow_manager.state` contains all conversation data

---

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| [e.g., 4th project] | [current need] | [why 3 projects insufficient] |
| [e.g., Repository pattern] | [specific problem] | [why direct DB access insufficient] |
