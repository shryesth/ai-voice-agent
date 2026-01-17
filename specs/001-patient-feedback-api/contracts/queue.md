# API Contract: Queue Management

**Base Path**: `/api/v1/campaigns/{campaign_id}/queue`, `/api/v1/queue`
**Purpose**: Campaign queue monitoring and Dead Letter Queue (DLQ) management

---

## GET `/api/v1/campaigns/{campaign_id}/queue`

**Description**: Get queue status for campaign (pending, in-progress, retrying entries)

**Authentication**: Required (both Admin and User roles)

**Path Parameters**:
- `campaign_id`: MongoDB ObjectId

**Query Parameters**:
- `state` (optional): Filter by state (pending, calling, retrying, success, failed)
- `skip` (optional, default: 0): Pagination offset
- `limit` (optional, default: 50, max: 100): Page size

**Success Response** (200 OK):
```json
{
  "campaign_id": "65b2c3d4e5f6g7h8i9j0k1l2",
  "total": 150,
  "summary": {
    "pending": 47,
    "calling": 3,
    "retrying": 8,
    "success": 90,
    "failed": 2
  },
  "items": [
    {
      "id": "65d4e5f6g7h8i9j0k1l2m3n4",
      "patient_phone": "+12025551234",
      "state": "retrying",
      "retry_count": 1,
      "next_retry_at": "2026-01-18T15:30:00Z",
      "last_failure_reason": "no_answer",
      "created_at": "2026-01-18T14:00:00Z"
    }
  ]
}
```

**Response Schema**:
```python
class QueueSummary(BaseModel):
    pending: int
    calling: int
    retrying: int
    success: int
    failed: int

class QueueEntryResponse(BaseModel):
    id: str
    patient_phone: str  # Hidden from User role
    state: QueueState
    retry_count: int
    next_retry_at: Optional[datetime]
    last_failure_reason: Optional[FailureReason]
    created_at: datetime
    first_attempted_at: Optional[datetime]
    completed_at: Optional[datetime]

class CampaignQueueResponse(BaseModel):
    campaign_id: str
    total: int
    summary: QueueSummary
    items: List[QueueEntryResponse]
```

**Privacy Note**: `patient_phone` hidden from User role

---

## GET `/api/v1/queue/dlq`

**Description**: Get Dead Letter Queue (failed calls that exhausted retries)

**Authentication**: Required (Admin role only)

**Query Parameters**:
- `campaign_id` (optional): Filter by campaign
- `skip` (optional, default: 0): Pagination offset
- `limit` (optional, default: 50, max: 100): Page size

**Success Response** (200 OK):
```json
{
  "total_dlq_count": 12,
  "items": [
    {
      "id": "65d4e5f6g7h8i9j0k1l2m3n4",
      "campaign_id": "65b2c3d4e5f6g7h8i9j0k1l2",
      "patient_phone": "+12025551234",
      "state": "failed",
      "retry_count": 3,
      "moved_to_dlq": true,
      "dlq_reason": "Max retries (3) exhausted. Last failure: no_answer",
      "retry_history": [
        {
          "attempt_number": 1,
          "attempted_at": "2026-01-18T14:00:00Z",
          "failure_reason": "no_answer",
          "error_details": null
        },
        {
          "attempt_number": 2,
          "attempted_at": "2026-01-18T14:30:00Z",
          "failure_reason": "no_answer",
          "error_details": null
        },
        {
          "attempt_number": 3,
          "attempted_at": "2026-01-18T15:00:00Z",
          "failure_reason": "busy",
          "error_details": null
        }
      ],
      "created_at": "2026-01-18T14:00:00Z",
      "completed_at": "2026-01-18T15:00:30Z"
    }
  ]
}
```

**Response Schema**:
```python
class RetryHistoryResponse(BaseModel):
    attempt_number: int
    attempted_at: datetime
    failure_reason: FailureReason
    error_details: Optional[str]

class DLQEntryResponse(QueueEntryResponse):
    moved_to_dlq: bool
    dlq_reason: Optional[str]
    retry_history: List[RetryHistoryResponse]

class DLQListResponse(BaseModel):
    total_dlq_count: int
    items: List[DLQEntryResponse]
```

**Use Cases**:
- Identify phone numbers with persistent issues
- Detect invalid numbers (INVALID_NUMBER failures)
- Manual review and retry decisions

---

## POST `/api/v1/queue/dlq/{entry_id}/retry`

**Description**: Manually retry a DLQ entry (admin override)

**Authentication**: Required (Admin role only)

**Path Parameters**:
- `entry_id`: MongoDB ObjectId (QueueEntry ID)

**Request Body** (optional):
```json
{
  "reset_retry_count": true,
  "phone_number": "+12025559999"
}
```

**Request Schema**:
```python
class DLQRetryRequest(BaseModel):
    reset_retry_count: bool = Field(
        default=False,
        description="Reset retry count to 0 (fresh start)"
    )
    phone_number: Optional[str] = Field(
        None,
        description="Override phone number if original was invalid"
    )
```

**Success Response** (200 OK):
```json
{
  "id": "65d4e5f6g7h8i9j0k1l2m3n4",
  "state": "pending",
  "retry_count": 0,
  "moved_to_dlq": false,
  "next_retry_at": null,
  "message": "Entry removed from DLQ and queued for retry"
}
```

**Response Schema**:
```python
class DLQRetryResponse(BaseModel):
    id: str
    state: QueueState
    retry_count: int
    moved_to_dlq: bool
    next_retry_at: Optional[datetime]
    message: str
```

**Side Effects**:
- Sets `moved_to_dlq = false`
- Sets `state = PENDING`
- Optionally resets `retry_count = 0`
- Optionally updates `patient_phone` if provided

**Error Responses**:

- **404 Not Found** - Entry doesn't exist
- **409 Conflict** - Entry not in DLQ
```json
{
  "detail": "Entry is not in DLQ (current state: pending)"
}
```

---

## DELETE `/api/v1/queue/dlq/{entry_id}`

**Description**: Permanently remove entry from DLQ (acknowledge failure)

**Authentication**: Required (Admin role only)

**Path Parameters**:
- `entry_id`: MongoDB ObjectId

**Success Response** (204 No Content)

**Side Effects**:
- Deletes `QueueEntry` record
- Does NOT delete associated `CallRecord` (preserved for audit)

**Error Responses**:

- **404 Not Found** - Entry doesn't exist

---

## GET `/api/v1/queue/stats`

**Description**: Global queue statistics across all campaigns

**Authentication**: Required (Admin role only)

**Success Response** (200 OK):
```json
{
  "timestamp": "2026-01-18T15:30:00Z",
  "global_stats": {
    "total_pending": 120,
    "total_calling": 15,
    "total_retrying": 25,
    "total_dlq": 12
  },
  "by_campaign": [
    {
      "campaign_id": "65b2c3d4e5f6g7h8i9j0k1l2",
      "campaign_name": "Post-Vaccination Feedback - January 2026",
      "pending": 47,
      "calling": 3,
      "retrying": 8,
      "dlq": 2
    }
  ],
  "retry_breakdown": {
    "no_answer": 12,
    "busy": 5,
    "failed": 3,
    "person_not_available": 3,
    "network_failure": 2
  }
}
```

**Response Schema**:
```python
class GlobalQueueStats(BaseModel):
    total_pending: int
    total_calling: int
    total_retrying: int
    total_dlq: int

class CampaignQueueStats(BaseModel):
    campaign_id: str
    campaign_name: str
    pending: int
    calling: int
    retrying: int
    dlq: int

class RetryBreakdown(BaseModel):
    no_answer: int
    busy: int
    failed: int
    person_not_available: int
    network_failure: int

class QueueStatsResponse(BaseModel):
    timestamp: datetime
    global_stats: GlobalQueueStats
    by_campaign: List[CampaignQueueStats]
    retry_breakdown: RetryBreakdown
```

**Use Cases**:
- Monitor queue health across all campaigns
- Identify campaigns with high retry rates
- Detect systemic issues (e.g., all failures are "network_failure")

---

## Internal: Queue Processor (Celery Task)

**Not an API endpoint** - internal Celery task documentation

**Task Name**: `process_campaign_queues`

**Schedule**: Every 30 seconds (Celery Beat)

**Logic**:
1. Find all campaigns with `state = ACTIVE`
2. For each campaign:
   - Check time window constraints (UTC)
   - Query `QueueEntry` where `state = PENDING` and `next_retry_at <= now`
   - Respect `max_concurrent_calls` limit
   - Create Celery task for each call: `initiate_patient_call.delay(entry_id)`

**Retry Logic**:
```python
RETRY_DELAYS = {
    FailureReason.NO_ANSWER: timedelta(minutes=30),
    FailureReason.BUSY: timedelta(hours=1),
    FailureReason.FAILED: timedelta(minutes=15),
    FailureReason.PERSON_NOT_AVAILABLE: timedelta(hours=2),
    FailureReason.SHORT_DURATION: timedelta(hours=1),
    FailureReason.NETWORK_FAILURE: timedelta(minutes=15),
    FailureReason.TIMEOUT: timedelta(hours=1),
}

NON_RETRIABLE = {
    FailureReason.INVALID_NUMBER,
    FailureReason.REJECTED,
}
```

**DLQ Criteria**:
- `retry_count >= 3` → Move to DLQ
- `failure_reason in NON_RETRIABLE` → Move to DLQ immediately

---

## Business Rules

### Retry Strategy
- Max 3 attempts before DLQ
- Delay between retries based on failure reason
- Non-retriable failures skip retries entirely

### Time Window Enforcement
- Queue processor checks campaign `time_windows`
- If current time outside all windows → skip campaign until next window
- Midnight-crossing windows handled correctly

### Concurrency Limits
- Count current `QueueEntry` with `state = CALLING` for campaign
- If count >= `max_concurrent_calls` → skip campaign until slots available

### DLQ Alerts
- Prometheus metric: `call_queue_dlq_count{queue="patient-feedback"}`
- Alert rule: trigger if DLQ count > 10

---

## Performance Requirements

- Queue status query: < 5 seconds (SC-008)
- Queue scheduler execution: < 2 seconds per cycle (SC-018)
- DLQ retry operation: < 3 seconds
