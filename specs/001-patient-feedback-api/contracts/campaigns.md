# API Contract: Campaigns

**Base Path**: `/api/v1/campaigns`, `/api/v1/geographies/{geography_id}/campaigns`
**Purpose**: Patient feedback campaign management and state control

---

## POST `/api/v1/geographies/{geography_id}/campaigns`

**Description**: Create new campaign within geography

**Authentication**: Required (Admin role only)

**Path Parameters**:
- `geography_id`: MongoDB ObjectId

**Request Body**:
```json
{
  "name": "Post-Vaccination Feedback - January 2026",
  "config": {
    "max_concurrent_calls": 10,
    "time_windows": [
      {
        "start_time": "09:00:00",
        "end_time": "17:00:00",
        "days_of_week": ["monday", "tuesday", "wednesday", "thursday", "friday"]
      }
    ],
    "patient_list": [
      "+12025551234",
      "+12025555678",
      "+13105559999"
    ],
    "language_preference": "en"
  }
}
```

**Request Schema**:
```python
class TimeWindowCreate(BaseModel):
    start_time: time
    end_time: time
    days_of_week: List[DayOfWeek] = Field(default_factory=lambda: list(DayOfWeek))

class CampaignConfigCreate(BaseModel):
    max_concurrent_calls: int = Field(default=10, ge=1, le=50)
    time_windows: List[TimeWindowCreate] = Field(default_factory=list)
    patient_list: List[str] = Field(..., min_items=1)  # E.164 format
    language_preference: str = Field(default="en", pattern="^(en|es|fr|ht)$")

class CampaignCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    config: CampaignConfigCreate
```

**Success Response** (201 Created):
```json
{
  "id": "65b2c3d4e5f6g7h8i9j0k1l2",
  "geography_id": "65a1b2c3d4e5f6g7h8i9j0k1",
  "name": "Post-Vaccination Feedback - January 2026",
  "state": "draft",
  "config": {
    "max_concurrent_calls": 10,
    "time_windows": [
      {
        "start_time": "09:00:00",
        "end_time": "17:00:00",
        "days_of_week": ["monday", "tuesday", "wednesday", "thursday", "friday"]
      }
    ],
    "patient_list": ["+12025551234", "+12025555678", "+13105559999"],
    "language_preference": "en"
  },
  "stats": {
    "total_calls": 3,
    "queued_count": 0,
    "in_progress_count": 0,
    "completed_count": 0,
    "failed_count": 0,
    "urgent_flagged_count": 0
  },
  "created_at": "2026-01-18T14:30:00Z",
  "updated_at": "2026-01-18T14:30:00Z"
}
```

**Response Schema**:
```python
class TimeWindowResponse(BaseModel):
    start_time: time
    end_time: time
    days_of_week: List[DayOfWeek]

class CampaignConfigResponse(BaseModel):
    max_concurrent_calls: int
    time_windows: List[TimeWindowResponse]
    patient_list: List[str]  # Hidden from User role
    language_preference: str

class CampaignStatsResponse(BaseModel):
    total_calls: int
    queued_count: int
    in_progress_count: int
    completed_count: int
    failed_count: int
    urgent_flagged_count: int

class CampaignResponse(BaseModel):
    id: str
    geography_id: str
    name: str
    state: CampaignState
    config: CampaignConfigResponse
    stats: CampaignStatsResponse
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
```

**Error Responses**:

- **403 Forbidden** - User role lacks permission
- **404 Not Found** - Geography doesn't exist
- **422 Unprocessable Entity** - Invalid phone number format
```json
{
  "detail": [
    {
      "loc": ["body", "config", "patient_list", 0],
      "msg": "Invalid E.164 phone number format. Expected: +12025551234",
      "type": "value_error.phone"
    }
  ]
}
```

---

## GET `/api/v1/campaigns`

**Description**: List all campaigns with optional filtering

**Authentication**: Required (both Admin and User roles)

**Query Parameters**:
- `geography_id` (optional): Filter by geography
- `state` (optional): Filter by state (draft, active, paused, completed, cancelled)
- `skip` (optional, default: 0): Pagination offset
- `limit` (optional, default: 50, max: 100): Page size

**Example**: `GET /api/v1/campaigns?geography_id=65a1b2c3d4e5f6g7h8i9j0k1&state=active`

**Success Response** (200 OK):
```json
{
  "total": 15,
  "skip": 0,
  "limit": 50,
  "items": [
    {
      "id": "65b2c3d4e5f6g7h8i9j0k1l2",
      "geography_id": "65a1b2c3d4e5f6g7h8i9j0k1",
      "name": "Post-Vaccination Feedback - January 2026",
      "state": "active",
      "stats": {
        "total_calls": 150,
        "queued_count": 47,
        "in_progress_count": 3,
        "completed_count": 98,
        "failed_count": 2,
        "urgent_flagged_count": 5
      },
      "created_at": "2026-01-18T14:30:00Z"
    }
  ]
}
```

**Response Schema**:
```python
class CampaignListResponse(BaseModel):
    total: int
    skip: int
    limit: int
    items: List[CampaignResponse]
```

**Note**: `patient_list` hidden from User role responses (privacy protection)

---

## GET `/api/v1/campaigns/{campaign_id}`

**Description**: Get campaign by ID with full details

**Authentication**: Required (both Admin and User roles)

**Path Parameters**:
- `campaign_id`: MongoDB ObjectId

**Success Response** (200 OK):
```json
{
  "id": "65b2c3d4e5f6g7h8i9j0k1l2",
  "geography_id": "65a1b2c3d4e5f6g7h8i9j0k1",
  "name": "Post-Vaccination Feedback - January 2026",
  "state": "active",
  "config": {
    "max_concurrent_calls": 10,
    "time_windows": [
      {
        "start_time": "09:00:00",
        "end_time": "17:00:00",
        "days_of_week": ["monday", "tuesday", "wednesday", "thursday", "friday"]
      }
    ],
    "patient_list": ["+12025551234", "+12025555678"],
    "language_preference": "en"
  },
  "stats": {
    "total_calls": 150,
    "queued_count": 47,
    "in_progress_count": 3,
    "completed_count": 98,
    "failed_count": 2,
    "urgent_flagged_count": 5
  },
  "created_at": "2026-01-18T14:30:00Z",
  "started_at": "2026-01-18T15:00:00Z"
}
```

**Response Schema**: `CampaignResponse`

**Error Responses**:

- **404 Not Found** - Campaign doesn't exist

---

## PATCH `/api/v1/campaigns/{campaign_id}`

**Description**: Update campaign configuration (only allowed in DRAFT or PAUSED state)

**Authentication**: Required (Admin role only)

**Path Parameters**:
- `campaign_id`: MongoDB ObjectId

**Request Body** (all fields optional):
```json
{
  "name": "Updated Campaign Name",
  "config": {
    "max_concurrent_calls": 15,
    "time_windows": [
      {
        "start_time": "08:00:00",
        "end_time": "20:00:00",
        "days_of_week": ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]
      }
    ]
  }
}
```

**Request Schema**:
```python
class CampaignUpdate(BaseModel):
    name: Optional[str] = None
    config: Optional[CampaignConfigCreate] = None
```

**Success Response** (200 OK): `CampaignResponse`

**Error Responses**:

- **403 Forbidden** - User role lacks permission
- **409 Conflict** - Campaign is ACTIVE (cannot modify running campaign)
```json
{
  "detail": "Cannot modify active campaign. Pause campaign first."
}
```

---

## POST `/api/v1/campaigns/{campaign_id}/start`

**Description**: Start campaign (transition from DRAFT → ACTIVE)

**Authentication**: Required (Admin role only)

**Path Parameters**:
- `campaign_id`: MongoDB ObjectId

**Success Response** (200 OK):
```json
{
  "id": "65b2c3d4e5f6g7h8i9j0k1l2",
  "state": "active",
  "started_at": "2026-01-18T15:00:00Z",
  "message": "Campaign started. Queue entries created for 150 patients."
}
```

**Response Schema**:
```python
class CampaignStateChangeResponse(BaseModel):
    id: str
    state: CampaignState
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    message: str
```

**Side Effects**:
- Creates `QueueEntry` for each phone number in `patient_list`
- Updates `stats.total_calls` and `stats.queued_count`
- Sets `started_at` timestamp

**Error Responses**:

- **409 Conflict** - Campaign already started
```json
{
  "detail": "Campaign is already active"
}
```

---

## POST `/api/v1/campaigns/{campaign_id}/pause`

**Description**: Pause campaign (transition from ACTIVE → PAUSED)

**Authentication**: Required (Admin role only)

**Path Parameters**:
- `campaign_id`: MongoDB ObjectId

**Success Response** (200 OK):
```json
{
  "id": "65b2c3d4e5f6g7h8i9j0k1l2",
  "state": "paused",
  "message": "Campaign paused. 3 calls in progress will complete. 47 queued calls will not be processed until resumed."
}
```

**Response Schema**: `CampaignStateChangeResponse`

**Side Effects**:
- In-progress calls continue to completion
- No new calls initiated from queue
- Queue entries remain in PENDING state

---

## POST `/api/v1/campaigns/{campaign_id}/resume`

**Description**: Resume paused campaign (transition from PAUSED → ACTIVE)

**Authentication**: Required (Admin role only)

**Success Response** (200 OK):
```json
{
  "id": "65b2c3d4e5f6g7h8i9j0k1l2",
  "state": "active",
  "message": "Campaign resumed. Processing 47 queued calls."
}
```

---

## POST `/api/v1/campaigns/{campaign_id}/cancel`

**Description**: Cancel campaign permanently (transition to CANCELLED state)

**Authentication**: Required (Admin role only)

**Success Response** (200 OK):
```json
{
  "id": "65b2c3d4e5f6g7h8i9j0k1l2",
  "state": "cancelled",
  "completed_at": "2026-01-18T16:30:00Z",
  "message": "Campaign cancelled. All pending calls removed from queue."
}
```

**Side Effects**:
- In-progress calls continue to completion
- All PENDING queue entries removed or marked as cancelled
- Cannot be resumed (terminal state)

---

## GET `/api/v1/campaigns/{campaign_id}/status`

**Description**: Get real-time campaign execution status

**Authentication**: Required (both Admin and User roles)

**Path Parameters**:
- `campaign_id`: MongoDB ObjectId

**Success Response** (200 OK):
```json
{
  "campaign_id": "65b2c3d4e5f6g7h8i9j0k1l2",
  "state": "active",
  "stats": {
    "total_calls": 150,
    "queued_count": 47,
    "in_progress_count": 3,
    "completed_count": 98,
    "failed_count": 2,
    "urgent_flagged_count": 5
  },
  "progress_percent": 65.3,
  "estimated_completion": "2026-01-18T18:45:00Z",
  "current_concurrency": 3,
  "next_execution_window": {
    "starts_at": "2026-01-19T09:00:00Z",
    "ends_at": "2026-01-19T17:00:00Z"
  }
}
```

**Response Schema**:
```python
class ExecutionWindow(BaseModel):
    starts_at: datetime
    ends_at: datetime

class CampaignStatusResponse(BaseModel):
    campaign_id: str
    state: CampaignState
    stats: CampaignStatsResponse
    progress_percent: float
    estimated_completion: Optional[datetime]
    current_concurrency: int
    next_execution_window: Optional[ExecutionWindow]
```

**Performance**: Must respond < 5 seconds (SC-008)

---

## Business Rules

### State Transitions
```
DRAFT → ACTIVE (via /start)
ACTIVE → PAUSED (via /pause)
PAUSED → ACTIVE (via /resume)
ACTIVE → COMPLETED (automatic when all calls processed)
ACTIVE/PAUSED → CANCELLED (via /cancel)
```

### Queue Creation
- On `/start`: Create one `QueueEntry` per phone in `patient_list`
- Duplicate phone numbers skipped (deduplicated before queue creation)

### Time Window Validation
- Midnight-crossing windows allowed (e.g., 22:00-02:00)
- Service layer handles date boundary logic

### Concurrency Enforcement
- Scheduler respects `max_concurrent_calls` limit
- Pending calls wait in queue until slot available

---

## Performance Requirements

- Campaign creation: < 30 seconds (SC-003)
- Campaign status query: < 5 seconds (SC-008)
- State transitions: < 2 seconds
