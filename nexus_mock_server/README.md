# Client Visit Verification Mock Server

A standalone FastAPI mock server that mimics Nexus's client visit verification API endpoints for development and testing purposes.

## Setup

```bash
cd mock_server
pip install -r requirements.txt
```

## Running the Server

```bash
uvicorn main:app --reload --port 8001
```

Or run directly:

```bash
python main.py
```

The server will start at `http://localhost:8001`

## Authentication

All endpoints require API key authentication via the `X-API-Key` header.

| Header | Value |
|--------|-------|
| `X-API-Key` | `mock-api-key-12345` |

## Endpoints

### GET `/api/v1/hmis/client-visits/verification`

Get paginated list of client visits available for verification.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `page` | int | 1 | Page number (min: 1) |
| `pageSize` | int | 50 | Items per page (min: 1) |
| `dateFrom` | date | null | Filter visits from this date (YYYY-MM-DD) |
| `dateTo` | date | null | Filter visits to this date (YYYY-MM-DD) |

**Example Request:**

```bash
curl -H "X-API-Key: mock-api-key-12345" \
  "http://localhost:8001/api/v1/hmis/client-visits/verification?page=1&pageSize=10"
```

**Example Response:**

```json
{
  "items": [
    {
      "id": 1,
      "status": 1,
      "canBeChanged": true,
      "contactClientSptId": "SPT-10001",
      "contactName": "John Doe",
      "contactGender": "Male",
      "contactPhone": "+255712345678",
      "contactPhones": ["+255712345678", "+255723456789"],
      "contactPhoneOwnerName": "John Doe",
      "eventInfo": {
        "eventDate": "2024-01-15",
        "eventFacility": "Muhimbili National Hospital",
        "eventType": "Vaccination Visit",
        "attributes": [
          {"name": "Weight", "value": "68 kg"}
        ],
        "vaccineDoses": [
          {"name": "BCG", "doseNumber": 1}
        ],
        "sptDocumentIds": [
          {"id": 101, "documentNumber": "DOC-2024-001"}
        ]
      },
      "recordingUrl": null,
      "isVisitConfirmed": null
    }
  ],
  "total": 5,
  "page": 1,
  "pageSize": 10,
  "pages": 1,
  "hasNext": false,
  "hasPrevious": false
}
```

---

### PUT `/api/v1/hmis/client-visits/verification/{client_visit_verification_id}`

Update a client visit verification record.

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `client_visit_verification_id` | int | ID of the verification record |

**Request Body:**

| Field | Type | Description |
|-------|------|-------------|
| `status` | int | Verification status (see below) |
| `recordingUrl` | string | URL to audio recording |
| `isVisitConfirmed` | boolean | Whether visit is confirmed |

**Verification Status Values:**

| Value | Name | Can Update |
|-------|------|------------|
| 999 | UNKNOWN | Yes |
| 1 | IN_PROGRESS | Yes |
| 2 | VALID | No |
| 3 | NOT_VALID | No |
| 4 | NOT_REACHABLE | No |

**Example Request:**

```bash
curl -X PUT \
  -H "X-API-Key: mock-api-key-12345" \
  -H "Content-Type: application/json" \
  -d '{"status": 2, "recordingUrl": "https://example.com/recording.mp3", "isVisitConfirmed": true}' \
  "http://localhost:8001/api/v1/hmis/client-visits/verification/1"
```

**Example Response:**

```json
{
  "id": 1,
  "status": 2,
  "canBeChanged": false,
  "contactClientSptId": "SPT-10001",
  "contactName": "John Doe",
  "contactGender": "Male",
  "contactPhone": "+255712345678",
  "contactPhones": ["+255712345678", "+255723456789"],
  "contactPhoneOwnerName": "John Doe",
  "eventInfo": {
    "eventDate": "2024-01-15",
    "eventFacility": "Muhimbili National Hospital",
    "eventType": "Vaccination Visit",
    "attributes": [
      {"name": "Weight", "value": "68 kg"}
    ],
    "vaccineDoses": [
      {"name": "BCG", "doseNumber": 1}
    ],
    "sptDocumentIds": [
      {"id": 101, "documentNumber": "DOC-2024-001"}
    ]
  },
  "recordingUrl": "https://example.com/recording.mp3",
  "isVisitConfirmed": true
}
```

---

### GET `/health`

Health check endpoint (no authentication required).

```bash
curl http://localhost:8001/health
```

## Data Files

| File | Description |
|------|-------------|
| `data/verifications.json` | Sample verification records (8 records pre-populated) |
| `data/updates.json` | Log of all PUT updates with timestamps |

## Interactive API Documentation

- Swagger UI: `http://localhost:8001/docs`
- ReDoc: `http://localhost:8001/redoc`

## Error Responses

**401 Unauthorized - Missing API Key:**
```json
{"detail": "Missing API key. Provide X-API-Key header."}
```

**401 Unauthorized - Invalid API Key:**
```json
{"detail": "Invalid API key"}
```

**404 Not Found - Record not found:**
```json
{"detail": "Verification record with ID 999 not found"}
```

**400 Bad Request - Cannot update status:**
```json
{"detail": "Verification record with status 2 cannot be updated"}
```
