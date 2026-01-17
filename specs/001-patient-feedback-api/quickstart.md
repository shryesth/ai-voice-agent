# Quickstart Guide: Patient Feedback Collection API

**Feature**: Patient Feedback Collection API
**Date**: 2026-01-18
**Purpose**: Developer setup instructions for local development, testing, and deployment

---

## Prerequisites

### Required Software
- **Python 3.11+** (check: `python --version`)
- **Docker & Docker Compose** (check: `docker --version`, `docker-compose --version`)
- **Git** (check: `git --version`)

### Required Accounts
- **Twilio Account** - For outbound calling ([sign up](https://www.twilio.com/try-twilio))
- **OpenAI Account** - For Realtime API access ([sign up](https://platform.openai.com/signup))
- **CapRover Server** (production only) - For deployment ([docs](https://caprover.com/docs/get-started.html))

---

## Local Development Setup

### 1. Clone Repository
```bash
git clone <repository-url>
cd ai-voice-agent-fastapi
git checkout 001-patient-feedback-api
```

### 2. Environment Configuration

Create `.env` file from template:
```bash
cp .env.example .env
```

**Edit `.env` with your credentials:**
```env
# MongoDB Configuration
MONGODB_URI=mongodb://localhost:27017
MONGODB_DATABASE=voice_ai

# Redis Configuration
REDIS_URL=redis://localhost:6379/0

# Twilio Credentials
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_PHONE_NUMBER=+12025551234

# OpenAI Configuration
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
OPENAI_MODEL=gpt-4o-realtime-preview-2024-12-17

# Security
JWT_SECRET_KEY=generate-a-secure-random-key-here
JWT_ALGORITHM=HS256
JWT_EXPIRATION_HOURS=24

# Application Settings
LOG_LEVEL=debug
LOG_FORMAT=text  # Use 'json' for production
ENVIRONMENT=development

# Feature Flags (Development Overrides)
SKIP_STARTUP_VALIDATION=false
HEALTH_CHECK_DEPENDENCIES=true
USE_DOCKER_SECRETS=false  # Use env vars for local dev
ENABLE_PROMETHEUS_METRICS=true
```

**Generate JWT Secret:**
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 3. Start Development Environment

**Using Docker Compose (Recommended):**
```bash
# Start all services (MongoDB, Redis, API, Celery Worker, Celery Beat)
docker-compose -f docker-compose.dev.yml up -d

# View logs
docker-compose -f docker-compose.dev.yml logs -f api

# Stop services
docker-compose -f docker-compose.dev.yml down
```

**Manual Setup (without Docker):**
```bash
# Install dependencies
pip install -r requirements.txt

# Start MongoDB (separate terminal)
mongod --dbpath ./data/mongodb

# Start Redis (separate terminal)
redis-server

# Start API server (separate terminal)
uvicorn backend.main:app --reload --host 0.0.0.0 --port 3000

# Start Celery worker (separate terminal)
celery -A backend.celery_app worker --loglevel=info

# Start Celery beat scheduler (separate terminal)
celery -A backend.celery_app beat --loglevel=info
```

### 4. Verify Installation

**Check health endpoint:**
```bash
curl http://localhost:3000/api/v1/health
```

Expected response:
```json
{
  "status": "healthy",
  "timestamp": "2026-01-18T14:30:00Z",
  "version": "1.0.0"
}
```

**Check readiness (with dependency validation):**
```bash
curl http://localhost:3000/api/v1/health/ready
```

Expected response:
```json
{
  "status": "ready",
  "checks": {
    "mongodb": {"status": "healthy", "latency_ms": 12},
    "redis": {"status": "healthy", "latency_ms": 3}
  }
}
```

### 5. Create Admin User

**Seed initial admin account:**
```bash
docker-compose -f docker-compose.dev.yml exec api python -m backend.scripts.create_admin \
  --email admin@example.com \
  --password secure_password_123
```

Or manually:
```bash
python -m backend.scripts.create_admin \
  --email admin@example.com \
  --password secure_password_123
```

### 6. Get Access Token

**Login:**
```bash
curl -X POST http://localhost:3000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@example.com",
    "password": "secure_password_123"
  }'
```

Response:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 86400,
  "user": {
    "email": "admin@example.com",
    "role": "admin"
  }
}
```

**Export token for subsequent requests:**
```bash
export TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

---

## Basic Workflow Example

### 1. Create Geography
```bash
curl -X POST http://localhost:3000/api/v1/geographies \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "North America - East Coast",
    "region_code": "US-EAST",
    "retention_policy": {
      "retention_days": 2555,
      "compliance_notes": "HIPAA 7-year retention"
    }
  }'
```

Save the returned `id` (e.g., `65a1b2c3d4e5f6g7h8i9j0k1`)

### 2. Create Campaign
```bash
export GEO_ID="65a1b2c3d4e5f6g7h8i9j0k1"

curl -X POST http://localhost:3000/api/v1/geographies/$GEO_ID/campaigns \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Campaign - January 2026",
    "config": {
      "max_concurrent_calls": 5,
      "time_windows": [
        {
          "start_time": "09:00:00",
          "end_time": "17:00:00",
          "days_of_week": ["monday", "tuesday", "wednesday", "thursday", "friday"]
        }
      ],
      "patient_list": ["+12025551234", "+12025555678"],
      "language_preference": "en"
    }
  }'
```

Save the returned `id` (e.g., `65b2c3d4e5f6g7h8i9j0k1l2`)

### 3. Initiate Test Call
```bash
export CAMPAIGN_ID="65b2c3d4e5f6g7h8i9j0k1l2"

curl -X POST http://localhost:3000/api/v1/campaigns/$CAMPAIGN_ID/calls/test \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "phone_number": "+12025551234",
    "language": "en"
  }'
```

Response:
```json
{
  "call_id": "65c3d4e5f6g7h8i9j0k1l2m3",
  "status": "queued",
  "message": "Test call queued"
}
```

### 4. Check Call Status
```bash
export CALL_ID="65c3d4e5f6g7h8i9j0k1l2m3"

curl http://localhost:3000/api/v1/calls/$CALL_ID \
  -H "Authorization: Bearer $TOKEN"
```

### 5. Start Campaign
```bash
curl -X POST http://localhost:3000/api/v1/campaigns/$CAMPAIGN_ID/start \
  -H "Authorization: Bearer $TOKEN"
```

Response:
```json
{
  "id": "65b2c3d4e5f6g7h8i9j0k1l2",
  "state": "active",
  "started_at": "2026-01-18T15:00:00Z",
  "message": "Campaign started. Queue entries created for 2 patients."
}
```

### 6. Monitor Campaign Status
```bash
curl http://localhost:3000/api/v1/campaigns/$CAMPAIGN_ID/status \
  -H "Authorization: Bearer $TOKEN"
```

---

## Running Tests

### Contract Tests (API Endpoints)
```bash
# Run all contract tests
pytest tests/contract/ -v

# Run specific test file
pytest tests/contract/test_auth.py -v

# Run with coverage
pytest tests/contract/ --cov=backend --cov-report=html
```

### Integration Tests (Voice Pipeline)
```bash
# Run integration tests (requires Twilio test credentials)
pytest tests/integration/ -v

# Skip slow tests
pytest tests/integration/ -v -m "not slow"
```

### Unit Tests
```bash
# Run all unit tests
pytest tests/unit/ -v

# Watch mode (re-run on file changes)
pytest-watch tests/unit/
```

### Full Test Suite
```bash
# Run everything
pytest -v

# Parallel execution (faster)
pytest -v -n auto
```

---

## Development Tools

### Interactive API Documentation
- **Swagger UI**: http://localhost:3000/docs
- **ReDoc**: http://localhost:3000/redoc
- **OpenAPI JSON**: http://localhost:3000/openapi.json

### Database Management
**MongoDB shell:**
```bash
# Via Docker
docker-compose -f docker-compose.dev.yml exec mongodb mongosh voice_ai

# Local
mongosh voice_ai
```

**Common queries:**
```javascript
// List all campaigns
db.campaigns.find().pretty()

// Find urgent calls
db.call_records.find({"urgency_flagged": true}).pretty()

// Count queue entries by state
db.queue_entries.aggregate([
  { $group: { _id: "$state", count: { $sum: 1 } } }
])
```

### Redis CLI
```bash
# Via Docker
docker-compose -f docker-compose.dev.yml exec redis redis-cli

# Local
redis-cli
```

**Common commands:**
```
# Check Celery queue depth
LLEN celery

# View all keys
KEYS *

# Monitor real-time commands
MONITOR
```

### Celery Monitoring
**Flower (Celery monitoring UI):**
```bash
# Start Flower
celery -A backend.celery_app flower --port=5555

# Open browser
open http://localhost:5555
```

### Logs
```bash
# API server logs
docker-compose -f docker-compose.dev.yml logs -f api

# Celery worker logs
docker-compose -f docker-compose.dev.yml logs -f celery-worker

# All logs
docker-compose -f docker-compose.dev.yml logs -f
```

---

## Production Deployment (CapRover)

### 1. Prepare CapRover Server
```bash
# Install CapRover (one-time setup)
# Follow: https://caprover.com/docs/get-started.html

# Login to CapRover
caprover login
```

### 2. Create Apps
```bash
# Create API app
caprover app create patient-feedback-api

# Create Celery Worker app
caprover app create patient-feedback-worker

# Create Celery Beat app
caprover app create patient-feedback-beat

# Create MongoDB app (or use managed MongoDB Atlas)
caprover app create patient-feedback-mongodb

# Create Redis app
caprover app create patient-feedback-redis
```

### 3. Configure Secrets
**Using CapRover Dashboard:**
1. Navigate to app settings
2. Go to "App Configs" → "Environment Variables"
3. Add secrets:
   - `TWILIO_ACCOUNT_SID`
   - `TWILIO_AUTH_TOKEN`
   - `OPENAI_API_KEY`
   - `JWT_SECRET_KEY`
   - `MONGODB_URI`
   - `REDIS_URL`

**Or use CapRover CLI:**
```bash
caprover app config patient-feedback-api \
  --env TWILIO_ACCOUNT_SID=ACxxxxxx \
  --env TWILIO_AUTH_TOKEN=xxxxxx \
  --env OPENAI_API_KEY=sk-xxxxxx
```

### 4. Deploy API
```bash
# Build and deploy
caprover deploy -a patient-feedback-api

# Or use Git push deployment
git remote add caprover-api git@git.apps.example.com:patient-feedback-api.git
git push caprover-api 001-patient-feedback-api:main
```

### 5. Deploy Celery Worker
```bash
caprover deploy -a patient-feedback-worker \
  --dockerfile ./docker/Dockerfile.worker
```

### 6. Deploy Celery Beat
```bash
caprover deploy -a patient-feedback-beat \
  --dockerfile ./docker/Dockerfile.beat
```

### 7. Configure Health Checks
**CapRover Dashboard → App Settings → HTTP Settings:**
- Health Check Path: `/health/ready`
- Container HTTP Port: `3000`

### 8. Enable Rolling Updates
**captain-definition.json** (in repo root):
```json
{
  "schemaVersion": 2,
  "dockerfilePath": "./docker/Dockerfile.api",
  "deployStrategy": "rolling-update",
  "healthCheckPath": "/health/ready",
  "containerHttpPort": 3000,
  "instanceCount": 2,
  "preDeployFunction": {
    "command": "python -m backend.scripts.migrate_db",
    "enabled": true
  }
}
```

### 9. Verify Deployment
```bash
# Check API health
curl https://patient-feedback-api.apps.example.com/api/v1/health

# Check metrics
curl https://patient-feedback-api.apps.example.com/api/v1/metrics \
  -H "Authorization: Bearer $TOKEN"
```

---

## Configuration Overrides

### Development Environment
```env
# .env.development
LOG_FORMAT=text
LOG_LEVEL=debug
SKIP_STARTUP_VALIDATION=false
USE_DOCKER_SECRETS=false
ENABLE_NETWORK_SEGMENTATION=false
DOCKER_RESOURCE_LIMITS_ENABLED=false
```

### Production Environment
```env
# .env.production (CapRover env vars)
LOG_FORMAT=json
LOG_LEVEL=info
SKIP_STARTUP_VALIDATION=false
USE_DOCKER_SECRETS=true
ENABLE_NETWORK_SEGMENTATION=true
DOCKER_RESOURCE_LIMITS_ENABLED=true
ENABLE_AUTOMATED_BACKUPS=true
ENABLE_ROLLING_UPDATES=true
GRACEFUL_SHUTDOWN_TIMEOUT=600  # 10 minutes for voice calls
```

### Testing Environment
```env
# .env.test
MONGODB_URI=mongodb://localhost:27017/voice_ai_test
REDIS_URL=redis://localhost:6379/1
SKIP_STARTUP_VALIDATION=true
HEALTH_CHECK_DEPENDENCIES=false
```

---

## Troubleshooting

### Issue: MongoDB Connection Failed
**Symptom**: `GET /health/ready` returns 503, MongoDB check unhealthy

**Solution**:
```bash
# Check MongoDB is running
docker-compose -f docker-compose.dev.yml ps mongodb

# Restart MongoDB
docker-compose -f docker-compose.dev.yml restart mongodb

# Check logs
docker-compose -f docker-compose.dev.yml logs mongodb
```

### Issue: Celery Worker Not Processing Queue
**Symptom**: Calls stuck in "pending" state, never initiated

**Solution**:
```bash
# Check Celery worker is running
docker-compose -f docker-compose.dev.yml ps celery-worker

# Check Celery logs
docker-compose -f docker-compose.dev.yml logs celery-worker

# Verify Redis connection
docker-compose -f docker-compose.dev.yml exec redis redis-cli PING
```

### Issue: Twilio Calls Failing
**Symptom**: Test calls return "failed" outcome immediately

**Solution**:
1. Verify Twilio credentials in `.env`
2. Check phone number format (E.164: `+12025551234`)
3. Verify Twilio phone number is active and has voice capability
4. Check Twilio dashboard for error logs

### Issue: 401 Unauthorized on All Endpoints
**Symptom**: Valid token returns 401

**Solution**:
1. Verify JWT secret matches between token generation and validation
2. Check token expiration (24 hours)
3. Re-login to get fresh token

---

## Performance Tuning

### Local Development
```env
# Reduce concurrency for faster startup
CELERY_WORKER_CONCURRENCY=2

# Disable health check caching for testing
HEALTH_CHECK_CACHE_TTL=0
```

### Production
```env
# Increase worker concurrency
CELERY_WORKER_CONCURRENCY=10

# Enable health check caching
HEALTH_CHECK_CACHE_TTL=5

# Adjust resource limits
API_MEMORY_LIMIT=4G
WORKER_MEMORY_LIMIT=2G
```

---

## Next Steps

1. **Read API Contracts**: Review [contracts/README.md](./contracts/README.md) for full API documentation
2. **Understand Data Models**: Review [data-model.md](./data-model.md) for database schema
3. **Follow TDD Workflow**: Write tests first (see [spec.md](./spec.md) acceptance criteria)
4. **Implement Features**: Follow task list in `tasks.md` (generated by `/speckit.tasks` command)

---

## Support & Resources

- **Specification**: [spec.md](./spec.md)
- **Architecture**: [plan.md](./plan.md)
- **Technology Decisions**: [research.md](./research.md)
- **API Contracts**: [contracts/](./contracts/)
- **Deployment Analysis**: [deployment-analysis.md](./deployment-analysis.md)
