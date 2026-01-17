# API Contract: Calls

**Base Path**: `/api/v1/campaigns/{campaign_id}/calls`, `/api/v1/calls`
**Purpose**: Test call initiation, call record queries, and call management

---

## POST `/api/v1/campaigns/{campaign_id}/calls/test`

**Description**: Initiate test call to verify voice pipeline before launching campaign

**Authentication**: Required (Admin role only)

**Path Parameters**:
- `campaign_id`: MongoDB ObjectId

**Request Body**:
```json
{
  "phone_number": "+12025551234",
  "language": "en"
}
```

**Request Schema**:
```python
class TestCallRequest(BaseModel):
    phone_number: str = Field(..., pattern=r'^\+[1-9]\d{1,14}$')  # E.164 format
    language: str = Field(default="en", pattern="^(en|es|fr|ht)$")
```

**Success Response** (202 Accepted):
```json
{
  "call_id": "65c3d4e5f6g7h8i9j0k1l2m3",
  "status": "queued",
  "phone_number": "+12025551234",
  "language": "en",
  "message": "Test call queued. Check status at /api/v1/calls/65c3d4e5f6g7h8i9j0k1l2m3"
}
```

**Response Schema**:
```python
class TestCallResponse(BaseModel):
    call_id: str
    status: str  # "queued" | "ringing" | "in-progress"
    phone_number: str
    language: str
    message: str
```

**Error Responses**:

- **403 Forbidden** - User role lacks permission
- **404 Not Found** - Campaign doesn't exist
- **422 Unprocessable Entity** - Invalid phone number

**Performance**: Must respond < 10 seconds (SC-004)

**Side Effects**:
- Creates `CallRecord` with test call metadata
- Does NOT create `QueueEntry` (test calls bypass queue)
- Initiates Twilio call immediately

---

## POST `/api/v1/campaigns/{campaign_id}/calls/test-scenario`

**Description**: Simulate test conversation with specific scenario path (for debugging)

**Authentication**: Required (Admin role only)

**Path Parameters**:
- `campaign_id`: MongoDB ObjectId

**Request Body**:
```json
{
  "phone_number": "+12025551234",
  "language": "es",
  "scenario": "wrong_person",
  "scenario_params": {
    "wrong_person_attempts": 2,
    "offer_callback": true
  }
}
```

**Request Schema**:
```python
class TestScenario(str, Enum):
    HAPPY_PATH = "happy_path"              # Full conversation, success
    WRONG_PERSON = "wrong_person"          # Caller not patient/guardian
    URGENT_KEYWORDS = "urgent_keywords"    # Simulate urgency detection
    NETWORK_FAILURE = "network_failure"    # Simulate mid-call disconnect
    SHORT_DURATION = "short_duration"      # Simulate <30s call

class TestScenarioRequest(BaseModel):
    phone_number: str = Field(..., pattern=r'^\+[1-9]\d{1,14}$')
    language: str = Field(default="en", pattern="^(en|es|fr|ht)$")
    scenario: TestScenario
    scenario_params: Dict[str, Any] = Field(default_factory=dict)
```

**Success Response** (202 Accepted):
```json
{
  "call_id": "65c3d4e5f6g7h8i9j0k1l2m3",
  "status": "queued",
  "scenario": "wrong_person",
  "message": "Test scenario 'wrong_person' queued for execution"
}
```

**Response Schema**: `TestCallResponse` with `scenario` field

---

## GET `/api/v1/calls/{call_id}`

**Description**: Get call record by ID with full details

**Authentication**: Required (both Admin and User roles)

**Path Parameters**:
- `call_id`: MongoDB ObjectId

**Success Response** (200 OK):
```json
{
  "id": "65c3d4e5f6g7h8i9j0k1l2m3",
  "campaign_id": "65b2c3d4e5f6g7h8i9j0k1l2",
  "patient_phone": "+12025551234",
  "language": "en",
  "conversation_state": {
    "current_stage": "call_completion",
    "completed_stages": [
      "greeting",
      "language_selection",
      "patient_verification",
      "feedback_collection",
      "urgency_detection"
    ],
    "failed_stages": [],
    "stage_retry_counts": {}
  },
  "transcript": [
    {
      "speaker": "ai",
      "text": "Hello! This is a call from your healthcare provider to collect feedback about your recent visit.",
      "timestamp": "2026-01-18T15:00:10Z"
    },
    {
      "speaker": "patient",
      "text": "Yes, I remember. How can I help?",
      "timestamp": "2026-01-18T15:00:15Z"
    }
  ],
  "feedback": {
    "overall_satisfaction": 8,
    "specific_concerns": "Wait time was a bit long",
    "side_effects_reported": null,
    "experience_quality": "Good overall, staff was friendly"
  },
  "urgency_flagged": false,
  "urgency_keywords_detected": [],
  "call_tracking": {
    "call_sid": "CA1234567890abcdef",
    "stream_sid": "MZ9876543210fedcba",
    "status": "completed",
    "outcome": "success",
    "created_at": "2026-01-18T15:00:00Z",
    "started_at": "2026-01-18T15:00:05Z",
    "ended_at": "2026-01-18T15:03:25Z",
    "duration_seconds": 200
  },
  "error_message": null,
  "created_at": "2026-01-18T15:00:00Z",
  "updated_at": "2026-01-18T15:03:30Z"
}
```

**Response Schema**:
```python
class ConversationTurnResponse(BaseModel):
    speaker: str  # "patient" | "ai"
    text: str
    timestamp: datetime

class ConversationStateResponse(BaseModel):
    current_stage: Optional[ConversationStage]
    completed_stages: List[ConversationStage]
    failed_stages: List[ConversationStage]
    stage_retry_counts: Dict[str, int]

class FeedbackDataResponse(BaseModel):
    overall_satisfaction: Optional[int]
    specific_concerns: Optional[str]
    side_effects_reported: Optional[str]
    experience_quality: Optional[str]

class CallTrackingResponse(BaseModel):
    call_sid: Optional[str]
    stream_sid: Optional[str]
    status: str
    outcome: Optional[CallOutcome]
    created_at: datetime
    started_at: Optional[datetime]
    ended_at: Optional[datetime]
    duration_seconds: Optional[int]

class CallRecordResponse(BaseModel):
    id: str
    campaign_id: str
    patient_phone: str  # Hidden from User role
    language: str
    conversation_state: ConversationStateResponse
    transcript: List[ConversationTurnResponse]
    feedback: FeedbackDataResponse
    urgency_flagged: bool
    urgency_keywords_detected: List[str]
    call_tracking: CallTrackingResponse
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime
```

**Privacy Notes**:
- `patient_phone` hidden from User role responses
- Full transcript visible to both Admin and User roles (for clinical review)

**Error Responses**:

- **404 Not Found** - Call record doesn't exist

---

## GET `/api/v1/campaigns/{campaign_id}/calls`

**Description**: List all calls for a campaign with filtering

**Authentication**: Required (both Admin and User roles)

**Path Parameters**:
- `campaign_id`: MongoDB ObjectId

**Query Parameters**:
- `outcome` (optional): Filter by call outcome (success, no_answer, failed, etc.)
- `urgency_flagged` (optional): Filter by urgency flag (true/false)
- `skip` (optional, default: 0): Pagination offset
- `limit` (optional, default: 50, max: 100): Page size

**Example**: `GET /api/v1/campaigns/{campaign_id}/calls?urgency_flagged=true&limit=20`

**Success Response** (200 OK):
```json
{
  "total": 150,
  "skip": 0,
  "limit": 50,
  "items": [
    {
      "id": "65c3d4e5f6g7h8i9j0k1l2m3",
      "campaign_id": "65b2c3d4e5f6g7h8i9j0k1l2",
      "language": "en",
      "urgency_flagged": true,
      "urgency_keywords_detected": ["severe", "hospital"],
      "call_tracking": {
        "outcome": "success",
        "duration_seconds": 180,
        "ended_at": "2026-01-18T15:03:25Z"
      },
      "created_at": "2026-01-18T15:00:00Z"
    }
  ]
}
```

**Response Schema**:
```python
class CallRecordListItem(BaseModel):
    id: str
    campaign_id: str
    language: str
    urgency_flagged: bool
    urgency_keywords_detected: List[str]
    call_tracking: CallTrackingResponse
    created_at: datetime

class CallRecordListResponse(BaseModel):
    total: int
    skip: int
    limit: int
    items: List[CallRecordListItem]
```

**Note**: List view omits `transcript` and `feedback` for performance (fetch full record for details)

---

## GET `/api/v1/calls/urgent`

**Description**: Get all urgent-flagged calls across all campaigns (for clinical review)

**Authentication**: Required (both Admin and User roles)

**Query Parameters**:
- `campaign_id` (optional): Filter by campaign
- `skip` (optional, default: 0): Pagination offset
- `limit` (optional, default: 50, max: 100): Page size

**Success Response** (200 OK):
```json
{
  "total": 12,
  "items": [
    {
      "id": "65c3d4e5f6g7h8i9j0k1l2m3",
      "campaign_id": "65b2c3d4e5f6g7h8i9j0k1l2",
      "urgency_keywords_detected": ["severe", "hospital"],
      "feedback": {
        "overall_satisfaction": 2,
        "specific_concerns": "Severe allergic reaction, went to hospital"
      },
      "call_tracking": {
        "ended_at": "2026-01-18T15:03:25Z"
      },
      "created_at": "2026-01-18T15:00:00Z"
    }
  ]
}
```

**Response Schema**: Similar to `CallRecordListResponse` but includes `feedback` field

---

## GET `/api/v1/campaigns/{campaign_id}/calls/export`

**Description**: Export call data as CSV for external analysis

**Authentication**: Required (Admin role only)

**Path Parameters**:
- `campaign_id`: MongoDB ObjectId

**Query Parameters**:
- `format` (optional, default: csv): Export format (csv, json)

**Success Response** (200 OK):
```csv
call_id,phone_number,language,outcome,duration_seconds,overall_satisfaction,urgency_flagged,created_at
65c3d4e5f6g7h8i9j0k1l2m3,+12025551234,en,success,200,8,false,2026-01-18T15:00:00Z
65c3d4e5f6g7h8i9j0k1l2m4,+12025555678,es,no_answer,0,,false,2026-01-18T15:05:00Z
```

**Content-Type**: `text/csv` or `application/json`

**Privacy Notes**:
- Admin role only (contains patient phone numbers)
- Transcripts NOT included in export (too large, use API for full records)

---

## Webhook: POST `/api/v1/webhooks/twilio/status`

**Description**: Twilio status callback webhook (called by Twilio, not clients)

**Authentication**: Twilio signature validation

**Request Body** (from Twilio):
```
CallSid=CA1234567890abcdef
CallStatus=completed
CallDuration=200
```

**Success Response** (200 OK):
```xml
<?xml version="1.0" encoding="UTF-8"?>
<Response></Response>
```

**Side Effects**:
- Updates `CallRecord.call_tracking.status` and `outcome`
- Calculates `duration_seconds`
- Triggers queue entry state transition (SUCCESS or FAILED)

**Security**:
- Validates Twilio signature using `X-Twilio-Signature` header
- Rejects unsigned requests with 403 Forbidden

---

## Business Rules

### Urgency Detection Keywords
- Keywords: "hospital", "severe", "emergency", "can't breathe", "pain", "allergic reaction"
- Case-insensitive matching in patient transcript
- Sets `urgency_flagged = true` if any keyword detected

### Call Outcome Classification
- `SUCCESS`: Completed all 6 conversation stages
- `PARTIAL_SUCCESS`: Completed feedback collection but not all stages
- `NO_ANSWER`: Twilio status "no-answer" or "busy"
- `FAILED`: Technical failure or timeout
- `WRONG_PERSON`: Caller indicated not patient/guardian/helper

### Transcript Logging
- All conversation turns logged with timestamps (SC-010)
- Speaker identification: "patient" or "ai"
- Partial transcripts saved on network failure (SC-009)

---

## Performance Requirements

- Test call initiation: < 10 seconds (SC-004)
- Call record query: < 5 seconds (SC-008)
- Call duration accuracy: ±2 seconds (SC-019)
- Transcript capture: 100% of conversation turns (SC-010)
