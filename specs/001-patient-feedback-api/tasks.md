# Tasks: Patient Feedback Collection API

**Input**: Design documents from `/specs/001-patient-feedback-api/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Contract tests for all API endpoints, integration tests for voice pipeline (per TDD constitution requirement)

**Organization**: Tasks grouped by user story to enable independent implementation and testing

---

## Format: `- [ ] [ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4, US5)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and directory structure

- [X] T001 Create project directory structure per plan.md (backend/app/, tests/, docker/, scripts/)
- [X] T002 Initialize Python 3.12.12 project with requirements.txt (FastAPI 0.128.0, Beanie 2.0.1, Celery, Pipecat-ai[silero] 0.0.99, pipecat-flows 0.0.10)
- [X] T003 [P] Create .env.example with all configuration variables from research.md
- [X] T004 [P] Configure pytest.ini for contract/integration/unit test organization
- [X] T005 [P] Create docker/Dockerfile.api for API server container (Python 3.12.12, MongoDB 8.0.17)
- [X] T006 [P] Create docker/Dockerfile.worker for Celery worker container (Python 3.12.12)
- [X] T007 [P] Create docker/Dockerfile.beat for Celery beat scheduler container (Python 3.12.12)
- [X] T008 Create docker-compose.dev.yml for local development (MongoDB 8.0.17, Redis, API, Worker, Beat)
- [X] T009 [P] Update .gitignore for Python project (added backups/, logs/, .env variants)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story implementation

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T010 Implement Pydantic Settings in backend/app/core/config.py (all env vars from research.md with validators)
- [X] T011 [P] Implement structured logging setup in backend/app/core/logging.py (JSON format, correlation IDs, sensitive data masking)
- [X] T012 [P] Implement Beanie database initialization in backend/app/core/database.py (MongoDB connection, init_beanie, ping health check)
- [X] T013 [P] Implement Redis client setup in backend/app/core/redis.py (connection pool, get/set/delete/exists methods)
- [X] T014 [P] Implement JWT security utilities in backend/app/core/security.py (create_token, decode_token, verify_password with bcrypt)
- [X] T015 Create FastAPI app factory in backend/app/main.py (lifespan context, startup validation, exception handlers, CORS)
- [X] T016 [P] Create Celery app configuration in backend/app/celery_app.py (Redis broker, beat schedule for queue processor)
- [X] T017 [P] Create base Pydantic schemas in backend/app/schemas/__init__.py (MessageResponse, ErrorResponse)
- [X] T018 Create scripts/create_admin.py for seeding initial admin user (with argparse CLI)

**Checkpoint**: ✅ Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - API Server Infrastructure & Admin Authentication (Priority: P1) 🎯 MVP

**Goal**: Secure REST API backend with health checks, authentication, and role-based access control

**Independent Test**: Verify admin login, token validation, protected endpoint access control, health/metrics endpoints responding

### Contract Tests for User Story 1

> **TDD Requirement**: Write these tests FIRST, ensure they FAIL before implementation

- [X] T019 [P] [US1] Contract test for POST /api/v1/auth/login in tests/contract/test_auth.py
- [X] T020 [P] [US1] Contract test for GET /api/v1/auth/me in tests/contract/test_auth.py
- [X] T021 [P] [US1] Contract test for GET /api/v1/health endpoints in tests/contract/test_health.py
- [X] T022 [P] [US1] Contract test for GET /api/v1/metrics endpoints in tests/contract/test_health.py

### Implementation for User Story 1

**Models:**
- [X] T023 [US1] Create User model with UserRole enum in backend/app/models/user.py (Beanie Document, email index)

**Schemas:**
- [X] T024 [P] [US1] Create auth request/response schemas in backend/app/schemas/auth.py (LoginRequest, LoginResponse, UserResponse)

**Services:**
- [X] T025 [US1] Implement AuthService in backend/app/services/auth_service.py (login, verify_password, create_user)

**API Endpoints:**
- [X] T026 [US1] Implement POST /api/v1/auth/login in backend/app/api/v1/auth.py (authenticate user, return JWT)
- [X] T027 [US1] Implement GET /api/v1/auth/me in backend/app/api/v1/auth.py (get current user from token)
- [X] T028 [US1] Implement authentication dependency in backend/app/api/v1/auth.py (get_current_user, require_admin)
- [X] T029 [P] [US1] Implement GET /api/v1/health endpoints in backend/app/api/v1/health.py (live, ready with dependency checks)
- [X] T030 [P] [US1] Implement GET /api/v1/metrics endpoints in backend/app/api/v1/health.py (JSON format, Prometheus export)

**Infrastructure:**
- [X] T031 [US1] Register all US1 routes in backend/app/main.py (/auth, /health, /metrics)
- [X] T032 [US1] Add RBAC middleware for Admin/User role enforcement in backend/app/api/v1/auth.py

**Checkpoint**: At this point, User Story 1 should be fully functional - admin can login, access protected endpoints, view health/metrics

---

## Phase 4: User Story 2 - Geography & Campaign Project Setup (Priority: P2)

**Goal**: Regional organization with configurable retention policies and campaign management

**Independent Test**: Create geographies, create campaigns within geographies, verify configurations persisted, filter campaigns by geography

### Contract Tests for User Story 2

- [X] T033 [P] [US2] Contract test for geography CRUD endpoints in tests/contract/test_geographies.py
- [X] T034 [P] [US2] Contract test for campaign CRUD endpoints in tests/contract/test_campaigns.py
- [X] T035 [P] [US2] Contract test for campaign state transitions in tests/contract/test_campaigns.py

### Implementation for User Story 2

**Models:**
- [X] T036 [P] [US2] Create Geography model with RetentionPolicy in backend/app/models/geography.py (soft delete, retention config)
- [X] T037 [P] [US2] Create Campaign model with CampaignConfig in backend/app/models/campaign.py (state machine, time windows, queue config)

**Schemas:**
- [X] T038 [P] [US2] Create geography request/response schemas in backend/app/schemas/geography.py (GeographyCreate, GeographyResponse)
- [X] T039 [P] [US2] Create campaign request/response schemas in backend/app/schemas/campaign.py (CampaignCreate, CampaignResponse, TimeWindow, CampaignStats)

**Services:**
- [X] T040 [US2] Implement GeographyService in backend/app/services/geography_service.py (CRUD operations, soft delete)
- [X] T041 [US2] Implement CampaignService in backend/app/services/campaign_service.py (CRUD, state machine: start/pause/resume/cancel)

**API Endpoints:**
- [X] T042 [P] [US2] Implement geography endpoints in backend/app/api/v1/geographies.py (POST, GET list, GET by ID, PATCH, DELETE)
- [X] T043 [P] [US2] Implement campaign endpoints in backend/app/api/v1/campaigns.py (POST under geography, GET list, GET by ID, PATCH)
- [X] T044 [US2] Implement campaign state control endpoints in backend/app/api/v1/campaigns.py (POST /start, /pause, /resume, /cancel)
- [X] T045 [US2] Implement GET /api/v1/campaigns/{id}/status in backend/app/api/v1/campaigns.py (real-time progress tracking)

**Infrastructure:**
- [X] T046 [US2] Register geography and campaign routes in backend/app/main.py

**Checkpoint**: Geographies and campaigns can be created, state transitions work, filtering by geography works

---

## Phase 5: User Story 4 - Patient Feedback Collection via Voice Calls (Priority: P1)

**Goal**: AI-powered voice calls with 6-stage conversation flow, multilingual support, urgency detection

**Independent Test**: Initiate call, complete full conversation flow (greeting → language → verification → feedback → urgency → completion), verify feedback stored with transcript

**Note**: Implementing US4 before US3 because US4 is P1 (core feature) and US3 is P2 (test utilities)

### Integration Tests for User Story 4

- [ ] T047 [P] [US4] Integration test for Pipecat voice pipeline in tests/integration/test_voice_pipeline.py (full 6-stage flow)
- [ ] T048 [P] [US4] Integration test for Twilio integration in tests/integration/test_voice_pipeline.py (call initiation, webhook handling)
- [ ] T049 [P] [US4] Integration test for urgency detection in tests/integration/test_voice_pipeline.py (keyword matching)

### Implementation for User Story 4

**Models:**
- [X] T050 [US4] Create CallRecord model in backend/app/models/call_record.py (FeedbackData, ConversationState, CallTracking, urgency flags)

**Schemas:**
- [X] T051 [P] [US4] Create call request/response schemas in backend/app/schemas/call.py (CallRecordResponse, FeedbackDataResponse, ConversationStateResponse)

**Domain Logic (Voice Pipeline):**
- [X] T052 [P] [US4] Implement conversation flow state machine in backend/app/domains/patient_feedback/conversation_flow.py with 6 stage NodeConfig functions (create_greeting_node, create_language_selection_node, create_verification_node, create_feedback_node, create_urgency_detection_node, create_completion_node) using pipecat-flows FlowManager pattern. Each NodeConfig must include: (1) role_messages list defining system identity, (2) task_messages list with stage-specific instructions, (3) functions list with FlowsFunctionSchema having properties dict + required list (NOT parameters dict), (4) handler with signature async def handler(args: FlowArgs, flow_manager: FlowManager) returning (FlowResult, next_node), (5) FlowResult base classes (GreetingResult, LanguageResult, VerificationResult, FeedbackResult, UrgencyResult, CompletionResult) with typed fields
- [X] T053 [P] [US4] Implement urgency keyword detector in backend/app/domains/patient_feedback/urgency_detector.py (hospital, severe, can't breathe, etc.)
- [X] T054 [US4] Implement Twilio integration in backend/app/domains/patient_feedback/twilio_integration.py (initiate outbound calls via Twilio API, parse WebSocket "start" event, extract call_sid/stream_sid, handle status webhooks with signature validation) using FastAPIWebsocketTransport + TwilioFrameSerializer for ALL audio conversion (µ-law 8kHz ↔ PCM 16kHz)
- [X] T055 [US4] Implement Pipecat v0.0.99 voice pipeline orchestration in backend/app/domains/patient_feedback/voice_pipeline.py with create_voice_pipeline(websocket, call_record_id, call_data) function implementing: (1) TwilioFrameSerializer initialization with stream_sid/call_sid, (2) FastAPIWebsocketTransport with Silero VAD, (3) OpenAIRealtimeLLMService with language-specific voice, (4) LLMContext with initial system message, (5) LLMContextAggregatorPair with VADUserTurnStartStrategy + TranscriptionUserTurnStopStrategy + MuteUntilFirstBotCompleteUserMuteStrategy + FunctionCallUserMuteStrategy, (6) FlowManager initialization with create_greeting_node(), (7) Pipeline assembly in correct order: transport.input() → user_aggregator → llm_service → transport.output() → assistant_aggregator, (8) PipelineTask with PipelineParams (no allow_interruptions parameter), (9) Return flow_manager.state for CallRecord persistence

**Services:**
- [X] T056 [US4] Implement CallService in backend/app/services/call_service.py (create call record, query calls, export CSV)

**Celery Tasks:**
- [X] T057 [US4] Implement voice call task in backend/app/tasks/voice_call.py (initiate_patient_call, integrate with Pipecat pipeline)

**API Endpoints:**
- [X] T058 [US4] Implement GET /api/v1/calls/{id} in backend/app/api/v1/calls.py (get call record with full transcript)
- [X] T059 [P] [US4] Implement GET /api/v1/campaigns/{id}/calls in backend/app/api/v1/calls.py (list calls with filtering)
- [X] T060 [P] [US4] Implement GET /api/v1/calls/urgent in backend/app/api/v1/calls.py (urgent-flagged calls for clinical review)
- [X] T061 [P] [US4] Implement POST /api/v1/webhooks/twilio/status in backend/app/api/v1/calls.py (Twilio status callback with signature validation)

**Infrastructure:**
- [X] T062 [US4] Register call routes and webhooks in backend/app/main.py
- [X] T063 [US4] Add multilingual support configuration (en, es, fr, ht) in backend/app/core/config.py

**Checkpoint**: Voice calls work end-to-end, full conversation flow completes, transcripts and feedback saved, urgency detection functional

---

## Phase 6: User Story 3 - Test Call & Call Scenario Simulation (Priority: P2)

**Goal**: Test call endpoints for validating voice pipeline before production campaigns

**Independent Test**: Initiate test call, simulate conversation scenarios, verify call metadata logged

### Contract Tests for User Story 3

- [ ] T064 [P] [US3] Contract test for POST /api/v1/campaigns/{id}/calls/test in tests/contract/test_calls.py
- [ ] T065 [P] [US3] Contract test for POST /api/v1/campaigns/{id}/calls/test-scenario in tests/contract/test_calls.py

### Implementation for User Story 3

**Schemas:**
- [X] T066 [P] [US3] Create test call request schemas in backend/app/schemas/call.py (TestCallRequest, TestScenarioRequest with TestScenario enum)

**Services:**
- [X] T067 [US3] Add test call methods to CallService in backend/app/services/call_service.py (initiate_test_call, simulate_scenario)

**API Endpoints:**
- [X] T068 [US3] Implement POST /api/v1/campaigns/{id}/calls/test in backend/app/api/v1/calls.py (initiate test call, bypass queue)
- [X] T069 [US3] Implement POST /api/v1/campaigns/{id}/calls/test-scenario in backend/app/api/v1/calls.py (simulate scenarios: happy_path, wrong_person, urgent_keywords, etc.)
- [X] T070 [US3] Implement GET /api/v1/campaigns/{id}/calls/export in backend/app/api/v1/calls.py (CSV export, Admin only)

**Checkpoint**: Test calls can be initiated, scenarios simulated, call metadata queryable

---

## Phase 7: User Story 5 - Call Campaign Queuing & Execution (Priority: P3)

**Goal**: Automated bulk campaign execution with intelligent retry logic and DLQ management

**Independent Test**: Create campaign with patient list, start campaign, verify queue processing, test retry logic and DLQ routing

### Contract Tests for User Story 5

- [ ] T071 [P] [US5] Contract test for queue endpoints in tests/contract/test_queue.py (GET queue status, DLQ management)

### Integration Tests for User Story 5

- [ ] T072 [P] [US5] Integration test for queue processor in tests/integration/test_queue_processor.py (30s scheduler, time window enforcement)
- [ ] T073 [P] [US5] Integration test for retry logic in tests/integration/test_retry_logic.py (per-failure-reason delays, max 3 attempts)

### Implementation for User Story 5

**Models:**
- [X] T074 [US5] Create QueueEntry model in backend/app/models/queue_entry.py (retry tracking, state machine, DLQ flags, RetryHistory)

**Schemas:**
- [X] T075 [P] [US5] Create queue request/response schemas in backend/app/schemas/queue.py (QueueEntryResponse, DLQResponse, RetryHistoryResponse)

**Services:**
- [X] T076 [US5] Implement QueueService in backend/app/services/queue_service.py (create queue entries, retry logic, DLQ routing)

**Celery Tasks:**
- [X] T077 [US5] Implement queue processor task in backend/app/tasks/queue_processor.py (process_campaign_queues every 30s, respect time windows and concurrency)
- [X] T078 [US5] Implement retry handler task in backend/app/tasks/retry_handler.py (calculate retry delays per FailureReason, max 3 attempts before DLQ)
- [X] T079 [US5] Configure Celery Beat schedule in backend/app/celery_app.py (queue processor every 30s)

**API Endpoints:**
- [X] T080 [P] [US5] Implement GET /api/v1/campaigns/{id}/queue in backend/app/api/v1/queue.py (queue status with summary stats)
- [X] T081 [P] [US5] Implement GET /api/v1/queue/dlq in backend/app/api/v1/queue.py (Dead Letter Queue entries, Admin only)
- [X] T082 [P] [US5] Implement POST /api/v1/queue/dlq/{id}/retry in backend/app/api/v1/queue.py (manual retry, Admin only)
- [X] T083 [P] [US5] Implement DELETE /api/v1/queue/dlq/{id} in backend/app/api/v1/queue.py (remove from DLQ, Admin only)
- [X] T084 [P] [US5] Implement GET /api/v1/queue/stats in backend/app/api/v1/queue.py (global queue statistics, Admin only)

**Infrastructure:**
- [X] T085 [US5] Register queue routes in backend/app/main.py
- [X] T086 [US5] Update CampaignService.start() to create QueueEntry for each patient in backend/app/services/campaign_service.py

**Checkpoint**: Campaign queues process automatically, retry logic works per failure type, DLQ collects exhausted retries

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Production readiness, deployment configuration, documentation

- [ ] T087 [P] Create docker-compose.production.yml with resource limits, network segmentation, health checks
- [ ] T088 [P] Create captain-definition.json for CapRover deployment (rolling updates, pre-deploy hooks)
- [ ] T089 [P] Create scripts/migrate_db.py for database migrations (if needed)
- [ ] T090 [P] Create scripts/backup_db.sh for automated MongoDB backups
- [ ] T091 [P] Add unit tests for services in tests/unit/test_services/ (AuthService, GeographyService, CampaignService, CallService, QueueService)
- [ ] T092 [P] Add unit tests for models in tests/unit/test_models/ (Pydantic validation, enum constraints)
- [ ] T093 [P] Add unit tests for Celery tasks in tests/unit/test_tasks/ (queue_processor, voice_call, retry_handler)
- [ ] T094 Add Prometheus alert rules in prometheus-alerts.yml (DLQ count > 10, queue depth, error rate)
- [ ] T095 [P] Add CORS configuration for production in backend/app/main.py
- [ ] T096 Run quickstart.md validation (local dev setup, test calls, campaign execution)
- [ ] T097 Add API documentation with examples in backend/app/main.py (OpenAPI tags, descriptions)
- [ ] T098 Security audit: verify no secrets in logs, phone number redaction for User role, Twilio signature validation

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - start immediately
- **Foundational (Phase 2)**: Depends on Setup - BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends on Foundational - MVP foundation
- **User Story 2 (Phase 4)**: Depends on Foundational + US1 (uses User model for auth)
- **User Story 4 (Phase 5)**: Depends on Foundational + US2 (needs Campaign model) - Core feature
- **User Story 3 (Phase 6)**: Depends on Foundational + US2 + US4 (needs Campaign and CallRecord models)
- **User Story 5 (Phase 7)**: Depends on Foundational + US2 + US4 (needs Campaign, CallRecord, queue infrastructure)
- **Polish (Phase 8)**: Depends on all desired user stories

### User Story Independence

Each user story delivers independently testable value:
- **US1**: Admin can login, access protected endpoints, view health/metrics → Deployable as API infrastructure
- **US2**: Admin can create geographies and campaigns → Adds campaign management
- **US4**: Voice calls work end-to-end with feedback collection → Core feature functional
- **US3**: Admin can test voice pipeline before production → Adds validation tooling
- **US5**: Bulk campaigns execute automatically with retries → Production automation

### Within Each User Story

1. Tests FIRST (write, ensure they FAIL)
2. Models (can be parallel if different files)
3. Schemas (parallel with models)
4. Services (depend on models)
5. API Endpoints (depend on services)
6. Integration with other components
7. Story complete, independently testable

### Parallel Opportunities

**Setup Phase (Phase 1)**:
- T003, T004, T005, T006, T007, T009 can all run in parallel (different files)

**Foundational Phase (Phase 2)**:
- T011, T012, T013, T014, T016, T017 can run in parallel (different files)

**User Story 1**:
- Contract tests: T019, T020, T021, T022 (parallel)
- Schemas: T024 (parallel with model T023 after model exists)
- API endpoints: T029, T030 (parallel, different concerns)

**User Story 2**:
- Contract tests: T033, T034, T035 (parallel)
- Models: T036, T037 (parallel)
- Schemas: T038, T039 (parallel)
- API endpoints: T042, T043 (parallel)

**User Story 4**:
- Integration tests: T047, T048, T049 (parallel)
- Schemas: T051 (parallel with model)
- Domain logic: T052, T053 (parallel, different concerns)
- API endpoints: T059, T060, T061 (parallel)

**User Story 3**:
- Contract tests: T064, T065 (parallel)
- Schemas: T066 (parallel with service)

**User Story 5**:
- Contract tests: T071, T072, T073 (parallel)
- Schemas: T075 (parallel with model)
- API endpoints: T080, T081, T082, T083, T084 (parallel)

**Polish Phase**:
- T087, T088, T089, T090, T091, T092, T093, T095 can all run in parallel

---

## Parallel Example: User Story 1 (MVP)

```bash
# After Foundational phase complete, launch US1 tests in parallel:
Task T019: "Contract test for POST /api/v1/auth/login"
Task T020: "Contract test for GET /api/v1/auth/me"
Task T021: "Contract test for GET /api/v1/health"
Task T022: "Contract test for GET /api/v1/metrics"

# After tests written and failing, launch models and schemas in parallel:
Task T023: "Create User model in backend/app/models/user.py"
Task T024: "Create auth schemas in backend/app/schemas/auth.py"

# After models and schemas complete, implement service:
Task T025: "Implement AuthService in backend/app/services/auth_service.py"

# After service complete, launch API endpoints in parallel:
Task T026: "Implement POST /api/v1/auth/login"
Task T027: "Implement GET /api/v1/auth/me"
Task T028: "Implement auth dependencies"
Task T029: "Implement GET /api/v1/health endpoints"
Task T030: "Implement GET /api/v1/metrics endpoints"

# Sequential registration:
Task T031: "Register US1 routes in main.py"
Task T032: "Add RBAC middleware"
```

---

## Parallel Example: User Story 4 (Voice Calls)

```bash
# After US2 complete, launch US4 integration tests in parallel:
Task T047: "Integration test for voice pipeline (6-stage flow)"
Task T048: "Integration test for Twilio integration"
Task T049: "Integration test for urgency detection"

# After tests written and failing, launch model and schemas in parallel:
Task T050: "Create CallRecord model"
Task T051: "Create call schemas"

# Launch domain logic in parallel (different concerns):
Task T052: "Implement conversation flow state machine"
Task T053: "Implement urgency keyword detector"

# Sequential: Twilio integration depends on conversation flow:
Task T054: "Implement Twilio integration"

# Sequential: Pipecat pipeline orchestrates all components:
Task T055: "Implement Pipecat voice pipeline orchestration"

# After pipeline ready, implement service:
Task T056: "Implement CallService"

# Implement Celery task:
Task T057: "Implement voice call task"

# Launch API endpoints in parallel:
Task T058: "Implement GET /api/v1/calls/{id}"
Task T059: "Implement GET /api/v1/campaigns/{id}/calls"
Task T060: "Implement GET /api/v1/calls/urgent"
Task T061: "Implement POST /api/v1/webhooks/twilio/status"

# Sequential registration:
Task T062: "Register call routes in main.py"
Task T063: "Add multilingual support config"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

**Minimum Viable Product**: API server with authentication and health checks

1. Complete **Phase 1: Setup** (T001-T009) → Project structure ready
2. Complete **Phase 2: Foundational** (T010-T018) → Core infrastructure ready
3. Complete **Phase 3: User Story 1** (T019-T032) → Admin can login, access protected endpoints
4. **STOP and VALIDATE**: Test US1 independently
   - Admin login works
   - Token validation works
   - Health checks respond
   - Metrics endpoint works
5. Deploy/demo if ready

**Deliverable**: Secure API foundation for all future features

---

### Incremental Delivery (Recommended)

**Each user story adds value without breaking previous stories**

1. **Foundation** (Phases 1-2) → T001-T018
   - Project structure
   - Core infrastructure (database, auth, logging, config)
   - **Checkpoint**: Foundation ready for any user story

2. **MVP: API Infrastructure** (Phase 3) → T019-T032
   - User Story 1: Authentication, health checks, metrics
   - **Checkpoint**: Admin can login, API responds
   - **Deployable**: Secure API foundation

3. **Campaign Management** (Phase 4) → T033-T046
   - User Story 2: Geography and campaign setup
   - **Checkpoint**: Geographies and campaigns can be created
   - **Deployable**: Campaign organization ready for voice calls

4. **Core Feature: Voice Calls** (Phase 5) → T047-T063
   - User Story 4: Patient feedback collection via voice
   - **Checkpoint**: End-to-end voice calls work with feedback stored
   - **Deployable**: Core patient feedback feature functional

5. **Testing Tools** (Phase 6) → T064-T070
   - User Story 3: Test calls and scenario simulation
   - **Checkpoint**: Admins can validate voice pipeline before production
   - **Deployable**: Complete testing capability

6. **Production Automation** (Phase 7) → T071-T086
   - User Story 5: Bulk campaign queuing and execution
   - **Checkpoint**: Campaigns run automatically with retries
   - **Deployable**: Full production system

7. **Production Polish** (Phase 8) → T087-T098
   - Deployment configs, additional tests, security audit
   - **Checkpoint**: Production-ready system

---

### Parallel Team Strategy

**With multiple developers, maximize parallelism**

**Phase 1-2: Together** (Foundation)
- All developers collaborate on Setup and Foundational phases
- Critical: Everyone understands core infrastructure

**Phase 3+: Parallel User Stories** (after Foundation complete)
- **Developer A**: User Story 1 (T019-T032) - API infrastructure
- **Developer B**: User Story 2 (T033-T046) - Campaign management (starts after US1 auth ready)
- **Developer C**: Setup for User Story 4 - Begin domain logic research

**After US1 and US2 complete:**
- **Developer A**: User Story 4 (T047-T063) - Voice calls
- **Developer B**: User Story 3 (T064-T070) - Test calls
- **Developer C**: User Story 5 (T071-T086) - Queue automation

**Integration:**
- Stories integrate cleanly via API contracts
- Each story independently testable
- No merge conflicts (different files)

---

## Task Summary

**Total Tasks**: 98

**Breakdown by Phase**:
- Phase 1 (Setup): 9 tasks
- Phase 2 (Foundational): 9 tasks (BLOCKING)
- Phase 3 (US1 - API Infrastructure): 14 tasks → **MVP**
- Phase 4 (US2 - Geography/Campaign): 14 tasks
- Phase 5 (US4 - Voice Calls): 17 tasks → **Core Feature**
- Phase 6 (US3 - Test Calls): 7 tasks
- Phase 7 (US5 - Queue Automation): 16 tasks → **Production Ready**
- Phase 8 (Polish): 12 tasks

**Parallel Opportunities**: 42 tasks marked [P] can run in parallel within their phase

**Independent Test Criteria**:
- **US1**: Admin login + token validation + health checks → API infrastructure validated
- **US2**: Geography creation + campaign creation + filtering → Campaign management validated
- **US4**: End-to-end voice call + full conversation flow + feedback stored → Core feature validated
- **US3**: Test call initiation + scenario simulation + call metadata logged → Testing tools validated
- **US5**: Campaign queue processing + retry logic + DLQ routing → Automation validated

**Suggested MVP Scope**: Phases 1-3 (T001-T032) → Secure API with authentication

**Recommended Delivery Order**: Foundation → US1 (MVP) → US2 → US4 (Core) → US3 → US5 → Polish

---

## Notes

- **[P] tasks**: Different files, can run in parallel within phase
- **[Story] label**: Maps task to specific user story for traceability
- **TDD Requirement**: All contract/integration tests written FIRST, must FAIL before implementation
- **File paths**: All paths are exact (backend/app/..., tests/...) per plan.md structure
- **Checkpoints**: Stop after each user story to validate independently
- **Commits**: Commit after each task or logical group of parallel tasks
- **Constitution compliance**: Follows TDD, independent user stories, FastAPI standards, voice agent excellence
