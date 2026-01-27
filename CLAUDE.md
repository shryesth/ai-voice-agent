# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI-powered voice agent system for collecting patient feedback via automated phone calls. Built with FastAPI, Pipecat v0.0.99 (voice pipeline framework), OpenAI Realtime API (gpt-realtime-mini-2025-10-06), Twilio, MongoDB, Redis, and Celery. Supports 4 languages (English, Spanish, French, Haitian Creole) with multi-geography deployment.

## Common Commands

### Development
```bash
# Start all services (MongoDB, Redis, MinIO, API, Celery)
docker compose -f docker-compose.dev.yml up

# View API logs
docker compose -f docker-compose.dev.yml logs -f api

# Access MinIO Console (for S3 storage)
# URL: http://localhost:9001  Credentials: minioadmin/minioadmin
```

### Testing
```bash
# Run all tests with coverage
pytest

# Run specific test directories
pytest tests/unit
pytest tests/integration

# Run single test file
pytest tests/integration/test_queue_processor.py -v

# Run single test function
pytest tests/integration/test_queue_processor.py::test_function_name -v

# Run tests by marker
pytest -m "not slow"
pytest -m unit
pytest -m integration
```

### Code Quality
```bash
black backend/ tests/           # Format
ruff check backend/ tests/      # Lint
mypy backend/                   # Type check
```

### Celery Tasks
```bash
# Start worker manually
celery -A backend.app.celery_app worker --loglevel=info

# Start beat scheduler manually
celery -A backend.app.celery_app beat --loglevel=info

# Monitor with Flower
celery -A backend.app.celery_app flower --port=5555
```

## Architecture

### Layer Structure
```
backend/app/
├── api/v1/          # FastAPI route handlers (REST endpoints)
├── services/        # Business logic, data access coordination
├── domains/         # Feature-specific logic
│   └── patient_feedback/
│       ├── voice_pipeline.py      # Pipecat voice pipeline
│       ├── flow_manager.py        # Conversation state management
│       └── function_registry.py   # LLM function handlers (6 stages)
├── models/          # MongoDB document models (Beanie ODM)
├── schemas/         # Pydantic request/response schemas
├── tasks/           # Celery async tasks
├── infrastructure/  # External integrations (S3, Twilio)
└── core/            # Config, database, security, logging
```

### Key Patterns
- **Async-first**: All DB, Redis, and HTTP operations are async
- **Lifespan management**: FastAPI `@asynccontextmanager` for startup/shutdown
- **Beanie ODM**: MongoDB document models with async operations
- **State machine**: FlowManager handles 6-stage conversation flow (confirm_guardian → confirm_visit → confirm_service → record_side_effects → record_satisfaction → end_call)

### Configuration System
Environment detection via `ENVIRONMENT` variable:
- `development` → `config/.env.local`
- `uat` → `config/.env.uat`
- `production` → `config/.env.prod`

Test environment overrides:
- `SKIP_STARTUP_VALIDATION=true` - Skip connectivity checks for test isolation
- `ENABLE_BOOTSTRAP_ADMIN=false` - Disable auto-creation of admin user in tests

### Main Entry Points
- **API**: `backend/app/main.py` → `uvicorn backend.app.main:app`
- **Celery**: `backend/app/celery_app.py`
- **Voice Pipeline**: `backend/app/domains/patient_feedback/voice_pipeline.py`

### API Routes (in `api/v1/`)
- `auth.py` - `POST /api/v1/auth/login` - JWT authentication
- `health.py` - `GET /api/v1/health/live`, `/ready` - Health probes
- `geographies.py` - Regional organization management
- `queues.py` - CallQueue management
- `recipients.py` - Recipient & DLQ management
- `test_calls.py` - Test call endpoints
- `calls.py` - Call records & Twilio webhooks

### Celery Tasks (in `tasks/`)
- `queue_processor.py` - `process_campaign_queues` - Periodic queue processor (Beat: every 30s)
- `voice_call.py` - `initiate_patient_call`, `update_call_from_webhook` - Call initiation & status handling
- `recording_download.py` - `download_twilio_recording` - Download & upload recordings to S3
- `split_recording.py` - `split_recording_task` - Audio file processing
- `transcript_translation.py` - `translate_transcript` - OpenAI-based translation for non-English calls
- `clarity_sync.py` - `sync_clarity_subjects`, `sync_results_to_clarity`, `sync_all_queues_from_clarity` - Clarity integration (Beat: every 60s)
- `recipient_sync.py` - `sync_recipient_from_call` - Sync call results to recipient records

### Celery Beat Schedule
- `process-campaign-queues`: Every 30s - Process call queues
- `sync-clarity-queues`: Every 60s - Pull subjects from Clarity
- `sync-clarity-results`: Every 60s - Push results to Clarity

## Database

MongoDB with Beanie async ODM. Key collections (models in `models/`):
- `users` - Admin/User accounts with RBAC
- `geographies` - Regional organizations with Clarity config and retention policies
- `call_queues` - Queue definitions with time windows and retry strategies
- `recipients` - Queue recipients with call attempts and conversation results
- `call_records` - Call data with conversation transcripts and recording metadata
- `recording_dlq` - Dead Letter Queue for failed S3 uploads

**Model Import Order**: Geography → CallQueue → Recipient → CallRecord (parent before child for Link resolution)

Privacy filtering: User role receives `[REDACTED]` for patient_phone fields.

## Testing

- **Markers**: `@pytest.mark.unit`, `@pytest.mark.integration`, `@pytest.mark.slow`, `@pytest.mark.asyncio`
- **Fixtures** in `tests/conftest.py`: `async_client`, `test_db`, `test_admin_user`, `auth_headers`
- asyncio_mode is auto-configured in pytest.ini

## Voice Pipeline (Pipecat v0.0.99)

The voice system uses Pipecat framework with:
- **OpenAI Realtime API**: gpt-realtime-mini-2025-10-06 model
- **Server-side VAD**: OpenAI Realtime server-side voice activity detection
- **FunctionRegistry**: Pipecat-compatible handlers (FunctionCallParams + result_callback pattern)
- **FlowManager**: 6-stage state machine with conversation data persistence
- **Twilio**: Telephony integration via WebSocket (TwilioFrameSerializer)

Conversation stages:
1. `confirm_guardian` - Verify speaking with correct person
2. `confirm_visit` - Verify patient visited facility on date
3. `confirm_service` - Verify specific service was received
4. `record_side_effects` - Record side effects (vaccination service only)
5. `record_satisfaction` - Collect 1-10 satisfaction rating
6. `end_call` - Thank and disconnect with EndFrame

Multilingual support:
- System prompts in `domains/patient_feedback/prompts/{lang}/` (en, es, fr, ht)
- Voice mapping: en→alloy, es→nova, fr→alloy, ht→echo
- Automatic transcript translation for non-English calls

## Infrastructure & Storage

**S3/MinIO**:
- Bucket: `voice-recordings` (configurable via `S3_BUCKET_NAME`)
- Purpose: Store call recordings from Twilio
- Upload retry: Exponential backoff, max 5 attempts
- Fallback DLQ: Redis with 7-day TTL if S3 unavailable

**Redis Usage**:
- Celery broker for task distribution
- Celery result backend (1-hour expiry)
- Application caching (health checks, metadata)

**Docker Deployment**:
- Development: `docker-compose.dev.yml` with hot reload
- Production: `docker-compose.production.yml` with resource limits, health checks, replicas

## Important Patterns

**Celery Worker Event Loop**:
Workers must use a consistent event loop for MongoDB async operations. See `celery_app.py`:
```python
@worker_process_init.connect
def init_worker(**kwargs):
    global _worker_event_loop
    _worker_event_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_worker_event_loop)
    _worker_event_loop.run_until_complete(db.connect(...))
```
Use `get_worker_event_loop()` in tasks to ensure MongoDB client compatibility.

**State Management in Voice Pipeline**:
- FlowManager tracks conversation state across 6 stages
- FunctionRegistry dispatches LLM function calls to stage-specific handlers
- Each handler returns FunctionCallParams result via result_callback
- State persisted to CallRecord on completion or error

**Privacy & Security**:
- JWT-based authentication with role-based access control (RBAC)
- User role receives `[REDACTED]` for patient_phone in API responses
- Admin role has full data access

## Specs and Documentation

Feature specifications in `specs/001-patient-feedback-api/`:
- `spec.md` - Feature specification with user stories
- `plan.md` - Implementation roadmap
- `data-model.md` - Database schema documentation
- `contracts/` - API contract definitions
- `quickstart.md` - Getting started guide
