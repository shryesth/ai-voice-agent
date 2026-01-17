# API Contract: Geographies

**Base Path**: `/api/v1/geographies`
**Purpose**: Geographic region management with configurable retention policies

---

## POST `/api/v1/geographies`

**Description**: Create new geography (regional operational unit)

**Authentication**: Required (Admin role only)

**Request Body**:
```json
{
  "name": "North America - East Coast",
  "description": "US East Coast operations covering NY, NJ, PA, MD",
  "region_code": "US-EAST",
  "retention_policy": {
    "retention_days": 2555,
    "archival_destination": "s3://backups/us-east/",
    "auto_purge_enabled": false,
    "compliance_notes": "HIPAA requires 7-year retention (2555 days)"
  },
  "metadata": {
    "timezone": "America/New_York",
    "primary_language": "en",
    "contact_email": "ops-east@example.com"
  }
}
```

**Request Schema**:
```python
class RetentionPolicyCreate(BaseModel):
    retention_days: Optional[int] = None  # None = indefinite
    archival_destination: Optional[str] = None
    auto_purge_enabled: bool = False
    compliance_notes: Optional[str] = None

class GeographyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    region_code: Optional[str] = Field(None, max_length=20)
    retention_policy: RetentionPolicyCreate = Field(default_factory=RetentionPolicyCreate)
    metadata: Dict[str, Any] = Field(default_factory=dict)
```

**Success Response** (201 Created):
```json
{
  "id": "65a1b2c3d4e5f6g7h8i9j0k1",
  "name": "North America - East Coast",
  "description": "US East Coast operations covering NY, NJ, PA, MD",
  "region_code": "US-EAST",
  "retention_policy": {
    "retention_days": 2555,
    "archival_destination": "s3://backups/us-east/",
    "auto_purge_enabled": false,
    "compliance_notes": "HIPAA requires 7-year retention (2555 days)"
  },
  "metadata": {
    "timezone": "America/New_York",
    "primary_language": "en",
    "contact_email": "ops-east@example.com"
  },
  "created_at": "2026-01-18T14:30:00Z",
  "updated_at": "2026-01-18T14:30:00Z"
}
```

**Response Schema**:
```python
class RetentionPolicyResponse(RetentionPolicyCreate):
    pass

class GeographyResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    region_code: Optional[str]
    retention_policy: RetentionPolicyResponse
    metadata: Dict[str, Any]
    created_at: datetime
    updated_at: datetime
```

**Error Responses**:

- **403 Forbidden** - User role lacks permission
```json
{
  "detail": "Admin role required to create geographies"
}
```

- **409 Conflict** - Duplicate geography name
```json
{
  "detail": "Geography with name 'North America - East Coast' already exists"
}
```

---

## GET `/api/v1/geographies`

**Description**: List all geographies (with optional filtering)

**Authentication**: Required (both Admin and User roles)

**Query Parameters**:
- `region_code` (optional): Filter by region code
- `skip` (optional, default: 0): Pagination offset
- `limit` (optional, default: 50, max: 100): Page size

**Example**: `GET /api/v1/geographies?region_code=US-EAST&limit=20`

**Success Response** (200 OK):
```json
{
  "total": 42,
  "skip": 0,
  "limit": 50,
  "items": [
    {
      "id": "65a1b2c3d4e5f6g7h8i9j0k1",
      "name": "North America - East Coast",
      "region_code": "US-EAST",
      "retention_policy": {
        "retention_days": 2555,
        "archival_destination": "s3://backups/us-east/",
        "auto_purge_enabled": false
      },
      "created_at": "2026-01-18T14:30:00Z",
      "updated_at": "2026-01-18T14:30:00Z"
    }
  ]
}
```

**Response Schema**:
```python
class GeographyListResponse(BaseModel):
    total: int
    skip: int
    limit: int
    items: List[GeographyResponse]
```

---

## GET `/api/v1/geographies/{geography_id}`

**Description**: Get geography by ID with full details

**Authentication**: Required (both Admin and User roles)

**Path Parameters**:
- `geography_id`: MongoDB ObjectId

**Success Response** (200 OK):
```json
{
  "id": "65a1b2c3d4e5f6g7h8i9j0k1",
  "name": "North America - East Coast",
  "description": "US East Coast operations covering NY, NJ, PA, MD",
  "region_code": "US-EAST",
  "retention_policy": {
    "retention_days": 2555,
    "archival_destination": "s3://backups/us-east/",
    "auto_purge_enabled": false,
    "compliance_notes": "HIPAA requires 7-year retention (2555 days)"
  },
  "metadata": {
    "timezone": "America/New_York",
    "primary_language": "en",
    "contact_email": "ops-east@example.com"
  },
  "created_at": "2026-01-18T14:30:00Z",
  "updated_at": "2026-01-18T14:30:00Z"
}
```

**Response Schema**: `GeographyResponse`

**Error Responses**:

- **404 Not Found** - Geography doesn't exist
```json
{
  "detail": "Geography not found"
}
```

---

## PATCH `/api/v1/geographies/{geography_id}`

**Description**: Update geography (partial update)

**Authentication**: Required (Admin role only)

**Path Parameters**:
- `geography_id`: MongoDB ObjectId

**Request Body** (all fields optional):
```json
{
  "description": "Updated description",
  "retention_policy": {
    "retention_days": 3650,
    "compliance_notes": "Extended to 10 years per new regulation"
  }
}
```

**Request Schema**:
```python
class GeographyUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    region_code: Optional[str] = None
    retention_policy: Optional[RetentionPolicyCreate] = None
    metadata: Optional[Dict[str, Any]] = None
```

**Success Response** (200 OK):
```json
{
  "id": "65a1b2c3d4e5f6g7h8i9j0k1",
  "name": "North America - East Coast",
  "description": "Updated description",
  "retention_policy": {
    "retention_days": 3650,
    "compliance_notes": "Extended to 10 years per new regulation"
  },
  "updated_at": "2026-01-18T15:45:00Z"
}
```

**Response Schema**: `GeographyResponse`

**Error Responses**:

- **403 Forbidden** - User role lacks permission
- **404 Not Found** - Geography doesn't exist

---

## DELETE `/api/v1/geographies/{geography_id}`

**Description**: Soft delete geography (sets `deleted_at` timestamp)

**Authentication**: Required (Admin role only)

**Path Parameters**:
- `geography_id`: MongoDB ObjectId

**Success Response** (204 No Content)

**Error Responses**:

- **403 Forbidden** - User role lacks permission
- **404 Not Found** - Geography doesn't exist
- **409 Conflict** - Geography has active campaigns
```json
{
  "detail": "Cannot delete geography with active campaigns. Pause or complete campaigns first."
}
```

---

## Business Rules

### Retention Policy Defaults
- If not specified: indefinite retention (`retention_days = None`)
- `auto_purge_enabled = false` by default (require explicit opt-in)

### Geography Deletion
- Soft delete only (set `deleted_at` timestamp)
- Prevent deletion if geography has active campaigns
- Deleted geographies remain queryable with `?include_deleted=true` (Admin only)

### Naming Constraints
- Geography names must be unique (case-insensitive)
- Region codes are optional but recommended for filtering

---

## Performance Requirements

- Geography creation: < 30 seconds (SC-003, includes campaign creation in same request flow)
- List geographies: < 2 seconds for 100 items
