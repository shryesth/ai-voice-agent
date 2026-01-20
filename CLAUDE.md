# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Patient Feedback Collection API - an AI-powered voice call system for collecting patient feedback after medical appointments. Uses Twilio for telephony, OpenAI Realtime API for conversational AI, and Pipecat for voice pipeline orchestration.

## Development Commands

```bash
# Start all services (MongoDB, Redis, API, Celery worker, Celery beat)
docker compose -f docker-compose.dev.yml up

# Run API server locally (requires MongoDB and Redis running)
.venv/bin/python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 3000 --reload

# Install dependencies with uv
uv pip install -r requirements.txt

# Run tests with coverage
pytest

# Run specific test markers
pytest -m contract      # API contract tests
pytest -m integration   # Integration tests (voice pipeline)
pytest -m unit          # Unit tests
pytest -m voice         # Voice pipeline tests
pytest -m queue         # Queue processing tests

# Run single test file
pytest tests/contract/test_auth.py

# Run single test
pytest tests/contract/test_auth.py::test_login_success -v

# Linting and formatting
ruff check backend/
black backend/
mypy backend/
```

## Architecture

### Service Components
- **FastAPI Application** (`backend/app/main.py`): API server on port 3000
- **Celery Worker** (`backend/app/celery_app.py`): Async task processing for voice calls
- **Celery Beat**: Scheduler that runs queue processor every 30 seconds

### Directory Structure
```
backend/app/
├── api/v1/          # Route handlers (auth, health, geographies, campaigns, calls, queue)
├── core/            # Config, database, redis, security, logging
├── models/          # Beanie ODM models (User, Geography, Campaign, CallRecord, QueueEntry)
├── schemas/         # Pydantic request/response schemas
├── services/        # Business logic layer
├── tasks/           # Celery tasks (queue_processor, retry_handler, voice_call, recording_download, split_recording)
├── infrastructure/  # External service integrations (S3/MinIO storage)
└── domains/         # Domain-specific modules
    └── patient_feedback/  # Voice pipeline, Twilio integration, urgency detection, FlowManager
```

### Data Flow

**Call Initiation & Execution:**
1. Campaign created with patient phone list → QueueEntry records created
2. Celery Beat triggers `queue_processor` every 30s
3. Queue processor dequeues entries respecting concurrency limits
4. `voice_call` task initiates Twilio call with Pipecat voice pipeline
5. Twilio webhooks update CallRecord with status/transcript
6. Failed calls retry with backoff; max 3 attempts before Dead Letter Queue (DLQ)

**Recording Processing Pipeline:**
1. Call completes → Twilio webhook provides recording URL
2. `download_twilio_recording` task fetches MP3 from Twilio, uploads dual-channel recording to MinIO
3. `split_recording_task` downloads dual-channel MP3, splits into caller/callee/mixed mono tracks using pydub
4. Split tracks uploaded to MinIO with S3 keys cached in CallRecord.recording

### Key Technologies
- **Database**: MongoDB 8.0 with Beanie ODM 2.0.1 (uses `pymongo.AsyncMongoClient`)
- **Cache/Broker**: Redis 7 (Celery broker + result backend)
- **Voice Pipeline**: Pipecat v0.0.99 + custom FlowManager for conversation state machine
- **Telephony**: Twilio Media Streams (WebSocket)
- **AI Model**: OpenAI gpt-4o-realtime-preview
- **Storage**: S3/MinIO via boto3 for call recordings (supports both AWS S3 and self-hosted MinIO)
- **Audio Processing**: pydub for splitting dual-channel recordings into caller/callee/mixed tracks

### Database Connection
The database module (`backend/app/core/database.py`) performs fail-fast prechecks on startup:
1. **Connectivity check** - Pings MongoDB server
2. **Database access check** - Verifies database can be accessed
3. **Privileges check** - Verifies user permissions (read-only check)

If any precheck fails, the application exits immediately with a clear error message.

## Configuration

Settings loaded via Pydantic Settings from environment-specific files in `config/` directory:

### Environment Files
- **`config/.env.local`** - Local development with MinIO at localhost:9000 (gitignored, contains real credentials)
- **`config/.env.uat`** - UAT/staging environment (gitignored, create from `config/.env.uat.example`)
- **`config/.env.prod`** - Production environment (gitignored, create from `config/.env.prod.example`)
- **`config/.env.base`** - Base configuration template with all variables (tracked in git)
- **`config/.env.*.example`** - Environment templates with placeholders (tracked in git)

### Docker Compose Integration
- **Development**: `docker compose -f docker-compose.dev.yml up` uses `config/.env.local`
- **UAT/Staging**: `docker compose -f docker-compose.uat.yml up` uses `config/.env.uat`
- **Production**: `docker compose -f docker-compose.production.yml up` uses `config/.env.prod`

### Storage Configuration by Environment
- **Local**: MinIO at `http://localhost:9000` (bucket: `voice-recordings`)
- **UAT**: MinIO UAT or Hetzner Object Storage (bucket: `shifo-supervisor-uat`)
- **Production**: Hetzner Object Storage at `https://nbg1.your-objectstorage.com` (bucket: `shifo-supervisor`)

### Key Settings
- `MONGODB_URI` - MongoDB connection string (e.g., `mongodb://localhost:27017`)
- `MONGODB_DATABASE` - Database name (e.g., `voice_agent`)
- `ENVIRONMENT` - Environment name (development, staging, production)
- `PUBLIC_URL` - Public URL for Twilio webhooks (e.g., ngrok URL for local dev)
- `S3_ENDPOINT_URL` - Storage endpoint (MinIO or Hetzner)
- `S3_BUCKET_NAME` - Bucket for call recordings
- Required fields: `JWT_SECRET_KEY`, `TWILIO_*`, `OPENAI_API_KEY`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`

For detailed configuration documentation, see `config/README.md`.

## Testing

Tests organized by type:
- `tests/contract/` - API contract tests validating endpoint behavior
- `tests/integration/` - Integration tests for voice pipeline
- `tests/unit/` - Unit tests for models, services, tasks

Test fixtures in `tests/conftest.py` provide:
- `async_client` - HTTPX client for API testing
- `auth_headers` / `user_auth_headers` - JWT auth headers (admin/user roles)
- `test_db` - Isolated test database

Coverage threshold: 80% (enforced by pytest.ini)

## API Structure

All endpoints under `/api/v1/`:
- `/auth` - JWT authentication (login, logout, me)
- `/health`, `/health/ready`, `/health/live` - Health checks
- `/metrics`, `/metrics/prometheus` - Monitoring
- `/geographies` - Regional organization (Admin: create/update/delete)
- `/campaigns` - Campaign management with state machine (DRAFT→ACTIVE↔PAUSED→COMPLETED)
- `/calls` - Call records and transcripts
- `/queue` - Queue status and DLQ management (Admin only)

Role-based access: Admin has full access; User role has read-only with phone numbers redacted.

## Voice Pipeline Architecture

### FlowManager (State Machine)
The custom FlowManager (`backend/app/domains/patient_feedback/flow_manager.py`) replaces the imaginary pipecat-flows package with a local implementation:
- **NodeConfig**: Defines conversation stages with role/task messages and available LLM functions
- **FlowManager**: Manages conversation state transitions and provides function schemas to OpenAI Realtime API
- **FlowsFunctionSchema**: Converts function definitions to OpenAI tool calling format
- Used in `conversation_flow.py` to orchestrate multi-stage patient feedback collection

### Recording Storage
S3StorageClient (`backend/app/infrastructure/storage/s3_storage.py`) provides unified interface for both AWS S3 and MinIO:
- Automatically detects MinIO vs AWS based on `S3_ENDPOINT_URL` setting
- Supports upload, download, presigned URLs, and deletion
- Used by recording tasks to persist and retrieve call audio
