# Nexus HMIS Integration

This document describes the integration between Acme Supervisor and Nexus HMIS for automated vaccination verification calls.

## Table of Contents

1. [Overview](#overview)
2. [Nexus API Specification](#nexus-api-specification)
3. [Architecture](#architecture)
4. [Queue Configuration](#queue-configuration)
5. [Data Flow](#data-flow)
6. [API Reference](#api-reference)
7. [Error Handling](#error-handling)
8. [Deployment](#deployment)

---

## Overview

The Nexus integration enables automated vaccination verification calls by:

1. **Pulling** pending verifications from Nexus HMIS
2. **Processing** them through the managed queue system
3. **Making** verification calls via Twilio
4. **Pushing** results back to Nexus

### Multi-Environment Support

Each Nexus environment (staging, haiti, honduras) operates as a separate queue with:
- Independent API credentials
- Separate time windows
- Isolated retry strategies
- Per-queue recording storage

---

## Nexus API Specification

### Base URLs

| Environment | Base URL |
|-------------|----------|
| Staging | `https://nexus-staging.acme.org/api/v1` |
| Haiti | `https://nexus.hti.acme.org/api/v1` |
| Honduras | `https://nexus.hnd.acme.org/api/v1` |

### Authentication

All requests require Bearer token authentication:
```
Authorization: Bearer <api_key>
```

### Endpoints

#### GET /hmis/client-visits/verification

Fetch pending client visit verifications.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `date_from` | string (date) | No | Start date filter (YYYY-MM-DD) |
| `date_to` | string (date) | No | End date filter (YYYY-MM-DD) |
| `page` | integer | No | Page number (default: 1) |
| `pageSize` | integer | No | Items per page (default: 50, max: 100) |

**Response (200 OK):**

```json
{
  "items": [
    {
      "id": 12345,
      "status": 999,
      "canBeChanged": true,
      "contactClientSptId": "SPT-001",
      "contactName": "Maria Garcia",
      "contactGender": "female",
      "contactPhones": ["+50412345678", "+50487654321"],
      "contactPhoneOwnerName": "Maria Garcia",
      "eventInfo": {
        "eventDate": "2025-01-15",
        "eventFacility": "Centro de Salud La Esperanza",
        "eventType": "vaccination",
        "attributes": [
          {"name": "visitType", "value": "routine"}
        ],
        "vaccineDoses": [
          {"name": "BCG", "administered": true},
          {"name": "Hepatitis B", "administered": true}
        ],
        "sptDocumentIds": [
          {"name": "Vaccination Card", "url": "https://...", "image": "base64..."}
        ]
      },
      "recordingUrl": null,
      "isVisitConfirmed": null
    }
  ],
  "total": 150,
  "page": 1,
  "page_size": 50,
  "pages": 3,
  "has_next": true,
  "has_previous": false
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `id` | integer | Unique verification ID |
| `status` | integer | Status code (999 = pending) |
| `canBeChanged` | boolean | Whether verification can be modified |
| `contactName` | string | Name of the contact person |
| `contactPhones` | string[] | List of phone numbers (E.164 format) |
| `contactGender` | string | Gender: "male", "female", or null |
| `eventInfo.eventDate` | string | Date of the visit (YYYY-MM-DD) |
| `eventInfo.eventFacility` | string | Name of the health facility |
| `eventInfo.eventType` | string | Type of event (e.g., "vaccination") |
| `eventInfo.vaccineDoses` | object[] | List of vaccines administered |
| `recordingUrl` | string | URL to call recording (null if not set) |
| `isVisitConfirmed` | boolean | Whether visit was confirmed (null if pending) |

---

#### PUT /hmis/client-visits/verification/{client_visit_verification_id}

Update verification result after call completion.

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `client_visit_verification_id` | integer | Verification ID from GET response |

**Request Body:**

```json
{
  "status": 1,
  "recordingUrl": "https://minio.example.com/recordings/2025-01-15/CA123.mp3",
  "isVisitConfirmed": true
}
```

**Request Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `status` | integer | Yes | New status code (1=verified, 2=failed) |
| `recordingUrl` | string | No | URL to call recording (presigned URL) |
| `isVisitConfirmed` | boolean | No | Whether visit was confirmed by contact |

**Response (200 OK):**

Returns the updated verification object (same schema as GET response item).

**Error Responses:**

| Status | Description |
|--------|-------------|
| 400 | Invalid request body |
| 401 | Invalid or missing authentication |
| 403 | Verification cannot be changed (`canBeChanged: false`) |
| 404 | Verification not found |
| 500 | Internal server error |

---

## Architecture

### Component Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           ACME SUPERVISOR                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐    │
│  │ Nexus Router   │     │ Queue Admin      │     │ Queue Mgmt       │    │
│  │ /api/nexus/*   │     │ Router           │     │ Router           │    │
│  └────────┬─────────┘     └──────────────────┘     └────────┬─────────┘    │
│           │                                                  │              │
│           ▼                                                  ▼              │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                        Nexus Integration Module                     │  │
│  │  ┌─────────────┐  ┌─────────────────┐  ┌────────────────────────┐   │  │
│  │  │ Client      │  │ Sync Service    │  │ Models                  │   │  │
│  │  │ - fetch()   │  │ - pull from     │  │ - NexusVerification   │   │  │
│  │  │ - update()  │  │   Nexus       │  │ - NexusEventInfo      │   │  │
│  │  │             │  │ - push results  │  │ - PaginatedResponse     │   │  │
│  │  └─────────────┘  └─────────────────┘  └────────────────────────┘   │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│           │                                                                 │
│           ▼                                                                 │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                        Managed Queue System                           │  │
│  │  ┌─────────────┐  ┌─────────────────┐  ┌────────────────────────┐   │  │
│  │  │ QueueConfig │  │ CallEntry       │  │ QueueScheduler         │   │  │
│  │  │ (MongoDB)   │  │ (MongoDB)       │  │ (Celery Beat)          │   │  │
│  │  └─────────────┘  └─────────────────┘  └────────────────────────┘   │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│           │                                                                 │
│           ▼                                                                 │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                        Twilio / Voice Agent                           │  │
│  │  - Outbound calls via Twilio                                          │  │
│  │  - Voice conversation via Pipecat + OpenAI                            │  │
│  │  - Recording to MinIO/S3                                              │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                    │                              ▲
                    │ Pull verifications           │ Push results
                    ▼                              │
┌─────────────────────────────────────────────────────────────────────────────┐
│                           NEXUS HMIS                                       │
│  ┌─────────────┐  ┌─────────────────┐  ┌────────────────────────────────┐  │
│  │ Staging     │  │ Haiti           │  │ Honduras                        │  │
│  │ Environment │  │ Environment     │  │ Environment                     │  │
│  └─────────────┘  └─────────────────┘  └────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Module Structure

```
backend/app/integrations/nexus/
├── __init__.py           # Module exports
├── models.py             # Pydantic models for API responses
├── client.py             # NexusClient HTTP client
└── sync_service.py       # Bidirectional sync logic

backend/app/services/queue/
├── nexus_tasks.py      # Celery tasks for sync

backend/app/routers/
├── nexus_router.py     # REST API endpoints
```

---

## Queue Configuration

### Creating a Nexus Queue

Each Nexus environment requires a dedicated queue with:

```python
{
    # Queue identification
    "queue_id": "nexus_honduras_abc123",
    "name": "Honduras Vaccination Verifications",
    "domain": "vaccination",

    # Nexus API configuration (stored in metadata)
    "metadata": {
        "queue_type": "nexus",
        "nexus_api_url": "https://nexus.hnd.acme.org/api/v1",
        "nexus_api_key": "bearer-token-here",
        "nexus_environment": "honduras",

        # Sync settings
        "sync_interval_seconds": 300,  # 5 minutes
        "date_from": "2025-01-01",     # Optional fixed start date
        "date_to": null,               # null = use today's date
        "default_language": "es",

        # Storage settings
        "storage_prefix": "honduras",  # Optional custom prefix

        # Tracking (auto-updated by system)
        "last_sync_at": "2025-01-15T10:30:00Z",
        "last_sync_status": "success",
        "last_sync_error": null,
        "total_synced_items": 150
    },

    # Queue operation settings
    "time_window": {
        "start_time_utc": "14:00",
        "end_time_utc": "22:00",
        "days_of_week": [0, 1, 2, 3, 4]  # Mon-Fri
    },
    "max_concurrent_calls": 5,
    "retry_strategy": {
        "max_retries": 3,
        "no_answer_delay": 1800,  # 30 min
        "busy_delay": 1800
    },

    "state": "active"
}
```

### Queue Metadata Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `queue_type` | string | Yes | Must be "nexus" |
| `nexus_api_url` | string | Yes | Base URL for Nexus API |
| `nexus_api_key` | string | Yes | Bearer token for authentication |
| `nexus_environment` | string | Yes | Environment name (staging/haiti/honduras) |
| `sync_interval_seconds` | integer | No | Sync frequency (default: 300) |
| `date_from` | string | No | Fixed start date filter (YYYY-MM-DD) |
| `date_to` | string | No | End date filter (null = today) |
| `default_language` | string | No | Language for calls (default: "en") |
| `storage_prefix` | string | No | Custom S3 prefix (default: queue_id) |

---

## Data Flow

### 1. Sync from Nexus (Pull)

```
Celery Beat (every 5 min)
    │
    ▼
sync_nexus_queues task
    │
    ├─► For each ACTIVE queue with queue_type="nexus":
    │       │
    │       ▼
    │   NexusClient.fetch_pending_verifications()
    │       │
    │       ├─► GET /hmis/client-visits/verification
    │       │   (with date filters from queue metadata)
    │       │
    │       ▼
    │   For each verification:
    │       │
    │       ├─► Check if entry exists (by nexus_verification_id)
    │       │   └─► Skip if already processed
    │       │
    │       ├─► Create CallEntry with:
    │       │   - phone_number = verification.contactPhones[0]
    │       │   - call_data = patient info for voice prompt
    │       │   - metadata.source = "nexus"
    │       │   - metadata.nexus_verification_id = verification.id
    │       │   - status = PENDING
    │       │
    │       └─► Add state history entry
    │
    └─► Update queue metadata with sync status
```

### 2. Call Processing

```
process_managed_queues task (every 30 sec)
    │
    ▼
For each ACTIVE queue:
    │
    ├─► Check time window (auto-pause/resume)
    │
    ├─► Get PENDING entries (limit: max_concurrent_calls - active)
    │
    └─► For each entry:
            │
            ▼
        Update status: PENDING → CALLING
            │
            ▼
        POST /api/vaccination/start-call
            │
            ▼
        Twilio initiates outbound call
            │
            ▼
        Voice agent conducts conversation
            │
            ▼
        Call completes → status_callback
```

### 3. Sync to Nexus (Push)

```
status_callback receives Twilio webhook
    │
    ▼
Update CallEntry status:
    - SUCCESS (if completed + duration >= 30s)
    - FAILED/RETRY_SCHEDULED/DEAD_LETTER (otherwise)
    │
    ▼
Check if entry.metadata.source == "nexus"
    │
    ├─► Yes: Trigger sync_nexus_result task
    │           │
    │           ▼
    │       NexusClient.update_verification()
    │           │
    │           ├─► PUT /hmis/client-visits/verification/{id}
    │           │   {
    │           │     "status": 1 or 2,
    │           │     "recordingUrl": "https://...",
    │           │     "isVisitConfirmed": true/false
    │           │   }
    │           │
    │           └─► Update entry.metadata.sync_status
    │
    └─► No: Skip (manual queue entry)
```

---

## API Reference

### Nexus Router Endpoints

#### POST /api/nexus/queues

Create a new Nexus-synced queue.

**Request:**
```json
{
  "name": "Honduras Vaccination Verifications",
  "nexus_api_url": "https://nexus.hnd.acme.org/api/v1",
  "nexus_api_key": "secret-bearer-token",
  "nexus_environment": "honduras",
  "sync_interval_seconds": 300,
  "date_from": "2025-01-01",
  "date_to": null,
  "default_language": "es",
  "time_window": {
    "start_time_utc": "14:00",
    "end_time_utc": "22:00",
    "days_of_week": [0, 1, 2, 3, 4]
  },
  "max_concurrent_calls": 5,
  "start_immediately": true
}
```

**Response (201):**
```json
{
  "queue_id": "nexus_honduras_abc123",
  "name": "Honduras Vaccination Verifications",
  "state": "active",
  "nexus_environment": "honduras",
  "total_synced_items": 0,
  "last_sync_at": null,
  "last_sync_status": null,
  "message": "Nexus queue created for honduras. Sync will begin automatically."
}
```

---

#### GET /api/nexus/queues

List all Nexus-synced queues.

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `environment` | string | Filter by Nexus environment |

**Response (200):**
```json
[
  {
    "queue_id": "nexus_honduras_abc123",
    "name": "Honduras Vaccination Verifications",
    "state": "active",
    "nexus_environment": "honduras",
    "total_synced_items": 150,
    "last_sync_at": "2025-01-15T10:30:00Z",
    "last_sync_status": "success",
    "message": ""
  }
]
```

---

#### POST /api/nexus/queues/{queue_id}/sync

Manually trigger a sync for a Nexus queue.

**Response (200):**
```json
{
  "success": true,
  "queue_id": "nexus_honduras_abc123",
  "created": 25,
  "updated": 0,
  "skipped": 125,
  "errors": 0,
  "message": "Sync complete: 25 new entries created"
}
```

---

#### GET /api/nexus/queues/{queue_id}/sync-status

Get sync status for a Nexus queue.

**Response (200):**
```json
{
  "queue_id": "nexus_honduras_abc123",
  "nexus_environment": "honduras",
  "last_sync_at": "2025-01-15T10:30:00Z",
  "last_sync_status": "success",
  "last_sync_error": null,
  "total_synced_items": 150,
  "sync_interval_seconds": 300
}
```

---

## Error Handling

### Sync Error Recovery

| Error | Handling |
|-------|----------|
| Network timeout | Retry with exponential backoff (max 3 retries) |
| 401 Unauthorized | Log error, mark sync as failed, alert |
| 429 Rate Limited | Back off and retry after delay |
| 500 Server Error | Retry with backoff |
| Duplicate entry | Skip (already synced) |

### Result Sync Error Recovery

| Error | Handling |
|-------|----------|
| 403 Cannot change | Log warning, mark as synced_failed |
| 404 Not found | Log error, mark as synced_failed |
| Network error | Retry (max 5 retries with backoff) |

---

## Deployment

### Environment Variables

No new environment variables required. Nexus credentials are stored per-queue in MongoDB.

### Celery Beat Schedule

The sync task runs every 5 minutes (configurable per-queue):

```python
beat_schedule = {
    "sync-nexus-queues": {
        "task": "sync_nexus_queues",
        "schedule": 300,  # 5 minutes
    },
}
```

### Recording Storage

Recordings are stored with queue-specific prefixes:

```
s3://bucket/nexus_honduras_abc123/recordings/2025-01-15/CA123.mp3
s3://bucket/nexus_haiti_xyz789/recordings/2025-01-15/CA456.mp3
```

### Monitoring

Monitor these metrics:
- `nexus_sync_duration_seconds` - Time to complete sync
- `nexus_sync_items_created` - New entries per sync
- `nexus_sync_errors` - Errors per sync
- `nexus_result_sync_success` - Successful result pushes
- `nexus_result_sync_failures` - Failed result pushes
