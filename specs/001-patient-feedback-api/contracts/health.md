# API Contract: Health & Metrics

**Base Path**: `/api/v1/health`, `/api/v1/metrics`
**Purpose**: System health checks and operational metrics

---

## GET `/api/v1/health`

**Description**: Basic health check - confirm server is running

**Authentication**: None (public endpoint)

**Success Response** (200 OK):
```json
{
  "status": "healthy",
  "timestamp": "2026-01-18T14:30:00Z",
  "version": "1.0.0"
}
```

**Response Schema**:
```python
class HealthResponse(BaseModel):
    status: str = "healthy"
    timestamp: datetime
    version: str
```

**Error Response** (503 Service Unavailable):
```json
{
  "status": "unhealthy",
  "timestamp": "2026-01-18T14:30:00Z",
  "errors": ["MongoDB connection failed", "Redis connection timeout"]
}
```

---

## GET `/api/v1/health/ready`

**Description**: Readiness check - verify all dependencies are healthy

**Authentication**: None (public endpoint)

**Purpose**: Used by Kubernetes/Docker for readiness probes

**Success Response** (200 OK):
```json
{
  "status": "ready",
  "timestamp": "2026-01-18T14:30:00Z",
  "checks": {
    "mongodb": {
      "status": "healthy",
      "latency_ms": 12
    },
    "redis": {
      "status": "healthy",
      "latency_ms": 3
    },
    "twilio": {
      "status": "healthy",
      "latency_ms": 45
    }
  }
}
```

**Response Schema**:
```python
class DependencyCheck(BaseModel):
    status: str  # "healthy" | "degraded" | "unhealthy"
    latency_ms: int

class ReadinessResponse(BaseModel):
    status: str  # "ready" | "not_ready"
    timestamp: datetime
    checks: Dict[str, DependencyCheck]
```

**Error Response** (503 Service Unavailable):
```json
{
  "status": "not_ready",
  "timestamp": "2026-01-18T14:30:00Z",
  "checks": {
    "mongodb": {
      "status": "unhealthy",
      "error": "Connection timeout after 5s"
    },
    "redis": {
      "status": "healthy",
      "latency_ms": 2
    }
  }
}
```

**Cache Behavior**:
- Results cached for 5 seconds (configurable via `HEALTH_CHECK_CACHE_TTL`)
- Avoids hammering dependencies with frequent health checks

---

## GET `/api/v1/health/live`

**Description**: Liveness check - simple HTTP 200 response

**Authentication**: None (public endpoint)

**Purpose**: Used by Kubernetes/Docker for liveness probes (restart on failure)

**Success Response** (200 OK):
```json
{
  "status": "alive"
}
```

**Response Schema**:
```python
class LivenessResponse(BaseModel):
    status: str = "alive"
```

---

## GET `/api/v1/metrics`

**Description**: Application health and call statistics in custom JSON format

**Authentication**: Required (both Admin and User roles)

**Success Response** (200 OK):
```json
{
  "timestamp": "2026-01-18T14:30:00Z",
  "uptime_seconds": 3600,
  "system": {
    "cpu_usage_percent": 45.2,
    "memory_usage_mb": 512,
    "memory_limit_mb": 2048
  },
  "calls": {
    "active_calls_count": 3,
    "queued_calls_count": 47,
    "total_calls_today": 152,
    "success_rate_percent": 94.7,
    "average_duration_seconds": 180
  },
  "campaigns": {
    "active_campaigns": 5,
    "paused_campaigns": 2,
    "total_campaigns": 12
  },
  "queue": {
    "pending_entries": 47,
    "retrying_entries": 8,
    "dlq_count": 3
  }
}
```

**Response Schema**:
```python
class SystemMetrics(BaseModel):
    cpu_usage_percent: float
    memory_usage_mb: int
    memory_limit_mb: int

class CallMetrics(BaseModel):
    active_calls_count: int
    queued_calls_count: int
    total_calls_today: int
    success_rate_percent: float
    average_duration_seconds: int

class CampaignMetrics(BaseModel):
    active_campaigns: int
    paused_campaigns: int
    total_campaigns: int

class QueueMetrics(BaseModel):
    pending_entries: int
    retrying_entries: int
    dlq_count: int

class MetricsResponse(BaseModel):
    timestamp: datetime
    uptime_seconds: int
    system: SystemMetrics
    calls: CallMetrics
    campaigns: CampaignMetrics
    queue: QueueMetrics
```

**Error Response** (401 Unauthorized):
```json
{
  "detail": "Could not validate credentials"
}
```

---

## GET `/api/v1/metrics/prometheus`

**Description**: Prometheus-compatible metrics export

**Authentication**: None (public endpoint, but can be restricted via network policy)

**Success Response** (200 OK):
```
# HELP call_queue_depth Number of calls in queue by state
# TYPE call_queue_depth gauge
call_queue_depth{state="pending"} 47
call_queue_depth{state="retrying"} 8
call_queue_depth{state="calling"} 3

# HELP call_queue_dlq_count Number of calls in Dead Letter Queue
# TYPE call_queue_dlq_count counter
call_queue_dlq_count{queue="patient-feedback"} 3

# HELP call_retries_exhausted_total Total calls that exhausted retries
# TYPE call_retries_exhausted_total counter
call_retries_exhausted_total 3

# HELP active_calls Current number of active voice calls
# TYPE active_calls gauge
active_calls 3

# HELP call_duration_seconds Call duration in seconds
# TYPE call_duration_seconds histogram
call_duration_seconds_bucket{le="30"} 5
call_duration_seconds_bucket{le="60"} 12
call_duration_seconds_bucket{le="120"} 45
call_duration_seconds_bucket{le="300"} 98
call_duration_seconds_bucket{le="+Inf"} 152
call_duration_seconds_sum 27360
call_duration_seconds_count 152

# HELP campaign_processing_rate Campaigns processed per minute
# TYPE campaign_processing_rate gauge
campaign_processing_rate 2.5
```

**Content-Type**: `text/plain; version=0.0.4`

**Metrics Exposed**:
- `call_queue_depth{state}` - Queue entries by state
- `call_queue_dlq_count{queue}` - DLQ count
- `call_retries_exhausted_total` - Retry exhaustion counter
- `active_calls` - Current active calls
- `call_duration_seconds` - Histogram of call durations
- `campaign_processing_rate` - Campaigns per minute

---

## Configuration

### Health Check Settings
```env
HEALTH_CHECK_DEPENDENCIES=true         # Enable dependency checks
HEALTH_CHECK_CACHE_TTL=5               # Cache results for 5 seconds
```

### Metrics Settings
```env
ENABLE_PROMETHEUS_METRICS=true         # Enable /metrics/prometheus endpoint
METRICS_UPDATE_INTERVAL=15             # Update metrics every 15 seconds
```

---

## Performance Requirements

- `/api/v1/health` - Must respond < 500ms (SC-001)
- `/api/v1/metrics` - Must respond < 1s (SC-022)
- Prometheus metrics update at least every 15 seconds (SC-024)
