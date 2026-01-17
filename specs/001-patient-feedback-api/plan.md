# Implementation Plan: Patient Feedback Collection API

**Branch**: `001-patient-feedback-api` | **Date**: 2026-01-18 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-patient-feedback-api/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

Build a FastAPI-based REST API server for AI-powered patient feedback collection via voice calls. The system enables admins to create geographies and campaigns, initiate test calls, and execute bulk patient feedback campaigns using Twilio for telephony and OpenAI Realtime Model for conversational AI. Core features include role-based authentication (Admin/User), campaign queue processing with Celery/Redis, multilingual support (English, Spanish, French, Haitian Creole), intelligent retry logic, and comprehensive observability with Prometheus/OpenTelemetry-compatible metrics.

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**:
- FastAPI 0.128.0 (REST API framework)
- Beanie 2.0.1 (MongoDB ODM with Pydantic integration)
- Pipecat-ai 0.0.99 + pipecat-ai[silero] (voice pipeline orchestration)
- Celery + Redis (async task queue for campaign processing)
- Twilio (outbound calling, WebSocket media streaming)
- OpenAI Realtime API (conversational AI, function calling)
- Pytest 9.0.2 (testing framework)
- HTTPX 0.28.1 (async HTTP client for testing/integrations)

**Storage**: MongoDB (campaigns, call records, user accounts, queue state)

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
✅ **PASS** - Python 3.11+ type hints, error handling strategy defined (user/system/transient errors), logging without sensitive data exposure

### Dependencies & Package Management
✅ **PASS** - Python 3.11+, FastAPI, Beanie (not SQLAlchemy as constitution suggests, but Beanie is MongoDB ODM compatible with Pydantic), pytest, versions pinned

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

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| [e.g., 4th project] | [current need] | [why 3 projects insufficient] |
| [e.g., Repository pattern] | [specific problem] | [why direct DB access insufficient] |
