# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Patient Feedback Collection API - an AI-powered voice call system for collecting patient feedback after medical appointments. Uses Twilio for telephony, OpenAI Realtime API for conversational AI, and Pipecat for voice pipeline orchestration.

## Development Commands

```bash
# Start all services (MongoDB, Redis, API, Celery worker, Celery beat)
docker compose -f docker-compose.dev.yml up

# Run API server locally (requires MongoDB and Redis running)
uvicorn backend.app.main:app --host 0.0.0.0 --port 3000 --reload

# Run tests with coverage
pytest

# Run specific test markers
pytest -m contract      # API contract tests
pytest -m integration   # Integration tests (voice pipeline)
pytest -m unit          # Unit tests

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
├── tasks/           # Celery tasks (queue_processor, retry_handler, voice_call)
└── domains/         # Domain-specific modules
    └── patient_feedback/  # Voice pipeline, Twilio integration, urgency detection
```

### Data Flow
1. Campaign created with patient phone list → QueueEntry records created
2. Celery Beat triggers `queue_processor` every 30s
3. Queue processor dequeues entries respecting concurrency limits
4. `voice_call` task initiates Twilio call with Pipecat voice pipeline
5. Twilio webhooks update CallRecord with status/transcript
6. Failed calls retry with backoff; max 3 attempts before Dead Letter Queue (DLQ)

### Key Technologies
- **Database**: MongoDB 8.0 with Beanie ODM
- **Cache/Broker**: Redis 7 (Celery broker + result backend)
- **Voice Pipeline**: Pipecat v0.0.99 + pipecat-flows for conversation state machine
- **Telephony**: Twilio Media Streams (WebSocket)
- **AI Model**: OpenAI gpt-4o-realtime-preview

## Configuration

Settings loaded via Pydantic Settings from `.env` file (see `.env.example`). Key settings:
- `SKIP_STARTUP_VALIDATION=true` - Skip config validation for tests
- Required fields: `JWT_SECRET_KEY`, `TWILIO_*`, `OPENAI_API_KEY`

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
