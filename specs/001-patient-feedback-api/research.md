# Technology Research & Decisions

**Feature**: Patient Feedback Collection API
**Date**: 2026-01-17
**Purpose**: Document technology choices, rationale, and configuration options

---

## Design Principle: Secure Defaults with Escape Hatches

**Philosophy**: Production-ready defaults with configurable overrides for infrastructure flexibility.

Every security/operational constraint includes:
- ✅ **Default**: Secure, production-ready behavior (enabled by default)
- 🔧 **Override**: Environment variable to disable/bypass (documented with warnings)
- 📋 **Rationale**: Why the default exists and when to override

---

## 1. Container Architecture

### Decision: One Process Per Container (No Supervisord)

**Default Behavior**:
- Three separate container types: API, Celery Worker, Celery Beat
- Each container runs single process
- Orchestrated via Docker Compose / CapRover multi-app deployment

**Configuration Override**:
```env
# NOT RECOMMENDED: Emergency fallback only
ENABLE_SUPERVISOR_MODE=false  # Default: false (supervisord disabled)

# If true: Runs API + Worker + Beat in single container (like reference repo)
# Use only for: Local dev, resource-constrained environments, proof-of-concept
# Warning: Violates Docker best practices, harder to scale
```

**Rationale**:
- **Why separate**: Independent scaling (scale workers ≠ scale API), cleaner logs, better resource limits
- **When to override**: Local laptop with limited RAM, demo environments, legacy infrastructure requiring single container
- **Reference issue**: Reference repo's "all" mode makes it impossible to scale workers independently

**Alternatives Considered**:
- Supervisord mode (reference repo approach) - Rejected: scaling/logging complexity
- Kubernetes Jobs (for workers) - Deferred: too complex for CapRover deployment
- Single-threaded API with no workers - Rejected: doesn't support bulk campaigns

---

## 2. Resource Limits

### Decision: Default Resource Constraints with Override

**Default Behavior**:
```yaml
# docker-compose.yml
api:
  deploy:
    resources:
      limits:
        cpus: '2.0'
        memory: 2G
      reservations:
        cpus: '0.5'
        memory: 512M

celery-worker:
  deploy:
    resources:
      limits:
        cpus: '1.0'
        memory: 1G
      reservations:
        cpus: '0.25'
        memory: 256M
```

**Configuration Override**:
```env
# Disable resource limits (useful for local dev with unlimited resources)
DOCKER_RESOURCE_LIMITS_ENABLED=true  # Default: true

# Or customize per-service (CapRover allows per-app config):
API_CPU_LIMIT=2.0
API_MEMORY_LIMIT=2G
WORKER_CPU_LIMIT=1.0
WORKER_MEMORY_LIMIT=1G
```

**Rationale**:
- **Why limits**: Prevent single service consuming all host resources (reference repo issue)
- **When to override**: Development on powerful machines, custom infrastructure with external monitoring
- **Production**: Always enabled on shared infrastructure (CapRover)

---

## 3. Secrets Management

### Decision: Docker Secrets with Fallback to Environment Variables

**Default Behavior**:
- Sensitive data (API keys, passwords) loaded from Docker secrets
- Secrets mounted at `/run/secrets/<secret_name>`
- Pydantic Settings reads secrets first, falls back to env vars

**Configuration Override**:
```env
# Force environment variable mode (bypasses Docker secrets)
USE_DOCKER_SECRETS=true  # Default: true

# If false: Falls back to plain environment variables
# Warning: Secrets visible in `docker inspect`, process list, logs
# Use only for: Local dev, CI/CD where secrets injected via platform
```

**Implementation**:
```python
# config.py
class Settings(BaseSettings):
    openai_api_key: str = Field(...)

    @validator('openai_api_key', pre=True)
    def load_from_secret(cls, v, values):
        if os.getenv('USE_DOCKER_SECRETS', 'true').lower() == 'true':
            secret_path = '/run/secrets/openai_api_key'
            if os.path.exists(secret_path):
                return open(secret_path).read().strip()
        return v  # Fallback to env var
```

**Rationale**:
- **Why secrets**: Prevent credential leakage in logs, process listings (reference repo issue)
- **When to override**: Local dev (no secrets infra), CI/CD with native secrets injection
- **Production**: Always use Docker secrets or CapRover secrets

**Alternatives Considered**:
- HashiCorp Vault integration - Deferred: too complex for initial deployment
- AWS Secrets Manager - Deferred: vendor lock-in
- Encrypted .env files - Rejected: key distribution problem

---

## 4. Startup Configuration Validation

### Decision: Fail-Fast with Optional Bypass

**Default Behavior**:
- On startup, validate all required configs (MongoDB URI, Redis URL, API keys)
- If validation fails → exit with descriptive error (don't start server)
- Health check fails until validation passes

**Configuration Override**:
```env
# Skip startup validation (dangerous!)
SKIP_STARTUP_VALIDATION=false  # Default: false

# If true: Starts server even with invalid config
# Warning: May fail on first request instead of startup
# Use only for: Testing failure scenarios, gradual config migration
```

**Implementation**:
```python
# main.py
@asynccontextmanager
async def lifespan(app: FastAPI):
    if not settings.SKIP_STARTUP_VALIDATION:
        validate_required_configs()  # Raises exception if invalid
        await validate_dependencies()  # Check MongoDB, Redis connectivity
    yield
    # Shutdown logic
```

**Rationale**:
- **Why validate**: Fail immediately instead of serving traffic with broken config (reference repo issue)
- **When to override**: Testing edge cases, phased config rollout
- **Production**: Always enabled (catch config errors before user impact)

---

## 5. Health Check Strategy

### Decision: Readiness vs Liveness with Caching

**Default Behavior**:
- `/health/live` - Simple HTTP 200 (process alive)
- `/health/ready` - Check all dependencies (MongoDB, Redis, Twilio)
- `/health/startup` - One-time initialization check
- Results cached for 5s to avoid hammering dependencies

**Configuration Override**:
```env
# Disable dependency checks in health endpoints
HEALTH_CHECK_DEPENDENCIES=true  # Default: true

# If false: /health/ready returns 200 without checking MongoDB/Redis
# Use only for: Testing, environments where dependencies always available

# Adjust caching
HEALTH_CHECK_CACHE_TTL=5  # Default: 5 seconds
# Set to 0 to disable caching (not recommended - hammers dependencies)
```

**Implementation**:
```python
# api/v1/health.py
@router.get("/ready")
async def readiness():
    if not settings.HEALTH_CHECK_DEPENDENCIES:
        return {"status": "ready"}  # Fast path

    # Check dependencies with caching
    cached = cache.get("health_ready", ttl=settings.HEALTH_CHECK_CACHE_TTL)
    if cached:
        return cached

    checks = {
        "mongodb": await check_mongodb(),
        "redis": await check_redis(),
        "twilio": await check_twilio(),
    }
    result = {"status": "ready" if all(checks.values()) else "unhealthy", "checks": checks}
    cache.set("health_ready", result)
    return result
```

**Rationale**:
- **Why separate endpoints**: Kubernetes/Docker distinguish liveness (restart) vs readiness (route traffic)
- **Why caching**: Avoid checking MongoDB every 15s (reference repo hammered dependencies)
- **When to override**: Testing failure scenarios, environments with unreliable health check network

---

## 6. Database Backup Strategy

### Decision: Automated Backups with Optional Disable

**Default Behavior**:
- Automated MongoDB backups via sidecar container (tiredofit/mongodb-backup)
- Daily backups at 2 AM UTC, retained for 7 days
- Backups stored in volume mount `/backups`

**Configuration Override**:
```env
# Disable automated backups
ENABLE_AUTOMATED_BACKUPS=true  # Default: true

# If false: No backup container deployed
# Use only for: Ephemeral dev environments, managed MongoDB (Atlas)

# Customize backup schedule
BACKUP_INTERVAL=86400  # Default: daily (86400 seconds)
BACKUP_RETENTION_DAYS=7  # Default: 7 days
```

**Docker Compose**:
```yaml
mongodb-backup:
  image: tiredofit/mongodb-backup
  depends_on:
    - mongodb
  volumes:
    - ./backups:/backups
  environment:
    DB_HOST: mongodb
    DB_NAME: voice_ai
    DB_BACKUP_INTERVAL: ${BACKUP_INTERVAL:-86400}
    DB_CLEANUP_TIME: ${BACKUP_RETENTION_DAYS:-7}
  profiles:
    - backups  # Only start if ENABLE_AUTOMATED_BACKUPS=true
```

**Rationale**:
- **Why backups**: Reference repo had no backup strategy (data loss risk)
- **When to disable**: Managed MongoDB (MongoDB Atlas), ephemeral dev/test
- **Production**: Always enabled for self-hosted MongoDB

---

## 7. Dead Letter Queue Monitoring

### Decision: Prometheus Metrics with Optional Disable

**Default Behavior**:
- Expose Prometheus metrics at `/metrics`
- DLQ metrics: `call_queue_dlq_count{queue="patient-feedback"}`, `call_retries_exhausted_total`
- Alert rules included in `prometheus-alerts.yml`

**Configuration Override**:
```env
# Disable Prometheus metrics
ENABLE_PROMETHEUS_METRICS=true  # Default: true

# If false: /metrics endpoint returns 404
# Use only for: Privacy-sensitive environments, legacy monitoring

# Disable DLQ alerts
ENABLE_DLQ_ALERTS=true  # Default: true
```

**Rationale**:
- **Why metrics**: Reference repo collected metrics but had no alerting
- **When to disable**: Environments with alternative monitoring (Datadog, New Relic)
- **Production**: Enabled for visibility into queue health

---

## 8. Graceful Shutdown

### Decision: Signal Handling with Configurable Timeout

**Default Behavior**:
- On SIGTERM: Stop accepting new requests → drain active connections → close DB pools → exit
- Shutdown timeout: 30 seconds (configurable)
- Celery workers finish current task before shutdown

**Configuration Override**:
```env
# Shutdown timeout
GRACEFUL_SHUTDOWN_TIMEOUT=30  # Default: 30 seconds

# Set to 0 for immediate shutdown (not recommended)
# Set higher for long-running voice calls (max call duration = 10 min)

# For Celery workers
CELERY_WORKER_SHUTDOWN_TIMEOUT=600  # Default: 10 minutes (max call duration)
```

**Implementation**:
```python
# main.py
import signal

async def graceful_shutdown():
    logger.info("SIGTERM received, starting graceful shutdown")
    # Stop accepting new requests
    server.should_exit = True
    # Wait for active connections
    await asyncio.sleep(settings.GRACEFUL_SHUTDOWN_TIMEOUT)
    # Close resources
    await mongodb.close()
    await redis.close()

signal.signal(signal.SIGTERM, lambda s, f: asyncio.create_task(graceful_shutdown()))
```

**Rationale**:
- **Why graceful**: Prevent cutting off active voice calls mid-conversation
- **When to adjust**: Voice calls may exceed 30s (extend timeout), or testing rapid restarts
- **Production**: Set timeout >= max expected call duration

---

## 9. Enhanced CapRover Deployment

### Decision: Rolling Updates with Pre-Deploy Hooks

**Default Behavior**:
- Rolling updates (zero-downtime deployments)
- Pre-deploy hook runs database migrations
- Health check validation before routing traffic

**Configuration Override**:
```env
# Disable rolling updates (faster deploy, brief downtime)
ENABLE_ROLLING_UPDATES=true  # Default: true

# If false: Stop all containers → deploy new → start (brief downtime)
# Use only for: Non-production, maintenance windows

# Skip pre-deploy hooks
SKIP_PREDEPLOY_HOOKS=false  # Default: false
```

**Captain Definition**:
```json
{
  "schemaVersion": 2,
  "dockerfilePath": "./docker/Dockerfile.api",
  "deployStrategy": "${DEPLOY_STRATEGY:-rolling-update}",
  "healthCheckPath": "/health/ready",
  "containerHttpPort": 3000,
  "instanceCount": 2,
  "preDeployFunction": {
    "command": "python -m backend.scripts.migrate_db",
    "enabled": "${SKIP_PREDEPLOY_HOOKS:-false}" === "false"
  }
}
```

**Rationale**:
- **Why rolling**: Zero-downtime deployments (reference repo had no strategy)
- **When to disable**: Non-critical environments, testing deployment speed
- **Production**: Always enabled

---

## 10. Structured Logging with Correlation IDs

### Decision: Structured JSON Logs with Optional Plain Text

**Default Behavior**:
- All logs in JSON format: `{"timestamp": "...", "level": "info", "call_sid": "CA123", "message": "..."}`
- Correlation ID (call_sid, campaign_id) in every log entry
- Human-readable format optional for local dev

**Configuration Override**:
```env
# Log format
LOG_FORMAT=json  # Options: json, text
# Default: json (production), text (local dev if LOG_LEVEL=debug)

# Disable correlation IDs
ENABLE_CORRELATION_IDS=true  # Default: true

# If false: Logs don't include call_sid/campaign_id tracking
# Use only for: Simple debugging, privacy requirements
```

**Implementation**:
```python
# core/logging.py
import structlog

def setup_logging():
    if settings.LOG_FORMAT == "json":
        processors = [
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer()
        ]
    else:
        processors = [
            structlog.dev.ConsoleRenderer()
        ]

    structlog.configure(processors=processors)
```

**Rationale**:
- **Why JSON**: Machine-parseable for log aggregation (ELK, Loki)
- **Why correlation IDs**: Trace requests across services (reference repo missing)
- **When to override**: Local dev (human-readable), legacy log systems

---

## 11. Network Segmentation

### Decision: Multi-Network Architecture with Override

**Default Behavior**:
- Three Docker networks: `public`, `private`, `data`
  - Public: API container only
  - Private: API ↔ Celery workers
  - Data: All ↔ MongoDB/Redis (isolated from public)

**Configuration Override**:
```env
# Disable network segmentation (all on default bridge)
ENABLE_NETWORK_SEGMENTATION=true  # Default: true

# If false: Single network (simpler but less secure)
# Use only for: Local dev, Docker Desktop limitations
```

**Docker Compose**:
```yaml
networks:
  public:
    driver: bridge
  private:
    driver: bridge
    internal: true  # No internet access
  data:
    driver: bridge
    internal: true

services:
  api:
    networks:
      - public    # Internet-facing
      - private   # Workers communication
      - data      # Database access

  celery-worker:
    networks:
      - private   # API communication
      - data      # Database access

  mongodb:
    networks:
      - data      # Isolated from public
```

**Rationale**:
- **Why segment**: Limit blast radius if API compromised (can't directly access MongoDB)
- **When to disable**: Simple local dev, networking limitations
- **Production**: Always enabled for defense-in-depth

---

## Summary: Configuration Matrix

| Feature | Default | Override Env Var | When to Override |
|---------|---------|------------------|------------------|
| **Container Mode** | Separate (API/Worker/Beat) | `ENABLE_SUPERVISOR_MODE=true` | Local dev, resource-constrained |
| **Resource Limits** | Enabled (2GB API, 1GB Worker) | `DOCKER_RESOURCE_LIMITS_ENABLED=false` | Unlimited dev environment |
| **Secrets** | Docker secrets | `USE_DOCKER_SECRETS=false` | CI/CD with platform secrets |
| **Startup Validation** | Fail-fast | `SKIP_STARTUP_VALIDATION=true` | Testing edge cases |
| **Health Check Deps** | Check MongoDB/Redis | `HEALTH_CHECK_DEPENDENCIES=false` | Testing, managed infra |
| **Backups** | Automated daily | `ENABLE_AUTOMATED_BACKUPS=false` | Managed MongoDB (Atlas) |
| **DLQ Monitoring** | Prometheus metrics | `ENABLE_PROMETHEUS_METRICS=false` | Alternative monitoring |
| **Graceful Shutdown** | 30s timeout | `GRACEFUL_SHUTDOWN_TIMEOUT=0` | Immediate shutdown needed |
| **Rolling Updates** | Enabled | `ENABLE_ROLLING_UPDATES=false` | Non-production, testing |
| **Structured Logs** | JSON format | `LOG_FORMAT=text` | Local dev, human-readable |
| **Network Segmentation** | 3 networks | `ENABLE_NETWORK_SEGMENTATION=false` | Simple local dev |

**Guideline**: Production should use all defaults. Override only when infrastructure requires it and document the reason.

---

## Next: Phase 1 - Data Models & Contracts

All decisions documented. Proceeding to data model design and API contract generation.
