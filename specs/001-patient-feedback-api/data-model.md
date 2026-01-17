# Data Model: Patient Feedback Collection API

**Feature**: Patient Feedback Collection API
**Date**: 2026-01-18
**Purpose**: Define Beanie ODM models for MongoDB persistence with clean architecture separation

---

## Design Principles

### 1. Beanie ODM with Pydantic Integration
- All collections extend `beanie.Document` base class
- Full Pydantic validation on all fields
- MongoDB indexes defined in model `Settings` class
- Type hints on all fields for IDE support and runtime validation

### 2. Embedded vs Referenced Documents
- **Reference (ObjectId)**: When entities have independent lifecycle (User, Geography, Campaign)
- **Embedded (nested)**: When data is always accessed together and has no independent meaning (ConversationState, CallTracking, FeedbackData)

### 3. Enums for Status Fields
- All state machines use Python Enums (not raw strings)
- Enables type safety and prevents invalid states
- Clear documentation of valid transitions

### 4. Timestamps and Audit Trail
- All documents include `created_at` and `updated_at` timestamps
- Deleted documents use soft delete with `deleted_at` (for compliance audit trail)
- Retention policies respect compliance requirements

---

## Core Models

### 1. User (Collection: `users`)

**Purpose**: Platform user accounts with role-based access control

```python
from beanie import Document, Indexed
from pydantic import EmailStr, Field
from datetime import datetime
from enum import Enum
from typing import Optional

class UserRole(str, Enum):
    """User role enumeration for RBAC"""
    ADMIN = "admin"  # Full access: create/modify/delete resources
    USER = "user"    # Read-only: view resources only

class User(Document):
    """
    Platform user with authentication credentials and role assignment.

    Indexes:
    - email (unique): Fast user lookup during authentication
    """

    email: Indexed(EmailStr, unique=True)
    hashed_password: str = Field(..., exclude=True)  # Never returned in API responses
    role: UserRole = Field(default=UserRole.USER)

    # Metadata
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_login: Optional[datetime] = None

    class Settings:
        name = "users"
        indexes = [
            "email",  # Unique index for authentication
        ]

    class Config:
        json_schema_extra = {
            "example": {
                "email": "admin@example.com",
                "role": "admin",
                "is_active": True
            }
        }
```

---

### 2. Geography (Collection: `geographies`)

**Purpose**: Regional organization unit for campaigns with configurable retention policies

```python
from beanie import Document
from pydantic import Field
from datetime import datetime
from typing import Optional, Dict, Any

class RetentionPolicy(BaseModel):
    """
    Configurable data retention rules per geography for compliance.

    Default: Indefinite retention with audit trail.
    Override: Per-geography archival and purge rules.
    """

    retention_days: Optional[int] = Field(
        None,
        description="Days to retain data before archival (None = indefinite)"
    )
    archival_destination: Optional[str] = Field(
        None,
        description="Storage location for archived data (S3 bucket, MinIO path, etc.)"
    )
    auto_purge_enabled: bool = Field(
        default=False,
        description="Automatically delete data after retention period expires"
    )
    compliance_notes: Optional[str] = Field(
        None,
        description="Regulatory requirements justifying retention policy"
    )

class Geography(Document):
    """
    Geographic region or operational unit containing campaigns.

    Indexes:
    - name: Fast lookup and filtering
    """

    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    region_code: Optional[str] = Field(
        None,
        description="ISO 3166-1 alpha-2 country code or custom region identifier"
    )

    # Configurable retention policy
    retention_policy: RetentionPolicy = Field(
        default_factory=RetentionPolicy,
        description="Data retention rules for this geography"
    )

    # Metadata for operational tracking
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Custom key-value pairs for operational context"
    )

    # Audit timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    deleted_at: Optional[datetime] = Field(
        None,
        description="Soft delete timestamp for audit trail"
    )

    class Settings:
        name = "geographies"
        indexes = [
            "name",
            "region_code",
        ]

    class Config:
        json_schema_extra = {
            "example": {
                "name": "North America - East Coast",
                "region_code": "US-EAST",
                "retention_policy": {
                    "retention_days": 2555,  # 7 years
                    "compliance_notes": "HIPAA requires 7-year retention"
                }
            }
        }
```

---

### 3. Campaign (Collection: `campaigns`)

**Purpose**: Patient feedback collection initiative with queue configuration

```python
from beanie import Document, Link
from pydantic import Field, validator
from datetime import datetime, time
from typing import Optional, List
from enum import Enum

class CampaignState(str, Enum):
    """Campaign lifecycle states"""
    DRAFT = "draft"          # Created but not started
    ACTIVE = "active"        # Running and processing calls
    PAUSED = "paused"        # Temporarily stopped
    COMPLETED = "completed"  # All calls processed
    CANCELLED = "cancelled"  # Manually terminated

class DayOfWeek(str, Enum):
    """Days when campaign can execute"""
    MONDAY = "monday"
    TUESDAY = "tuesday"
    WEDNESDAY = "wednesday"
    THURSDAY = "thursday"
    FRIDAY = "friday"
    SATURDAY = "saturday"
    SUNDAY = "sunday"

class TimeWindow(BaseModel):
    """UTC-based time window for campaign execution"""
    start_time: time = Field(..., description="UTC start time (HH:MM)")
    end_time: time = Field(..., description="UTC end time (HH:MM)")
    days_of_week: List[DayOfWeek] = Field(
        default_factory=lambda: list(DayOfWeek),
        description="Days when campaign can run"
    )

    @validator('end_time')
    def validate_time_window(cls, v, values):
        """Allow midnight-crossing time windows (e.g., 22:00-02:00)"""
        # Validation happens in service layer to handle day boundary logic
        return v

class CampaignConfig(BaseModel):
    """Campaign execution parameters"""
    max_concurrent_calls: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Maximum simultaneous calls (default: 10)"
    )
    time_windows: List[TimeWindow] = Field(
        default_factory=list,
        description="When campaign can execute (empty = always)"
    )
    patient_list: List[str] = Field(
        default_factory=list,
        description="E.164 formatted phone numbers"
    )
    language_preference: Optional[str] = Field(
        "en",
        description="Default language: en, es, fr, ht"
    )

class CampaignStats(BaseModel):
    """Real-time campaign progress metrics"""
    total_calls: int = 0
    queued_count: int = 0
    in_progress_count: int = 0
    completed_count: int = 0
    failed_count: int = 0
    urgent_flagged_count: int = 0

class Campaign(Document):
    """
    Patient feedback collection campaign with queue configuration.

    Indexes:
    - geography_id: Filter campaigns by region
    - state: Query active/paused campaigns
    - created_at: Sort by recency
    """

    name: str = Field(..., min_length=1, max_length=200)
    geography_id: Link[Geography]  # Reference to parent geography

    # Campaign configuration
    config: CampaignConfig = Field(default_factory=CampaignConfig)

    # State management
    state: CampaignState = Field(default=CampaignState.DRAFT)

    # Real-time statistics (updated by queue processor)
    stats: CampaignStats = Field(default_factory=CampaignStats)

    # Audit timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None

    class Settings:
        name = "campaigns"
        indexes = [
            "geography_id",
            "state",
            "created_at",
        ]

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Post-Vaccination Feedback - January 2026",
                "state": "active",
                "config": {
                    "max_concurrent_calls": 10,
                    "patient_list": ["+12025551234", "+12025555678"],
                    "language_preference": "en"
                }
            }
        }
```

---

### 4. CallRecord (Collection: `call_records`)

**Purpose**: Individual patient call with feedback data and conversation transcript

```python
from beanie import Document, Link
from pydantic import Field
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum

class CallOutcome(str, Enum):
    """Final call disposition"""
    SUCCESS = "success"                      # Completed full conversation
    PARTIAL_SUCCESS = "partial_success"      # Partial feedback collected
    NO_ANSWER = "no_answer"                  # Did not pick up
    BUSY = "busy"                            # Line busy
    FAILED = "failed"                        # Technical failure
    INVALID_NUMBER = "invalid_number"        # Not a valid phone number
    REJECTED = "rejected"                    # Call rejected by carrier
    WRONG_PERSON = "wrong_person"            # Not patient/guardian/helper
    TIMEOUT = "timeout"                      # Exceeded 10-minute max duration
    NETWORK_FAILURE = "network_failure"      # Dropped mid-call

class FeedbackData(BaseModel):
    """Structured patient feedback responses"""
    overall_satisfaction: Optional[int] = Field(
        None,
        ge=1,
        le=10,
        description="Satisfaction rating (1-10 scale)"
    )
    specific_concerns: Optional[str] = Field(
        None,
        description="Free-text concerns or complaints"
    )
    side_effects_reported: Optional[str] = Field(
        None,
        description="Reported side effects (if applicable)"
    )
    experience_quality: Optional[str] = Field(
        None,
        description="Overall experience description"
    )

class ConversationTurn(BaseModel):
    """Single speaker turn in conversation"""
    speaker: str = Field(..., description="'patient' or 'ai'")
    text: str = Field(..., description="Transcribed text")
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class ConversationStage(str, Enum):
    """6-stage conversation flow"""
    GREETING = "greeting"
    LANGUAGE_SELECTION = "language_selection"
    PATIENT_VERIFICATION = "patient_verification"
    FEEDBACK_COLLECTION = "feedback_collection"
    URGENCY_DETECTION = "urgency_detection"
    CALL_COMPLETION = "call_completion"

class ConversationState(BaseModel):
    """Tracks progress through conversation stages"""
    current_stage: Optional[ConversationStage] = None
    completed_stages: List[ConversationStage] = Field(default_factory=list)
    failed_stages: List[ConversationStage] = Field(default_factory=list)
    stage_retry_counts: Dict[str, int] = Field(
        default_factory=dict,
        description="Retry attempts per stage (max 2 per stage)"
    )

class CallTracking(BaseModel):
    """Twilio call metadata and timing"""
    call_sid: Optional[str] = Field(None, description="Twilio Call SID")
    stream_sid: Optional[str] = Field(None, description="Twilio Stream SID")
    status: str = Field(default="queued")
    outcome: Optional[CallOutcome] = None

    # Timing
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    duration_seconds: Optional[int] = Field(
        None,
        description="Call duration in seconds"
    )

class CallRecord(Document):
    """
    Individual patient feedback call with full conversation history.

    Indexes:
    - campaign_id: Query all calls for a campaign
    - call_tracking.call_sid: Twilio webhook lookups
    - call_tracking.outcome: Filter by call result
    - urgency_flagged: Query urgent cases for clinical review
    - created_at: Sort by recency
    """

    campaign_id: Link[Campaign]

    # Patient contact (phone number ownership = authentication)
    patient_phone: str = Field(..., description="E.164 format")
    language: str = Field(default="en", description="en, es, fr, ht")

    # Conversation data
    conversation_state: ConversationState = Field(default_factory=ConversationState)
    transcript: List[ConversationTurn] = Field(
        default_factory=list,
        description="Full conversation history with timestamps"
    )
    feedback: FeedbackData = Field(default_factory=FeedbackData)

    # Urgency detection
    urgency_flagged: bool = Field(
        default=False,
        description="True if keywords detected: hospital, severe, can't breathe"
    )
    urgency_keywords_detected: List[str] = Field(default_factory=list)

    # Call tracking
    call_tracking: CallTracking = Field(default_factory=CallTracking)

    # Error context
    error_message: Optional[str] = Field(
        None,
        description="Detailed error for debugging (not shown to patients)"
    )

    # Audit
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "call_records"
        indexes = [
            "campaign_id",
            "call_tracking.call_sid",
            "call_tracking.outcome",
            "urgency_flagged",
            "created_at",
        ]

    class Config:
        json_schema_extra = {
            "example": {
                "patient_phone": "+12025551234",
                "language": "en",
                "urgency_flagged": False,
                "call_tracking": {
                    "call_sid": "CA1234567890abcdef",
                    "outcome": "success",
                    "duration_seconds": 180
                }
            }
        }
```

---

### 5. QueueEntry (Collection: `queue_entries`)

**Purpose**: Campaign queue item with retry logic and state tracking

```python
from beanie import Document, Link
from pydantic import Field
from datetime import datetime
from typing import Optional, List
from enum import Enum

class QueueState(str, Enum):
    """Queue entry lifecycle"""
    PENDING = "pending"      # Waiting to be processed
    CALLING = "calling"      # Call in progress
    SUCCESS = "success"      # Call completed successfully
    FAILED = "failed"        # Terminal failure (moved to DLQ)
    RETRYING = "retrying"    # Scheduled for retry

class FailureReason(str, Enum):
    """Call failure classification for retry logic"""
    NO_ANSWER = "no_answer"                  # Retry after 30min
    BUSY = "busy"                            # Retry after 1hr
    FAILED = "failed"                        # Generic failure, retry after 15min
    PERSON_NOT_AVAILABLE = "person_not_available"  # Retry after 2hr
    SHORT_DURATION = "short_duration"        # <30s call, retry after 1hr
    INVALID_NUMBER = "invalid_number"        # Non-retriable → DLQ
    REJECTED = "rejected"                    # Non-retriable → DLQ
    NETWORK_FAILURE = "network_failure"      # Retry after 15min
    TIMEOUT = "timeout"                      # Retry after 1hr

class RetryHistory(BaseModel):
    """Single retry attempt record"""
    attempt_number: int
    attempted_at: datetime
    failure_reason: FailureReason
    error_details: Optional[str] = None

class QueueEntry(Document):
    """
    Campaign queue entry with intelligent retry logic.

    Retry Strategy:
    - NO_ANSWER: 30 minutes
    - BUSY: 1 hour
    - FAILED: 15 minutes
    - PERSON_NOT_AVAILABLE: 2 hours
    - SHORT_DURATION: 1 hour
    - NETWORK_FAILURE: 15 minutes
    - TIMEOUT: 1 hour

    Non-Retriable (→ DLQ):
    - INVALID_NUMBER
    - REJECTED

    Max 3 attempts before DLQ.

    Indexes:
    - campaign_id: Query all entries for campaign
    - state: Find pending/retrying entries for processing
    - next_retry_at: Scheduler finds ready-to-retry entries
    """

    campaign_id: Link[Campaign]
    call_record_id: Optional[Link[CallRecord]] = None  # Populated after call initiated

    patient_phone: str = Field(..., description="E.164 format")
    language: str = Field(default="en")

    # State machine
    state: QueueState = Field(default=QueueState.PENDING)

    # Retry tracking
    retry_count: int = Field(default=0, ge=0, le=3)
    retry_history: List[RetryHistory] = Field(default_factory=list)
    next_retry_at: Optional[datetime] = Field(
        None,
        description="When to retry (None = ready now)"
    )

    # Failure tracking
    last_failure_reason: Optional[FailureReason] = None
    moved_to_dlq: bool = Field(
        default=False,
        description="True if non-retriable or max retries exceeded"
    )
    dlq_reason: Optional[str] = None

    # Audit
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    first_attempted_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    class Settings:
        name = "queue_entries"
        indexes = [
            "campaign_id",
            "state",
            "next_retry_at",
            "moved_to_dlq",
        ]

    class Config:
        json_schema_extra = {
            "example": {
                "patient_phone": "+12025551234",
                "state": "pending",
                "retry_count": 0,
                "moved_to_dlq": False
            }
        }
```

---

## Relationships & Data Flow

### 1. Entity Relationships
```
User (RBAC)
  └─> (no direct references, used for auth only)

Geography
  └─> Campaign (1:many)
      ├─> CallRecord (1:many)
      └─> QueueEntry (1:many)
          └─> CallRecord (1:1, optional until call initiated)
```

### 2. Data Flow: Campaign Execution
```
1. Admin creates Campaign with patient_list
   → Campaign.state = DRAFT
   → Campaign.stats.total_calls = len(patient_list)

2. Admin starts Campaign
   → Campaign.state = ACTIVE
   → Create QueueEntry for each patient
   → QueueEntry.state = PENDING

3. Celery Beat scheduler (every 30s)
   → Find Campaign where state = ACTIVE
   → Find QueueEntry where state = PENDING and next_retry_at <= now
   → Respect time_windows and max_concurrent_calls

4. Celery Worker processes QueueEntry
   → QueueEntry.state = CALLING
   → Create CallRecord with call_tracking.status = "queued"
   → Initiate Twilio call
   → Update CallRecord.call_tracking.call_sid

5. Pipecat voice pipeline executes
   → Update CallRecord.conversation_state (stage transitions)
   → Append to CallRecord.transcript
   → Detect urgency keywords → set CallRecord.urgency_flagged

6. Call completes
   → CallRecord.call_tracking.outcome = SUCCESS | FAILED | etc.
   → CallRecord.feedback populated
   → QueueEntry.state = SUCCESS | FAILED | RETRYING
   → If RETRYING: calculate next_retry_at based on FailureReason
   → If terminal failure or retry_count >= 3: moved_to_dlq = True

7. Campaign completion
   → When all QueueEntry.state in [SUCCESS, FAILED]
   → Campaign.state = COMPLETED
```

### 3. Soft Delete Strategy
- Geography, Campaign, CallRecord use `deleted_at` timestamp
- Deleted records remain queryable with `deleted_at != None` filter
- Retention policy enforces archival/purge based on Geography.retention_policy

---

## Indexes & Performance

### Query Patterns
1. **Auth**: `User.email` (unique index)
2. **Campaign List**: `Campaign.geography_id + Campaign.state`
3. **Queue Processing**: `QueueEntry.state + QueueEntry.next_retry_at`
4. **Call Lookup**: `CallRecord.call_tracking.call_sid` (Twilio webhooks)
5. **Urgent Cases**: `CallRecord.urgency_flagged = True + created_at desc`
6. **Audit Trail**: `CallRecord.campaign_id + created_at desc`

### Compound Indexes (future optimization)
```python
# Campaign filtering
("geography_id", "state", "created_at")

# Queue processing
("campaign_id", "state", "next_retry_at")

# Urgent case review
("urgency_flagged", "created_at")
```

---

## Validation Rules

### Phone Number Format
- **Pattern**: E.164 format (e.g., `+12025551234`)
- **Validation**: Regex `^\+[1-9]\d{1,14}$`
- **Enforced**: Pydantic validator on `patient_phone` fields

### Time Window Edge Cases
- **Midnight crossing**: `start_time=22:00, end_time=02:00` is valid
- **Service layer**: Handles date boundary logic for scheduler

### Retry Limits
- **Max attempts**: 3 per QueueEntry
- **DLQ conditions**: `retry_count >= 3` OR `FailureReason in [INVALID_NUMBER, REJECTED]`

---

## Migration Strategy

### Initial Schema
1. Create collections with indexes via Beanie `init_beanie()`
2. Seed admin user (email/password from environment)
3. No data migrations required for MVP

### Future Extensions
- Add `CampaignTemplate` collection for reusable configs
- Add `CallRecording` collection for audio file metadata (S3/MinIO URLs)
- Add `Alert` collection for DLQ notifications

---

## Summary

**Total Collections**: 5 (User, Geography, Campaign, CallRecord, QueueEntry)

**Total Embedded Models**: 8 (RetentionPolicy, TimeWindow, CampaignConfig, CampaignStats, FeedbackData, ConversationTurn, ConversationState, CallTracking, RetryHistory)

**Total Enums**: 7 (UserRole, CampaignState, DayOfWeek, CallOutcome, ConversationStage, QueueState, FailureReason)

**Key Design Decisions**:
- Beanie ODM for MongoDB (not SQLAlchemy)
- Links for references (User, Geography, Campaign relationships)
- Embedded documents for conversation/tracking data (no independent lifecycle)
- Soft delete with `deleted_at` for compliance audit trail
- Comprehensive indexes for query performance
- Retry logic embedded in QueueEntry model

**Next**: Generate API contracts defining request/response schemas for FastAPI routes.
