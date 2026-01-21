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

# Run specific test categories
pytest tests/unit -m unit
pytest tests/integration -m integration
pytest tests/contract -m contract

# Run single test file
pytest tests/contract/test_auth.py -v

# Run tests by marker
pytest -m "not slow"
pytest -m voice
pytest -m queue
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
- `staging` → `config/.env.uat`
- `production` → `config/.env.prod`

Test environment overrides:
- `SKIP_STARTUP_VALIDATION=true` - Skip connectivity checks for test isolation
- `ENABLE_BOOTSTRAP_ADMIN=false` - Disable auto-creation of admin user in tests

### Main Entry Points
- **API**: `backend/app/main.py` → `uvicorn backend.app.main:app`
- **Celery**: `backend/app/celery_app.py`
- **Voice Pipeline**: `backend/app/domains/patient_feedback/voice_pipeline.py`

### API Routes
- `POST /api/v1/auth/login` - JWT authentication
- `GET /api/v1/health/live` - Liveness probe
- `GET /api/v1/metrics` - Prometheus metrics
- `GET/POST /api/v1/geographies` - Regional organization management
- `GET/POST /api/v1/queues` - CallQueue management (NEW architecture)
- `GET/POST /api/v1/recipients` - Recipient & DLQ management (NEW)
- `POST /api/v1/calls/test` - Initiate test call with scenarios
- `GET/POST /api/v1/calls` - Call records & Twilio webhooks
- `GET/POST /api/v1/campaigns` - Legacy campaign endpoints (backward compatibility)
- `GET/POST /api/v1/queue` - Legacy queue endpoints (backward compatibility)

### Celery Tasks (in `tasks/`)
- `process_campaign_queues` - Periodic queue processor (Beat: every 30s)
- `initiate_patient_call` - Initiate voice call with Twilio
- `update_call_from_webhook` - Handle Twilio status webhooks
- `download_twilio_recording` - Download & upload recordings to S3
- `translate_transcript` - OpenAI-based transcript translation for non-English calls
- `sync_clarity_data` - Bidirectional sync with Clarity integration
- Intelligent retry with exponential backoff via `retry_handler.py`

## Database

MongoDB with Beanie async ODM. Key collections:
- `users` - Admin/User accounts with RBAC (Admin vs User roles)
- `geographies` - Regional organizations with retention policies
- `call_queues` - NEW: Queue definitions (replaces campaigns)
- `recipients` - NEW: Queue recipients (replaces queue_entry)
- `campaigns` - Legacy: Campaign definitions (backward compatibility)
- `queue_entry` - Legacy: Queue entries (backward compatibility)
- `call_records` - Call data with conversation transcripts
- `recording_dlq` - Dead Letter Queue for failed S3 uploads

Privacy filtering: User role receives `[REDACTED]` for patient_phone fields.

## Testing

- **80% coverage requirement** (configured in pytest.ini)
- **Markers**: `@pytest.mark.unit`, `@pytest.mark.integration`, `@pytest.mark.contract`, `@pytest.mark.voice`, `@pytest.mark.queue`, `@pytest.mark.auth`
- **Fixtures** in `tests/conftest.py`: `async_client`, `test_db`, `test_admin_user`, `auth_headers`

## Voice Pipeline (Pipecat v0.0.99)

The voice system uses Pipecat framework with:
- **OpenAI Realtime API**: gpt-realtime-mini-2025-10-06 model
- **Silero VAD**: Voice activity detection for turn management
- **FunctionRegistry**: Pipecat-compatible handlers (FunctionCallParams + result_callback pattern)
- **FlowManager**: 6-stage state machine with conversation data persistence
- **Twilio**: Telephony integration via WebSocket (TwilioFrameSerializer)
- **Turn Strategies**: VADUserTurnStartStrategy + TranscriptionUserTurnStopStrategy

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
- Upload retry: Exponential backoff (1s base, 60s max), max 5 attempts
- Fallback DLQ: Redis with 7-day TTL if S3 unavailable

**Redis Usage**:
- Celery broker for task distribution
- Celery result backend (1-hour expiry)
- Application caching (health checks, metadata)

**Docker Deployment**:
- Development: `docker-compose.dev.yml` with hot reload and local volumes
- Production: `docker-compose.production.yml` with:
  - Resource limits (MongoDB: 2 CPU/2GB RAM, Redis: 1 CPU/1GB RAM)
  - Network segmentation (backend-network + frontend-network)
  - Health checks (30s interval, 3 retries)
  - 2 API replicas, 2 Celery worker replicas, 1 Beat replica
  - Log rotation (50MB max, 5 files)

## Important Patterns

**Service Layer Architecture**:
- Controllers (api/v1/) handle HTTP concerns only
- Services (services/) contain business logic and coordinate data access
- Domains (domains/) contain feature-specific logic isolated from API layer
- Models (models/) are Beanie ODM documents with async operations

**Async-First Design**:
- All DB, Redis, and HTTP operations use async/await
- Celery worker creates event loop on startup for MongoDB compatibility
- Test fixtures use pytest-asyncio with function-scoped event loops

**Celery Worker Initialization Pattern**:
```python
# workers must initialize event loop for Beanie async operations
import asyncio
from beanie import init_beanie

@celery.on_after_configure.connect
def worker_startup(sender, **kwargs):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(init_beanie(...))
```

**State Management in Voice Pipeline**:
- FlowManager tracks conversation state across 6 stages
- FunctionRegistry dispatches LLM function calls to stage-specific handlers
- Each handler returns FunctionCallParams result via result_callback
- State persisted to CallRecord on completion or error

**Privacy & Security**:
- JWT-based authentication with role-based access control (RBAC)
- User role receives `[REDACTED]` for patient_phone in API responses
- Admin role has full data access
- Password hashing via bcrypt

## Specs and Documentation

Feature specifications in `specs/001-patient-feedback-api/`:
- `spec.md` - Feature specification with user stories
- `plan.md` - Implementation roadmap
- `data-model.md` - Database schema documentation
- `contracts/` - API contract definitions
- `quickstart.md` - Getting started guide
- `deployment-analysis.md` - Production deployment architecture
