# Feature Specification: Patient Feedback Collection API

**Feature Branch**: `001-patient-feedback-api`
**Created**: 2026-01-17
**Status**: Draft
**Input**: Initialise a FastAPI REST API server with admin authentication, geography/project management, and AI-powered patient feedback collection via voice calls using Twilio integration

## Clarifications

### Session 2026-01-17

- Q: Patient Data Identification & Verification Strategy - How should the system verify patient identity during calls? → A: Trust phone number ownership - caller is assumed to be patient or patient guardian or helper based on scenario
- Q: Campaign Data Retention & Archival Policy - How long should campaign and call data be retained? → A: Configurable per geography (some regions require longer retention for regulatory compliance); default is indefinite retention with compliance audit trail; admin can override with archival configuration per geography
- Q: Observability & Monitoring Strategy - What monitoring and metrics strategy should the system implement? → A: Multi-layered approach: (1) Basic logging to stdout/files for log aggregation, (2) Application metrics endpoint (/metrics) with custom format for health/call stats, (3) Structured logging + metrics export (Prometheus/OpenTelemetry compatible)
- Q: Admin Role & Permission Model - What role and permission model should the system implement? → A: Simple role-based access with two roles: Admin (full access to manage geographies, campaigns, configure settings) and User (read-only access to view campaigns and call results)
- Q: Healthcare Compliance & Regulatory Requirements - What specific compliance requirements should the system enforce? → A: Deferred - specific healthcare compliance requirements (HIPAA, GDPR, etc.) not specified in MVP; general data protection practices apply

### Session 2026-01-18

- Q: Pipecat Framework Implementation Constraints (v0.0.99) - What are the correct API patterns for implementing voice pipeline with Pipecat v0.0.99? → A: Use new module structure with breaking changes from v0.0.99: (1) Replace OpenAILLMContext with universal LLMContext, (2) Use LLMContextAggregatorPair instead of create_context_aggregator(), (3) Replace turn_analyzer with user_turn_strategies (VADUserTurnStartStrategy, TranscriptionUserTurnStopStrategy), (4) Use strategy-based interruption handling via user_mute_strategies instead of allow_interruptions, (5) Configure FastAPIWebsocketTransport with fixed_audio_packet_size for Twilio media endpoints, (6) Register function handlers directly with OpenAIRealtimeLLMService using register_function(), (7) Use FlowManager pattern for multi-stage conversation state management with dynamic node transitions

## User Scenarios & Testing *(mandatory)*

### User Story 1 - API Server Infrastructure & Admin Authentication (Priority: P1)

Platform administrators need a secure REST API backend with health checks and access control so they can manage campaigns and patient data.

**Why this priority**: P1 is critical - all other features depend on a running, authenticated API server. Without this infrastructure, no other functionality is accessible.

**Independent Test**: Can be fully tested by verifying admin login, authentication token validation, protected endpoint access control, delivering a secure API foundation.

**Acceptance Scenarios**:

1. **Given** user credentials are registered with role, **When** user calls `POST /api/v1/auth/login` with credentials, **Then** receives authentication token valid for 24 hours including role information
2. **Given** valid Admin role token, **When** admin calls protected endpoint requiring write access, **Then** receives successful response
3. **Given** valid User role token, **When** user calls protected endpoint requiring write access, **Then** receives 403 Forbidden
4. **Given** valid User role token, **When** user calls read-only endpoint (view campaigns, view calls), **Then** receives successful response
5. **Given** valid authentication token, **When** user calls `GET /api/v1/health` with token header, **Then** receives 200 OK with server status
6. **Given** monitoring system, **When** calls `GET /api/v1/metrics`, **Then** receives current application health and call statistics in JSON format
7. **Given** invalid or expired token, **When** user calls any protected endpoint, **Then** receives 401 Unauthorized
8. **Given** no authentication header, **When** user calls protected endpoint, **Then** receives 401 Unauthorized

---

### User Story 2 - Geography & Campaign Project Setup (Priority: P2)

Operations managers need to organize patient feedback campaigns by geography and create campaigns within those regions so they can manage multi-location operations.

**Why this priority**: P2 enables regional organization of patient feedback collection. Once the API server is running, managers can create regional scopes for campaigns.

**Independent Test**: Can be fully tested by creating geographies, creating feedback collection campaigns within geographies, and verifying campaign configurations are persisted, delivering geography-scoped campaign management.

**Acceptance Scenarios**:

1. **Given** authenticated admin, **When** calls `POST /api/v1/geographies`, **Then** can create new geography with name, region metadata, and optional data retention policy configuration
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

- **Wrong person answers**: If caller indicates they are not patient/guardian/helper or cannot provide feedback, and no appropriate person is available after 2 retry attempts, system marks "wrong_person" and stops, offers callback to reach appropriate respondent
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
- **FR-002**: System MUST support user authentication with login endpoint returning time-limited access tokens (24-hour validity)
- **FR-003**: System MUST support two user roles: Admin (full access to create/modify/delete resources) and User (read-only access to view resources)
- **FR-004**: System MUST authenticate all protected endpoints and reject requests without valid tokens with 401 Unauthorized
- **FR-005**: System MUST enforce role-based authorization: reject User role requests to create/modify/delete resources with 403 Forbidden
- **FR-006**: System MUST provide GET `/api/v1/health` endpoint confirming server is running (publicly accessible, no auth required)
- **FR-007**: System MUST return request/response validation errors as structured JSON with error codes and descriptive messages

**Geography & Campaign Management**

- **FR-008**: System MUST allow Admin role to create and list geographies with names, metadata, and optional data retention policy configuration (defaults to indefinite retention if not specified)
- **FR-009**: System MUST allow Admin role to create feedback collection campaigns within geographies
- **FR-010**: System MUST allow User role to view (but not modify) geographies and campaigns
- **FR-011**: System MUST support campaign configuration with: name, start/end time windows (UTC), days of week, max concurrent calls, patient list
- **FR-012**: System MUST return complete campaign configuration including current call queue state and progress metrics
- **FR-013**: System MUST allow filtering campaigns by geography

**Voice Call Testing**

- **FR-014**: System MUST provide endpoint to initiate test call to specified phone number (Admin role only)
- **FR-015**: System MUST return test call status (queued, ringing, in-progress, completed, failed) with unique call ID
- **FR-016**: System MUST provide endpoint to query test call metadata including duration, transcript, AI responses, and error reason if failed (both Admin and User roles)
- **FR-017**: System MUST provide endpoint to simulate test conversation scenarios allowing admins to specify language and conversation path (Admin role only)

**Patient Feedback Collection (Voice Calls)**

- **FR-018**: System MUST support multilingual patient calls in: English, Spanish, French, Haitian Creole
- **FR-019**: System MUST implement 6-stage conversation flow: Greeting → Language Selection → Patient Verification → Feedback Collection → Urgency Detection → Call Completion
- **FR-020**: System MUST verify patient identity by confirming caller is appropriate respondent (patient, guardian, or authorized helper answering on patient's behalf); phone number ownership serves as primary authentication; conversation confirms caller context but does not require additional identity verification (no DOB, SSN, or account credentials)
- **FR-021**: System MUST collect structured feedback: overall satisfaction (1-10 scale), specific concerns/complaints, reported side effects, experience quality
- **FR-022**: System MUST detect urgency signals in patient responses (keywords: "hospital", "severe", "can't breathe", etc.) and flag for clinical review
- **FR-023**: System MUST handle wrong person scenario (caller indicates they are not patient/guardian/helper or cannot provide feedback): retry up to 2 times asking if appropriate person is available, then mark "wrong_person" and end call with callback offer
- **FR-024**: System MUST capture complete call transcript with timestamps and speaker identification (patient/AI)
- **FR-025**: System MUST save all call data (transcript, feedback responses, urgency flags, metadata) immediately after call ends
- **FR-026**: System MUST integrate with Twilio API to place outbound calls with proper WebSocket media streaming
- **FR-027**: System MUST integrate with OpenAI Realtime Model for natural conversation with function calling support
- **FR-028**: System MUST use Pipecat framework to orchestrate voice pipeline: Twilio audio → VAD → Transcription → OpenAI LLM → Audio synthesis → Twilio

**Campaign Queue & Scheduling**

- **FR-029**: System MUST support campaign state transitions: active → paused → completed, with manual admin control (Admin role only)
- **FR-030**: System MUST queue all calls in a campaign for automatic processing via Celery + Redis
- **FR-031**: System MUST respect time windows (UTC-based start/end times, day-of-week filtering) for campaign execution
- **FR-032**: System MUST enforce maximum concurrent calls limit during active campaign processing
- **FR-033**: System MUST implement intelligent retry strategy: per-failure-reason delays (NO_ANSWER=30min, BUSY=1hr, FAILED=15min, PERSON_NOT_AVAILABLE=2hr, SHORT_DURATION=1hr)
- **FR-034**: System MUST route non-retriable failures (INVALID_NUMBER, REJECTED) directly to Dead Letter Queue without retry
- **FR-035**: System MUST track call entry state: pending → calling → success/failed, with full history of status changes
- **FR-036**: System MUST provide campaign status endpoint showing: queued count, in-progress count, completed count, failed count, urgent-flagged count (both Admin and User roles)

**Data Persistence**

- **FR-037**: System MUST persist all data in MongoDB with appropriate indexes for query performance
- **FR-038**: System MUST store call records with full metadata: patient contact info, feedback responses, transcript, duration, timestamps, urgency flags
- **FR-039**: System MUST store campaign records with configuration, patient lists, call status for each patient, and execution metrics
- **FR-040**: System MUST support configurable data retention policies per geography to accommodate regulatory compliance requirements
- **FR-041**: System MUST retain all campaign and call data indefinitely with compliance audit trail by default
- **FR-042**: System MUST allow Admin role to configure archival settings per geography (retention duration, archival destination, purge policy)

**Error Handling & Logging**

- **FR-043**: System MUST distinguish between user errors (invalid input), system errors (database down), and transient failures (network timeout)
- **FR-044**: System MUST log all errors with sufficient detail for debugging: call_sid, error type, context, timestamp
- **FR-045**: System MUST not expose sensitive data (phone numbers, API keys) in error messages returned to clients
- **FR-046**: System MUST log all authentication attempts and API access for audit trail

**Observability & Monitoring**

- **FR-047**: System MUST write logs to stdout/files in both human-readable and structured JSON formats for log aggregation
- **FR-048**: System MUST provide GET `/api/v1/metrics` endpoint exposing application health and call statistics in custom JSON format (accessible to both Admin and User roles)
- **FR-049**: System MUST export metrics in Prometheus-compatible format for external monitoring systems
- **FR-050**: System MUST support OpenTelemetry-compatible structured logging and metrics export
- **FR-051**: System MUST track and expose key operational metrics: active calls count, queued calls count, call success/failure rates, average call duration, campaign processing rate
- **FR-052**: System MUST include trace identifiers in logs for correlating events across call lifecycle (call_sid, stream_sid, campaign_id)

### Key Entities

- **User**: Platform user with email/password credentials and assigned role (Admin or User); authenticated via access token
- **Admin Role**: Full permissions to create/modify/delete geographies, campaigns, configure retention policies, initiate test calls, and control campaign state
- **User Role**: Read-only permissions to view geographies, campaigns, call results, and metrics; cannot create or modify resources
- **Geography**: Logical operational unit representing region/market; contains multiple campaigns; has name, metadata, and configurable data retention policy (retention duration, archival rules, compliance requirements)
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
- **SC-022**: Metrics endpoint responds within 1 second with current system health and call statistics
- **SC-023**: All logs include trace identifiers (call_sid, campaign_id) for 100% of call-related events
- **SC-024**: Prometheus metrics export updates at least every 15 seconds with current operational state

## Assumptions

**Architecture & Technology**

- FastAPI will serve as REST API framework (specified in requirements)
- MongoDB 8.0.17 will be used for data persistence (specified in requirements)
- Twilio will be used for outbound calling (specified in requirements)
- OpenAI Realtime Model will be used for conversational AI (specified in requirements)
- Pipecat v0.0.99 will be used for voice pipeline orchestration with new module structure: LLMContext (universal context), LLMContextAggregatorPair (context management), user_turn_strategies (turn detection), user_mute_strategies (interruption handling), FlowManager (multi-stage conversation state), FastAPIWebsocketTransport with fixed_audio_packet_size for Twilio compatibility
- Celery + Redis will be used for campaign queue processing (chosen in design decisions)
- Python 3.12.12 environment (specified in requirements)

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
- Users are pre-registered by system administrator with assigned role (Admin or User); no self-serve registration
- Admin role has full access to create/modify/delete resources; User role has read-only access
- Role assignment is permanent per user account (no dynamic role switching during session)
- Logs are written to stdout/files for ingestion by external log aggregation systems (e.g., ELK, Loki, Splunk)
- Metrics are exposed for scraping by external monitoring systems (e.g., Prometheus, Grafana, Datadog)
- Structured logs use JSON format with consistent field naming for machine parsing
- OpenTelemetry format is used for distributed tracing compatibility

**Call Flow Assumptions**

- Patient feedback collection prioritizes: caller context confirmation → core feedback collection → urgency assessment
- Phone number ownership serves as primary authentication; caller may be patient, guardian, or authorized helper
- Verification stage confirms caller is appropriate respondent who can provide feedback (not identity authentication with credentials)
- Urgency keywords (for clinical follow-up) include: "hospital", "severe", "emergency", "can't breathe", "pain", "allergic reaction"
- Wrong person scenarios: caller indicates they cannot provide feedback; retry up to 2 times asking if appropriate person is available before marking call unsuccessful
- Each conversation stage has max 2 retries before gracefully moving to next achievable stage
- Partial call data (due to network failure mid-call) is saved with "incomplete" flag for human review

**Error Handling Assumptions**

- Failures from Twilio/OpenAI are treated as transient unless they indicate terminal issues (e.g., invalid phone format)
- Network timeouts default to 10 minutes max per call (after which pipeline stops)
- Short-duration calls (< 30 seconds) are retriable (often indicates dropped call, not answered, or fast busy)
- Calls are retried maximum 3 times total before moving to Dead Letter Queue for manual review

**Data & Privacy Assumptions**

- Data retention is configurable per geography to accommodate regional regulatory requirements
- Default retention policy: indefinite storage with compliance audit trail (no automatic purge)
- Admins can configure per-geography archival rules (retention duration, archival destination, purge policy)
- Patient phone numbers are not exposed in API responses to non-admin users
- All data access is logged for audit trail (required for healthcare compliance)
- Patient feedback responses are treated as potentially sensitive health information
