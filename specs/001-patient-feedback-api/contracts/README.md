# API Contracts: Patient Feedback Collection API

**Feature**: Patient Feedback Collection API
**Date**: 2026-01-18
**Purpose**: OpenAPI-compatible contract specifications for all FastAPI endpoints

---

## Overview

This directory contains detailed API contract specifications for the Patient Feedback Collection API. Each file documents request/response schemas, authentication requirements, error codes, and business rules for a specific domain.

---

## Contract Files

### [auth.md](./auth.md) - Authentication
**Base Path**: `/api/v1/auth`

Endpoints:
- `POST /login` - User authentication, receive JWT access token
- `GET /me` - Get current authenticated user info
- `POST /logout` - Invalidate current access token

**Key Features**:
- JWT tokens with 24-hour expiration
- Role-based access control (Admin, User)
- Bcrypt password hashing

---

### [health.md](./health.md) - Health & Metrics
**Base Path**: `/api/v1/health`, `/api/v1/metrics`

Endpoints:
- `GET /health` - Basic health check (public)
- `GET /health/ready` - Readiness check with dependency validation
- `GET /health/live` - Liveness check (Kubernetes/Docker probe)
- `GET /metrics` - Application metrics in custom JSON format
- `GET /metrics/prometheus` - Prometheus-compatible metrics export

**Key Features**:
- Dependency health checks (MongoDB, Redis, Twilio)
- Cached results (5-second TTL) to avoid hammering dependencies
- Prometheus metrics for monitoring (queue depth, call duration, DLQ count)

---

### [geographies.md](./geographies.md) - Geography Management
**Base Path**: `/api/v1/geographies`

Endpoints:
- `POST /geographies` - Create geography (Admin only)
- `GET /geographies` - List geographies with filtering
- `GET /geographies/{id}` - Get geography details
- `PATCH /geographies/{id}` - Update geography (Admin only)
- `DELETE /geographies/{id}` - Soft delete geography (Admin only)

**Key Features**:
- Configurable data retention policies per geography
- Compliance notes for regulatory requirements
- Metadata storage for operational context

---

### [campaigns.md](./campaigns.md) - Campaign Management
**Base Path**: `/api/v1/campaigns`, `/api/v1/geographies/{geography_id}/campaigns`

Endpoints:
- `POST /geographies/{geography_id}/campaigns` - Create campaign (Admin only)
- `GET /campaigns` - List campaigns with filtering
- `GET /campaigns/{id}` - Get campaign details
- `PATCH /campaigns/{id}` - Update campaign (Admin only, DRAFT/PAUSED only)
- `POST /campaigns/{id}/start` - Start campaign (DRAFT → ACTIVE)
- `POST /campaigns/{id}/pause` - Pause campaign (ACTIVE → PAUSED)
- `POST /campaigns/{id}/resume` - Resume campaign (PAUSED → ACTIVE)
- `POST /campaigns/{id}/cancel` - Cancel campaign (terminal state)
- `GET /campaigns/{id}/status` - Get real-time campaign status

**Key Features**:
- Time window configuration (UTC-based, day-of-week filtering)
- Concurrency limits (default: 10 simultaneous calls)
- State machine: DRAFT → ACTIVE ↔ PAUSED → COMPLETED/CANCELLED
- Real-time progress tracking (queued, in-progress, completed, failed counts)

---

### [calls.md](./calls.md) - Call Management
**Base Path**: `/api/v1/campaigns/{campaign_id}/calls`, `/api/v1/calls`

Endpoints:
- `POST /campaigns/{campaign_id}/calls/test` - Initiate test call (Admin only)
- `POST /campaigns/{campaign_id}/calls/test-scenario` - Simulate test scenario (Admin only)
- `GET /calls/{id}` - Get call record with full transcript
- `GET /campaigns/{campaign_id}/calls` - List calls for campaign
- `GET /calls/urgent` - Get urgent-flagged calls for clinical review
- `GET /campaigns/{campaign_id}/calls/export` - Export call data as CSV (Admin only)
- `POST /webhooks/twilio/status` - Twilio status callback (internal webhook)

**Key Features**:
- Full conversation transcript with speaker identification
- Urgency detection (keywords: hospital, severe, can't breathe)
- Call outcome classification (success, no_answer, failed, etc.)
- Privacy controls (patient phone numbers hidden from User role)

---

### [queue.md](./queue.md) - Queue Management
**Base Path**: `/api/v1/campaigns/{campaign_id}/queue`, `/api/v1/queue`

Endpoints:
- `GET /campaigns/{campaign_id}/queue` - Get queue status for campaign
- `GET /queue/dlq` - Get Dead Letter Queue entries (Admin only)
- `POST /queue/dlq/{entry_id}/retry` - Manually retry DLQ entry (Admin only)
- `DELETE /queue/dlq/{entry_id}` - Remove entry from DLQ (Admin only)
- `GET /queue/stats` - Global queue statistics (Admin only)

**Key Features**:
- Intelligent retry strategy (per-failure-reason delays)
- Dead Letter Queue for exhausted retries
- Max 3 retry attempts before DLQ
- Queue scheduler runs every 30 seconds (Celery Beat)

---

## Authentication & Authorization

### Access Levels

| Endpoint | Public | User Role | Admin Role |
|----------|--------|-----------|------------|
| `/api/v1/health/*` | ✅ | ✅ | ✅ |
| `/api/v1/auth/login` | ✅ | - | - |
| `/api/v1/metrics` | - | ✅ | ✅ |
| `/api/v1/geographies` (GET) | - | ✅ | ✅ |
| `/api/v1/geographies` (POST/PATCH/DELETE) | - | - | ✅ |
| `/api/v1/campaigns` (GET) | - | ✅ | ✅ |
| `/api/v1/campaigns` (POST/PATCH) | - | - | ✅ |
| `/api/v1/campaigns/{id}/start|pause|resume|cancel` | - | - | ✅ |
| `/api/v1/calls` (GET) | - | ✅ | ✅ |
| `/api/v1/calls/test*` | - | - | ✅ |
| `/api/v1/queue/dlq` | - | - | ✅ |

### Token Format
- Type: JWT (HS256 algorithm)
- Header: `Authorization: Bearer <token>`
- Payload: `{user_id, email, role, exp}`
- Expiration: 24 hours (86400 seconds)

---

## Error Handling

### Standard Error Response
```json
{
  "detail": "Error message or validation errors array"
}
```

### HTTP Status Codes

| Code | Meaning | When Used |
|------|---------|-----------|
| 200 | OK | Successful GET/PATCH request |
| 201 | Created | Successful POST (resource created) |
| 202 | Accepted | Async operation queued (test calls) |
| 204 | No Content | Successful DELETE |
| 400 | Bad Request | Invalid request data |
| 401 | Unauthorized | Missing or invalid token |
| 403 | Forbidden | Valid token, insufficient permissions |
| 404 | Not Found | Resource doesn't exist |
| 409 | Conflict | Resource conflict (duplicate name, invalid state transition) |
| 422 | Unprocessable Entity | Validation error (Pydantic) |
| 500 | Internal Server Error | Unhandled system error |
| 503 | Service Unavailable | Dependency unhealthy (MongoDB down) |

---

## Performance Requirements

From spec success criteria (SC-001 to SC-024):

| Endpoint | Max Response Time |
|----------|------------------|
| `GET /health` | 500ms |
| `POST /auth/login` | 2s |
| `POST /geographies/{id}/campaigns` | 30s |
| `POST /campaigns/{id}/calls/test` | 10s |
| `GET /campaigns/{id}/status` | 5s |
| `GET /metrics` | 1s |

---

## Privacy & Data Protection

### Phone Number Redaction
- User role: `patient_phone` field hidden in responses
- Admin role: Full access to phone numbers
- Export endpoint: Admin only

### Sensitive Data Handling
- Passwords: Bcrypt hashed, never returned in responses
- API keys: Excluded from error messages
- Transcripts: Visible to both Admin and User (clinical review requirement)

### Audit Trail
- All authentication attempts logged
- All API access logged with user ID and timestamp
- Soft delete for geographies/campaigns (compliance requirement)

---

## Rate Limiting (Future)

Planned rate limits for MVP+1:
- `/api/v1/auth/login`: 5 attempts per 15 minutes per IP
- `/api/v1/calls/test`: 10 requests per hour per campaign
- All other endpoints: 1000 requests per hour per user

---

## Versioning Strategy

### API Versioning
- Current version: `/api/v1/`
- Version in URL path (not headers)
- Breaking changes: Increment major version → `/api/v2/`
- Backwards-compatible changes: Same version

### Contract Evolution
- New optional fields: No version bump
- New required fields: Major version bump
- Removed fields: Major version bump (deprecate first)

---

## Implementation Notes

### FastAPI Integration
All schemas in these contracts map directly to Pydantic models:
```python
from pydantic import BaseModel, Field, EmailStr

class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)

@app.post("/api/v1/auth/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    ...
```

### OpenAPI Documentation
FastAPI auto-generates OpenAPI 3.0 schema from these contracts:
- Interactive docs: `/docs` (Swagger UI)
- ReDoc: `/redoc`
- JSON schema: `/openapi.json`

### Contract Testing
Contracts serve as basis for contract tests:
```python
# tests/contract/test_auth.py
def test_login_success(client):
    response = client.post("/api/v1/auth/login", json={
        "email": "admin@example.com",
        "password": "secure_password_123"
    })
    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"
```

---

## Next Steps

1. **Phase 1 Complete**: Contracts defined ✅
2. **Phase 2**: Generate `tasks.md` with implementation tasks (`/speckit.tasks` command)
3. **Implementation**: Follow TDD workflow (tests first, then implementation)
4. **Validation**: Contract tests verify API matches these specifications

---

## Related Documentation

- [spec.md](../spec.md) - Feature specification with user stories and requirements
- [data-model.md](../data-model.md) - Beanie ODM models and database schema
- [research.md](../research.md) - Technology decisions and configuration options
- [plan.md](../plan.md) - Implementation plan and architecture
