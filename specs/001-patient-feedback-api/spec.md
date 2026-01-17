# Feature Specification: Patient Feedback Collection API

**Feature Branch**: `001-patient-feedback-api`
**Created**: 2026-01-17
**Status**: Draft
**Input**: Initialise a FastAPI REST API server with admin authentication, geography/project management, and AI-powered patient feedback collection via voice calls using Twilio integration

## User Scenarios & Testing *(mandatory)*

### User Story 1 - API Server Infrastructure & Admin Authentication (Priority: P1)

Platform administrators need a secure REST API backend with health checks and access control so they can manage campaigns and patient data.

**Why this priority**: P1 is critical - all other features depend on a running, authenticated API server. Without this infrastructure, no other functionality is accessible.

**Independent Test**: Can be fully tested by verifying admin login, authentication token validation, protected endpoint access control, delivering a secure API foundation.

**Acceptance Scenarios**:

1. **Given** admin credentials are registered, **When** admin calls `POST /api/v1/auth/login` with credentials, **Then** receives authentication token valid for 24 hours
2. **Given** valid authentication token, **When** admin calls `GET /api/v1/health` with token header, **Then** receives 200 OK with server status
3. **Given** invalid or expired token, **When** admin calls any protected endpoint, **Then** receives 401 Unauthorized
4. **Given** no authentication header, **When** admin calls protected endpoint, **Then** receives 401 Unauthorized

---

### User Story 2 - Geography & Campaign Project Setup (Priority: P2)

Operations managers need to organize patient feedback campaigns by geography and create campaigns within those regions so they can manage multi-location operations.

**Why this priority**: P2 enables regional organization of patient feedback collection. Once the API server is running, managers can create regional scopes for campaigns.

**Independent Test**: Can be fully tested by creating geographies, creating feedback collection campaigns within geographies, and verifying campaign configurations are persisted, delivering geography-scoped campaign management.

**Acceptance Scenarios**:

1. **Given** authenticated admin, **When** calls `POST /api/v1/geographies`, **Then** can create new geography with name and region metadata
2. **Given** existing geography, **When** admin calls `POST /api/v1/geographies/{geo-id}/campaigns`, **Then** can create feedback collection campaign with name and configuration
3. **Given** existing campaign, **When** admin calls `GET /api/v1/campaigns/{campaign-id}`, **Then** receives complete campaign configuration including time windows and concurrency limits
4. **Given** multiple campaigns, **When** admin filters by geography, **Then** receives only campaigns in that geography

---

### User Story 3 - Test Call & Call Scenario Simulation (Priority: P2)

Campaign managers need to verify the voice system works before launching patient campaigns. This requires endpoints to place test calls and simulate different conversation scenarios.

**Why this priority**: P2 - once campaigns exist, managers need validation endpoints to test the voice pipeline before running production campaigns.

**Independent Test**: Can be fully tested by calling test endpoints with phone numbers, simulating conversation scenarios, verifying calls are logged with metadata, delivering call validation capability.

**Acceptance Scenarios**:

1. **Given** authenticated admin with campaign access, **When** calls `POST /api/v1/campaigns/{campaign-id}/calls/test`, **Then** system initiates call to test phone number and returns call status
2. **Given** completed test call, **When** admin queries `GET /api/v1/campaigns/{campaign-id}/calls/{call-id}`, **Then** receives call metadata including duration, transcript, outcome, and any errors
3. **Given** valid campaign context, **When** admin calls `POST /api/v1/campaigns/{campaign-id}/calls/test-scenario`, **Then** can specify language and simulate conversation path (e.g., patient identifies as wrong person, reports side effects)
4. **Given** test call with error or edge case, **When** call completes, **Then** system captures error reason and logs with full context for debugging

---

### User Story 4 - Patient Feedback Collection via Voice Calls (Priority: P1)

Patients receive phone calls where an AI agent collects structured feedback about their medical experience, and the system records responses for clinical review.

**Why this priority**: P1 - this is the core feature delivering patient feedback collection value. Without this, the entire system has no purpose.

**Independent Test**: Can be fully tested by initiating a call, going through full conversation flow (verification → feedback collection → urgency detection), completing successfully, and verifying feedback is stored, delivering end-to-end feedback collection.

**Acceptance Scenarios**:

1. **Given** patient answers call in preferred language, **When** AI greeting plays, **Then** patient can respond in natural language and system understands context
2. **Given** AI asks for patient verification, **When** patient provides confirmation, **Then** system verifies identity or notes if different person answered
3. **Given** verification complete, **When** AI collects feedback questions, **Then** system records responses for: overall satisfaction, specific concerns, side effects (if applicable), experience quality
4. **Given** patient reports concerning symptoms or low satisfaction, **When** AI completes call, **Then** system flags response for urgent clinical review
5. **Given** conversation complete, **When** patient or AI ends call, **Then** system saves complete transcript, metadata, and outcome with timestamp

---

### User Story 5 - Call Campaign Queuing & Execution (Priority: P3)

Campaign managers need to queue bulk patient feedback campaigns that run automatically according to time windows and concurrency limits, so campaigns execute reliably overnight or during off-peak hours.

**Why this priority**: P3 - represents production campaign automation. Managers can launch large-scale campaigns after validating the system with individual test calls.

**Independent Test**: Can be fully tested by creating campaign queue with patient list, starting campaign, monitoring processing, verifying calls are placed and tracked, delivering bulk campaign execution.

**Acceptance Scenarios**:

1. **Given** campaign configuration and patient phone list, **When** admin creates campaign, **Then** system queues all calls for processing
2. **Given** active campaign, **When** campaign queue scheduler runs, **Then** places calls within time window (e.g., 9am-5pm) and concurrency limits (e.g., max 10 concurrent calls)
3. **Given** campaign in progress, **When** admin queries campaign status, **Then** receives breakdown of call states: queued, in-progress, completed, failed, urgent-flag
4. **Given** call fails (e.g., no answer, network issue), **When** failure reason is determined, **Then** system schedules intelligent retry (e.g., no-answer retries after 30min, busy retries after 1hr)

---

### Edge Cases

- **Wrong person answers**: If patient verification fails 2 times, system marks "wrong_person" and stops, offers callback to reach actual patient
- **Severe side effects reported**: AI detects keywords indicating urgent medical concern (e.g., "hospital", "severe", "can't breathe") and flags for immediate clinical review
- **Network/Twilio failure mid-call**: Call disconnects during conversation; system logs partial transcript and schedules intelligent retry based on duration
- **Time window edge case**: If campaign time window is 22:00-02:00 UTC (crosses midnight), scheduler correctly includes both dates in processing
- **Concurrent call limit reached**: Pending calls stay queued until an in-progress call completes; no calls drop due to concurrency limits
- **Language mismatch**: Patient requests language not supported (not English, Spanish, French, Haitian Creole); system defaults to English and logs the mismatch
- **Database unavailable during call**: Call data buffered locally; transcript saved when connection restored; no data loss

## Requirements *(mandatory)*

### Functional Requirements

**API & Infrastructure**

- **FR-001**: System MUST provide REST API endpoints under `/api/v1/` routing structure for all functionality
- **FR-002**: System MUST support admin user authentication with login endpoint returning time-limited access tokens (24-hour validity)
- **FR-003**: System MUST authenticate all protected endpoints and reject requests without valid tokens with 401 Unauthorized
- **FR-004**: System MUST provide GET `/api/v1/health` endpoint confirming server is running (publicly accessible, no auth required)
- **FR-005**: System MUST return request/response validation errors as structured JSON with error codes and descriptive messages

**Geography & Campaign Management**

- **FR-006**: System MUST allow admins to create and list geographies with names and metadata
- **FR-007**: System MUST allow admins to create feedback collection campaigns within geographies
- **FR-008**: System MUST support campaign configuration with: name, start/end time windows (UTC), days of week, max concurrent calls, patient list
- **FR-009**: System MUST return complete campaign configuration including current call queue state and progress metrics
- **FR-010**: System MUST allow filtering campaigns by geography

**Voice Call Testing**

- **FR-011**: System MUST provide endpoint to initiate test call to specified phone number
- **FR-012**: System MUST return test call status (queued, ringing, in-progress, completed, failed) with unique call ID
- **FR-013**: System MUST provide endpoint to query test call metadata including duration, transcript, AI responses, and error reason if failed
- **FR-014**: System MUST provide endpoint to simulate test conversation scenarios allowing admins to specify language and conversation path

**Patient Feedback Collection (Voice Calls)**

- **FR-015**: System MUST support multilingual patient calls in: English, Spanish, French, Haitian Creole
- **FR-016**: System MUST implement 6-stage conversation flow: Greeting → Language Selection → Patient Verification → Feedback Collection → Urgency Detection → Call Completion
- **FR-017**: System MUST verify patient identity (or note if different person answered) before collecting feedback
- **FR-018**: System MUST collect structured feedback: overall satisfaction (1-10 scale), specific concerns/complaints, reported side effects, experience quality
- **FR-019**: System MUST detect urgency signals in patient responses (keywords: "hospital", "severe", "can't breathe", etc.) and flag for clinical review
- **FR-020**: System MUST handle wrong person scenario: retry patient verification up to 2 times, then mark "wrong_person" and end call with callback offer
- **FR-021**: System MUST capture complete call transcript with timestamps and speaker identification (patient/AI)
- **FR-022**: System MUST save all call data (transcript, feedback responses, urgency flags, metadata) immediately after call ends
- **FR-023**: System MUST integrate with Twilio API to place outbound calls with proper WebSocket media streaming
- **FR-024**: System MUST integrate with OpenAI Realtime Model for natural conversation with function calling support
- **FR-025**: System MUST use Pipecat framework to orchestrate voice pipeline: Twilio audio → VAD → Transcription → OpenAI LLM → Audio synthesis → Twilio

**Campaign Queue & Scheduling**

- **FR-026**: System MUST support campaign state transitions: active → paused → completed, with manual admin control
- **FR-027**: System MUST queue all calls in a campaign for automatic processing via Celery + Redis
- **FR-028**: System MUST respect time windows (UTC-based start/end times, day-of-week filtering) for campaign execution
- **FR-029**: System MUST enforce maximum concurrent calls limit during active campaign processing
- **FR-030**: System MUST implement intelligent retry strategy: per-failure-reason delays (NO_ANSWER=30min, BUSY=1hr, FAILED=15min, PERSON_NOT_AVAILABLE=2hr, SHORT_DURATION=1hr)
- **FR-031**: System MUST route non-retriable failures (INVALID_NUMBER, REJECTED) directly to Dead Letter Queue without retry
- **FR-032**: System MUST track call entry state: pending → calling → success/failed, with full history of status changes
- **FR-033**: System MUST provide campaign status endpoint showing: queued count, in-progress count, completed count, failed count, urgent-flagged count

**Data Persistence**

- **FR-034**: System MUST persist all data in MongoDB with appropriate indexes for query performance
- **FR-035**: System MUST store call records with full metadata: patient contact info, feedback responses, transcript, duration, timestamps, urgency flags
- **FR-036**: System MUST store campaign records with configuration, patient lists, call status for each patient, and execution metrics

**Error Handling & Logging**

- **FR-037**: System MUST distinguish between user errors (invalid input), system errors (database down), and transient failures (network timeout)
- **FR-038**: System MUST log all errors with sufficient detail for debugging: call_sid, error type, context, timestamp
- **FR-039**: System MUST not expose sensitive data (phone numbers, API keys) in error messages returned to clients
- **FR-040**: System MUST log all authentication attempts and API access for audit trail

### Key Entities

- **Admin User**: Platform administrator with email/password credentials; permissions to manage geographies, campaigns, and view call results
- **Geography**: Logical operational unit representing region/market; contains multiple campaigns; has name and metadata
- **Campaign**: Feedback collection initiative; specifies patient list, time windows, concurrency limits, and aggregates call results
- **Patient Call Record**: Individual outbound call with patient contact info, feedback responses, transcript, duration, outcome, urgency flags
- **Call Queue Entry**: Individual entry in campaign queue; tracks state (pending/calling/success/failed), retry history, failure reason
- **Call Tracking**: Embedded metadata per call: call_sid (Twilio), stream_sid (Twilio), status, outcome, created/started/ended timestamps, duration
- **Conversation State**: Tracks patient feedback collection progress: current stage, completed stages, failed stages, stage-level retry counts
- **Campaign Queue**: Configuration for bulk campaign execution: patient list, time windows, concurrency limits, state machine

## Success Criteria *(mandatory)*

### Measurable Outcomes

**Performance & Reliability**

- **SC-001**: API health check responds within 500ms
- **SC-002**: Admin login/authentication completes within 2 seconds
- **SC-003**: Campaign creation (geography + campaign setup) completes within 30 seconds
- **SC-004**: Test call initiation returns call status within 10 seconds
- **SC-005**: Outbound calls successfully connect to valid phone numbers 95% of the time (excluding carrier/network failures)
- **SC-006**: Voice calls complete conversation flow within 10 minutes (from greeting to end)
- **SC-007**: Campaign queue processes calls without system degradation at concurrency limit of 10 simultaneous calls
- **SC-008**: Query campaign status returns results within 5 seconds

**Data & Accuracy**

- **SC-009**: 100% of call attempts are logged with complete metadata (phone, timestamp, duration, outcome)
- **SC-010**: Call transcripts capture 100% of conversation turns with speaker identification
- **SC-011**: Patient feedback responses (satisfaction, concerns, side effects) correctly recorded in 100% of calls
- **SC-012**: Urgency flags are correctly applied to 95% of calls with genuine urgent indicators

**Functionality Coverage**

- **SC-013**: All four language options (English, Spanish, French, Haitian Creole) produce audio output and accept speech input
- **SC-014**: Patient verification flow completes successfully in 90% of calls (10% account for wrong person scenarios)
- **SC-015**: Failed calls are classified with specific failure reason (NO_ANSWER, BUSY, INVALID_NUMBER, etc.) 100% of the time
- **SC-016**: Retriable failures are automatically retried with correct delay per failure type
- **SC-017**: Non-retriable failures (INVALID_NUMBER) move to Dead Letter Queue immediately without retry

**Operations & Diagnostics**

- **SC-018**: Campaign queue scheduler executes every 30 seconds, updating call states accurately
- **SC-019**: Call duration metadata is accurate within ±2 seconds
- **SC-020**: Error logs include sufficient context (call_sid, error type, timestamp) to debug 90% of issues without code inspection
- **SC-021**: Admin can troubleshoot failed call by querying call record and seeing full transcript + error reason

## Assumptions

**Architecture & Technology**

- FastAPI will serve as REST API framework (specified in requirements)
- MongoDB will be used for data persistence (specified in requirements)
- Twilio will be used for outbound calling (specified in requirements)
- OpenAI Realtime Model will be used for conversational AI (specified in requirements)
- Pipecat will be used for voice pipeline orchestration (specified in requirements)
- Celery + Redis will be used for campaign queue processing (chosen in design decisions)
- Python 3.11+ environment (specified in dependency list)

**Integration & Configuration**

- Twilio account credentials are securely configured at deployment time (not handled by spec)
- OpenAI API key is securely configured at deployment time (not handled by spec)
- MongoDB connection details are securely configured at deployment time (not handled by spec)
- Redis connection details are securely configured at deployment time (not handled by spec)

**Operational Assumptions**

- Phone numbers provided by admins are in E.164 format (international standard)
- Default campaign concurrency limit is 10 concurrent calls per campaign
- Campaign execution respects 1 call attempt per 2 seconds per phone number (carrier compliance)
- Session tokens expire after 24 hours of inactivity
- Admin users are pre-registered by system administrator (no self-serve admin registration)

**Call Flow Assumptions**

- Patient feedback collection prioritizes: patient verification → core feedback collection → urgency assessment
- Urgency keywords (for clinical follow-up) include: "hospital", "severe", "emergency", "can't breathe", "pain", "allergic reaction"
- Wrong person scenarios: retry patient verification max 2 times before marking call unsuccessful
- Each conversation stage has max 2 retries before gracefully moving to next achievable stage
- Partial call data (due to network failure mid-call) is saved with "incomplete" flag for human review

**Error Handling Assumptions**

- Failures from Twilio/OpenAI are treated as transient unless they indicate terminal issues (e.g., invalid phone format)
- Network timeouts default to 10 minutes max per call (after which pipeline stops)
- Short-duration calls (< 30 seconds) are retriable (often indicates dropped call, not answered, or fast busy)
- Calls are retried maximum 3 times total before moving to Dead Letter Queue for manual review

**Data & Privacy Assumptions**

- Call transcripts are retained for 90 days (industry standard for healthcare feedback)
- Patient phone numbers are not exposed in API responses to non-admin users
- All data access is logged for audit trail (required for healthcare compliance)
- Patient feedback responses are treated as potentially sensitive health information
