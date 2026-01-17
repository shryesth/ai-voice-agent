# Planning Context: Feature 001 - Patient Feedback Collection API

**Feature ID**: 001-patient-feedback-api
**Branch**: `001-patient-feedback-api`
**Planning Date**: 2026-01-18
**Status**: Planning Phase Complete, Ready for Implementation

---

## Overview

Successfully completed implementation planning for Patient Feedback Collection API - a FastAPI-based REST API server for AI-powered patient feedback collection via voice calls using Twilio and OpenAI Realtime Model.

---

## Planning Phase Artifacts Created

### Phase 0: Research & Technology Decisions
**File**: `specs/001-patient-feedback-api/research.md`

**Key Decisions**:
1. **Container Architecture**: Separate containers (API/Worker/Beat), reject supervisord "all" mode
2. **Resource Limits**: 2GB API, 1GB Worker with configurable overrides
3. **Secrets Management**: Docker secrets with env var fallback
4. **Startup Validation**: Fail-fast with optional bypass
5. **Health Checks**: Separate liveness/readiness with 5s caching
6. **Database Backups**: Automated daily backups with 7-day retention
7. **DLQ Monitoring**: Prometheus metrics with alerting
8. **Graceful Shutdown**: 30s timeout (configurable to 10min for voice calls)
9. **Rolling Updates**: Zero-downtime deployments with pre-deploy hooks
10. **Structured Logging**: JSON format with correlation IDs
11. **Network Segmentation**: Multi-network architecture (public/private/data)

**Philosophy**: "Secure Defaults with Escape Hatches" - all improvements configurable via environment variables

### Phase 1: Data Models
**File**: `specs/001-patient-feedback-api/data-model.md`

**Collections** (5 total):
1. **User** - Authentication with role-based access (Admin/User)
2. **Geography** - Regional organization with configurable retention policies
3. **Campaign** - Patient feedback campaigns with queue configuration
4. **CallRecord** - Individual calls with transcript and feedback data
5. **QueueEntry** - Campaign queue with intelligent retry logic

**Embedded Models** (8 total):
- RetentionPolicy, TimeWindow, CampaignConfig, CampaignStats
- FeedbackData, ConversationTurn, ConversationState, CallTracking, RetryHistory

**Enums** (7 total):
- UserRole, CampaignState, DayOfWeek, CallOutcome, ConversationStage, QueueState, FailureReason

**Technology**: Beanie ODM (MongoDB with Pydantic validation)

### Phase 1: API Contracts
**Directory**: `specs/001-patient-feedback-api/contracts/`

**Contract Files**:
1. **auth.md** - Authentication endpoints (login, /me, logout)
2. **health.md** - Health checks and metrics (live, ready, metrics, prometheus)
3. **geographies.md** - Geography CRUD operations
4. **campaigns.md** - Campaign management and state control
5. **calls.md** - Test calls, call records, urgent case management
6. **queue.md** - Queue monitoring and DLQ management
7. **README.md** - Contract overview and integration guide

**Total Endpoints**: 35+ REST API endpoints under `/api/v1/`

### Phase 1: Developer Guide
**File**: `specs/001-patient-feedback-api/quickstart.md`

**Contents**:
- Local development setup (Docker Compose)
- Environment configuration with all override options
- Basic workflow examples (create geography → campaign → test call)
- Testing instructions (contract, integration, unit tests)
- Production deployment guide (CapRover)
- Troubleshooting common issues
- Performance tuning recommendations

---

## Architecture Summary

### Technology Stack
- **Language**: Python 3.11+
- **API Framework**: FastAPI 0.128.0
- **Database**: MongoDB with Beanie 2.0.1 ODM
- **Queue System**: Celery + Redis
- **Voice Pipeline**: Pipecat-ai 0.0.99 + Twilio + OpenAI Realtime API
- **Testing**: Pytest 9.0.2 with async support
- **Deployment**: Docker containers + CapRover apps

### Clean Architecture Layers
1. **API Layer** (`backend/api/v1/`) - FastAPI route handlers
2. **Service Layer** (`backend/services/`) - Business logic
3. **Domain Layer** (`backend/domains/patient_feedback/`) - Voice-specific logic
4. **Infrastructure Layer** (`backend/models/`) - Beanie ODM models

### Deployment Architecture
```
Production (CapRover):
├── API Server Container (2 instances for rolling updates)
├── Celery Worker Container (1-N instances, scalable)
├── Celery Beat Container (1 instance, scheduler)
├── MongoDB Container (or managed MongoDB Atlas)
└── Redis Container (or managed Redis)

Networks:
├── public (API only, internet-facing)
├── private (API ↔ Workers, internal)
└── data (All ↔ MongoDB/Redis, isolated)
```

---

## User Stories & Priorities

**P1 (Critical)**:
- US1: API Server Infrastructure & Admin Authentication
- US4: Patient Feedback Collection via Voice Calls

**P2 (Enabler)**:
- US2: Geography & Campaign Project Setup
- US3: Test Call & Call Scenario Simulation

**P3 (Operational)**:
- US5: Call Campaign Queuing & Execution

**Implementation Order**: US1 → US2 → US4 → US3 → US5

---

## Key Requirements

### Functional Highlights (52 total)
- FR-001 to FR-007: API & Infrastructure (REST, auth, RBAC, health checks)
- FR-008 to FR-013: Geography & Campaign Management
- FR-014 to FR-017: Voice Call Testing
- FR-018 to FR-028: Patient Feedback Collection (6-stage conversation flow, 4 languages)
- FR-029 to FR-036: Campaign Queue & Scheduling (intelligent retry, DLQ)
- FR-037 to FR-042: Data Persistence (configurable retention per geography)
- FR-043 to FR-046: Error Handling & Logging
- FR-047 to FR-052: Observability (structured logs, Prometheus metrics, OpenTelemetry)

### Success Criteria (24 total)
**Performance**:
- API health check: <500ms (SC-001)
- Admin login: <2s (SC-002)
- Campaign creation: <30s (SC-003)
- Test call initiation: <10s (SC-004)
- Voice calls: <10min (SC-006)
- Campaign status query: <5s (SC-008)

**Data Accuracy**:
- 100% call logging (SC-009)
- 100% transcript capture (SC-010)
- 100% feedback recording (SC-011)
- 95% urgency flag accuracy (SC-012)

**Functionality**:
- 95% call connection rate (SC-005)
- 4 languages supported (SC-013)
- 100% failure classification (SC-015)
- Intelligent retry per failure type (SC-016)

---

## Retry Strategy & Queue Logic

### Retry Delays (per FailureReason)
- NO_ANSWER: 30 minutes
- BUSY: 1 hour
- FAILED: 15 minutes
- PERSON_NOT_AVAILABLE: 2 hours
- SHORT_DURATION: 1 hour
- NETWORK_FAILURE: 15 minutes
- TIMEOUT: 1 hour

### Non-Retriable (immediate DLQ)
- INVALID_NUMBER
- REJECTED

### Max Retry Attempts: 3 before DLQ

### Queue Scheduler
- **Frequency**: Every 30 seconds (Celery Beat)
- **Respects**: Time windows, max concurrent calls, retry timing
- **Handles**: Midnight-crossing time windows, day-of-week filtering

---

## Conversation Flow (6 Stages)

1. **Greeting** - AI introduces purpose of call
2. **Language Selection** - Patient selects preferred language (en/es/fr/ht)
3. **Patient Verification** - Confirm caller is appropriate respondent
4. **Feedback Collection** - Structured questions (satisfaction, concerns, side effects)
5. **Urgency Detection** - Keywords: hospital, severe, can't breathe, etc.
6. **Call Completion** - Thank patient, confirm data saved

**Max Retries per Stage**: 2 attempts before graceful progression

---

## Security & Privacy

### Authentication
- JWT tokens with HS256 algorithm
- 24-hour expiration
- Bcrypt password hashing (cost factor: 12)

### Role-Based Access Control
- **Admin**: Full CRUD access, campaign control, test calls, DLQ management
- **User**: Read-only access (view campaigns, calls, metrics)

### Data Protection
- Patient phone numbers hidden from User role
- API keys excluded from error messages
- Soft delete with `deleted_at` for audit trail
- Configurable retention policies per geography

### Network Security
- Multi-network Docker architecture
- MongoDB/Redis isolated from public network
- Twilio signature validation on webhooks

---

## Observability

### Logging
- **Format**: Structured JSON (production), text (development)
- **Correlation IDs**: call_sid, stream_sid, campaign_id in all logs
- **Levels**: DEBUG (dev), INFO (prod), ERROR (always)
- **Exclusions**: Phone numbers, API keys, passwords

### Metrics (Prometheus)
- `call_queue_depth{state}` - Queue entries by state
- `call_queue_dlq_count` - DLQ count
- `active_calls` - Current concurrent calls
- `call_duration_seconds` - Histogram of call durations
- `campaign_processing_rate` - Campaigns per minute

### Health Checks
- `/health` - Basic HTTP 200 (public)
- `/health/live` - Liveness probe (Kubernetes)
- `/health/ready` - Readiness probe with dependency checks
- `/metrics` - Custom JSON format (authenticated)
- `/metrics/prometheus` - Prometheus scrape endpoint

---

## Configuration Matrix

All improvements have configurable overrides:

| Feature | Default | Override Env Var | When to Override |
|---------|---------|------------------|------------------|
| Container Mode | Separate | ENABLE_SUPERVISOR_MODE=true | Local dev |
| Resource Limits | 2GB API, 1GB Worker | DOCKER_RESOURCE_LIMITS_ENABLED=false | Unlimited dev |
| Secrets | Docker secrets | USE_DOCKER_SECRETS=false | CI/CD |
| Startup Validation | Fail-fast | SKIP_STARTUP_VALIDATION=true | Testing |
| Health Check Deps | Check all | HEALTH_CHECK_DEPENDENCIES=false | Managed infra |
| Backups | Automated | ENABLE_AUTOMATED_BACKUPS=false | MongoDB Atlas |
| Metrics | Prometheus | ENABLE_PROMETHEUS_METRICS=false | Alt monitoring |
| Graceful Shutdown | 30s | GRACEFUL_SHUTDOWN_TIMEOUT=600 | Voice calls |
| Rolling Updates | Enabled | ENABLE_ROLLING_UPDATES=false | Non-prod |
| Logs | JSON | LOG_FORMAT=text | Local dev |
| Network Segmentation | 3 networks | ENABLE_NETWORK_SEGMENTATION=false | Simple dev |

---

## Reference Implementation Analysis

**Source**: `/Users/rohitkashyap/Workspace/voice-ai-reference-repo`

**Issues Identified** (10 major):
1. Supervisord anti-pattern (violates one-process-per-container)
2. No resource limits (can exhaust host resources)
3. Hardcoded credentials (security vulnerability)
4. No startup validation (fails on first request)
5. Aggressive health checks (hammers dependencies)
6. No build optimization (rebuilds deps on every code change)
7. Minimal CapRover config (no rolling updates)
8. No DLQ monitoring (failed calls silent)
9. No backup strategy (data loss risk)
10. Missing correlation IDs (can't trace requests)

**All issues addressed in current design** with configurable overrides.

---

## Next Steps

### Immediate (Ready Now)
1. ✅ Run `/speckit.tasks` command to generate `tasks.md` with implementation breakdown
2. ✅ Review generated tasks and prioritize by user story
3. ✅ Begin TDD workflow: Write tests first, then implementation

### Implementation Phase
1. **US1**: API Server & Auth (P1)
   - Set up FastAPI project structure
   - Implement Beanie ODM models
   - Create auth endpoints with JWT
   - Add health/metrics endpoints

2. **US2**: Geography & Campaign Setup (P2)
   - Implement geography CRUD
   - Implement campaign CRUD
   - Add campaign state machine

3. **US4**: Voice Feedback Collection (P1)
   - Integrate Pipecat voice pipeline
   - Implement 6-stage conversation flow
   - Add Twilio integration
   - Add OpenAI Realtime API integration

4. **US3**: Test Calls (P2)
   - Test call initiation endpoint
   - Test scenario simulation
   - Call record queries

5. **US5**: Campaign Queuing (P3)
   - Celery task implementation
   - Queue processor scheduler
   - Retry logic implementation
   - DLQ management

### Deployment Phase
1. Docker Compose for local development
2. CapRover deployment configuration
3. Production environment setup
4. Monitoring and alerting setup

---

## Testing Strategy

### Contract Tests
- All 35+ API endpoints
- Request/response schema validation
- Error handling (401, 403, 404, 409, 422)
- Role-based access control

### Integration Tests
- Voice pipeline end-to-end
- Twilio call simulation
- Queue processing with retries
- Database persistence

### Unit Tests
- Service layer business logic
- Queue retry calculations
- Conversation stage transitions
- Urgency keyword detection

---

## Documentation References

All planning artifacts in `specs/001-patient-feedback-api/`:

1. **spec.md** - Feature specification (5 user stories, 52 FRs, 24 SCs)
2. **plan.md** - Implementation plan with technical context
3. **research.md** - Technology decisions with override options
4. **deployment-analysis.md** - Critical analysis of reference repo
5. **data-model.md** - Beanie ODM models and database schema
6. **contracts/** - API contract specifications (35+ endpoints)
7. **quickstart.md** - Developer setup and deployment guide
8. **checklists/requirements.md** - Specification quality validation

---

## Constitution Compliance

All 5 core principles validated:

✅ **I. Specification-Driven Development** - Comprehensive spec.md with clarifications
✅ **II. Test-First Development (TDD)** - Testing strategy defined, contract tests ready
✅ **III. Independent User Story Implementation** - Stories prioritized and independently testable
✅ **IV. FastAPI Architectural Standards** - Clean architecture with 4 layers
✅ **V. Voice Agent Domain Excellence** - Pipecat pipeline, 6-stage flow, observability

**No violations** - Ready for implementation.

---

## Summary

**Planning Phase**: ✅ COMPLETE

**Artifacts Generated**: 8 major documents, 35+ API contracts, 5 data models, 7 enums

**Ready for**: Implementation phase with `/speckit.tasks` command

**Key Achievement**: Comprehensive planning with configurable architecture that learns from reference implementation issues while maintaining infrastructure flexibility through environment variable overrides.
