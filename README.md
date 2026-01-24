# Shifo Supervisor

AI-powered voice agent system for patient feedback collection and flexible call management powered by FastAPI, Pipecat, and OpenAI Realtime API.

## 🎯 Features

- **🤖 AI Voice Calls**: Automated outreach via Twilio + OpenAI Realtime API
- **🌍 Multilingual**: English, Spanish, French, Haitian Creole support
- **📞 Flexible Queue Modes**: Forever (continuous), Batch (one-time), Manual
- **🔗 Clarity Integration**: Bidirectional sync for verification subjects
- **⚠️ Urgency Detection**: Automatic flagging of emergency keywords
- **🔄 Smart Retry Logic**: Intelligent retry with failure-specific delays
- **📊 Call Queue Management**: Multiple queues per geography with time windows
- **🔒 RBAC**: Admin and User roles with privacy controls
- **📈 Monitoring**: Prometheus metrics and Dead Letter Queue (DLQ) management
- **🧪 Test Endpoints**: Debug and test call functionality

## 🏗️ Architecture

```
Shifo Supervisor (Server)
└── Geography (Haiti, Honduras, etc.)
    └── CallQueue (multiple per geo)
        └── Recipients
            └── CallRecords
```

**Tech Stack**:
- **Framework**: FastAPI (Python async web framework)
- **Voice Pipeline**: Pipecat v0.0.99 + OpenAI gpt-4o-realtime-preview
- **Queue System**: Celery Beat (30s scheduler) + Redis broker
- **Database**: MongoDB 8.0.17 with Beanie async ODM
- **Telephony**: Twilio Media Streams (WebSocket)
- **Storage**: S3/MinIO for call recordings
- **Deployment**: Docker Compose + CapRover

## 🚀 Quick Start

### Prerequisites

- Docker & Docker Compose
- Git
- Python 3.12+ (for local development)

### Development Environment

1. **Clone and navigate to project**:
   ```bash
   cd shifo-supervisor-backend
   ```

2. **Create local configuration**:
   ```bash
   cp config/.env.local.example config/.env.local
   # Edit config/.env.local with your credentials
   ```

3. **Start all services** (MongoDB, Redis, MinIO, API, Celery):
   ```bash
   docker compose -f docker-compose.dev.yml up
   ```

4. **Access services**:
   - **API Docs**: http://localhost:3000/docs
   - **MinIO Console**: http://localhost:9001 (minioadmin/minioadmin)
   - **Health Check**: http://localhost:3000/api/v1/health/ready

## 📚 Documentation

- **[CLAUDE.md](./CLAUDE.md)** - Development guide with commands and architecture details
- **[config/README.md](./config/README.md)** - Configuration system and environment setup
- **[Specs](./specs/001-patient-feedback-api/)** - Feature specifications and data models

## 🛠️ Development Commands

### Running Services

```bash
# Start all services (dev)
docker compose -f docker-compose.dev.yml up

# View API logs
docker compose -f docker-compose.dev.yml logs -f api

# Stop all services
docker compose -f docker-compose.dev.yml down
```

### Testing

```bash
# Run all tests with coverage
pytest

# Run specific test categories
pytest tests/unit -m unit
pytest tests/integration -m integration
pytest tests/contract -m contract

# Run specific test file
pytest tests/contract/test_auth.py -v

# Run tests by marker
pytest -m "not slow"
pytest -m voice
pytest -m queue
```

### Code Quality

```bash
# Format code
black backend/ tests/

# Lint code
ruff check backend/ tests/

# Type checking
mypy backend/
```

### Celery Tasks

```bash
# Start worker manually (if not running in Docker)
celery -A backend.app.celery_app worker --loglevel=info

# Start beat scheduler manually
celery -A backend.app.celery_app beat --loglevel=info

# Monitor with Flower
celery -A backend.app.celery_app flower --port=5555
```

## 📋 API Endpoints

### Authentication
- `POST /api/v1/auth/login` - Login with email/password

### Health & Metrics
- `GET /api/v1/health/live` - Liveness probe
- `GET /api/v1/health/ready` - Readiness probe

### Core Resources
- `GET/POST /api/v1/geographies` - Geography management
- `GET/POST /api/v1/queues` - Call queue management
- `GET/POST /api/v1/recipients` - Queue recipient management
- `GET /api/v1/calls` - Call records and transcripts

### Testing
- `POST /api/v1/test-calls` - Test voice calls
- `GET /api/v1/queue/dlq` - Dead Letter Queue (DLQ) entries

## 🗄️ Database

MongoDB with Beanie async ODM. Key collections:

| Collection | Purpose |
|-----------|---------|
| `users` | Admin/User accounts with role-based access |
| `geographies` | Regional organization with Clarity integration |
| `call_queues` | Call queue definitions and configuration |
| `recipients` | Queue recipient management |
| `call_records` | Call data with conversation transcripts |
| `recording_dlq` | Failed recording upload tracking |

## 🌐 Deployment

### Local Development
```bash
docker compose -f docker-compose.dev.yml up
```

### UAT/Staging
```bash
# 1. Create environment file
cp config/.env.uat.example config/.env.uat
# Edit config/.env.uat with staging credentials

# 2. Deploy
docker compose -f docker-compose.uat.yml up -d
```

### Production
```bash
# 1. Create environment file
cp config/.env.prod.example config/.env.prod
# Edit config/.env.prod with production credentials

# 2. Deploy with Docker Compose
docker compose -f docker-compose.production.yml up -d

# OR deploy with CapRover
git push caprover main
```

See **[config/README.md](./config/README.md)** for detailed deployment and configuration instructions.

## 🧪 Testing Coverage

- **Coverage Requirement**: 80% (configured in pytest.ini)
- **Test Markers**: unit, integration, contract, voice, queue, auth
- **Test Fixtures**: async_client, test_db, test_admin_user, auth_headers

Run tests:
```bash
pytest tests/ -v --cov=backend --cov-report=html
```

## 🎙️ Voice Pipeline

The Pipecat voice pipeline handles:

1. **Conversation Stages**:
   - Greeting
   - Confirm Identity
   - Confirm Visit
   - Confirm Service
   - Record Side Effects (health events)
   - Collect Satisfaction Rating (1-10)
   - Completion

2. **Voice Components**:
   - **VAD**: Silero Voice Activity Detection (built-in)
   - **Speech-to-Text**: Automatic via OpenAI Realtime API
   - **LLM**: OpenAI gpt-4o-realtime-preview for conversations
   - **Text-to-Speech**: Automatic via OpenAI Realtime API
   - **Transport**: Twilio Media Streams (WebSocket)

## 📊 Monitoring & Alerts

- **Prometheus Metrics**: Available at `/metrics` endpoint
- **Alert Groups** in `prometheus-alerts.yml`:
  - DLQ Count High/Critical
  - Queue Depth High
  - Queue Processor Stalled

## 🔒 Security

- **Authentication**: JWT-based with email/password
- **Authorization**: Role-based access control (Admin/User)
- **Data Privacy**: Phone numbers redacted for non-admin users
- **Secrets**: Environment-based configuration (never commit credentials)
- **CORS**: Relaxed for dev/UAT, strict for production

See **[config/README.md](./config/README.md)** for security best practices.

## 🐛 Troubleshooting

### Issue: Docker containers won't start
```bash
# Check logs
docker compose -f docker-compose.dev.yml logs

# Verify configuration file exists
ls config/.env.local
```

### Issue: API connection errors
```bash
# Check health endpoint
curl http://localhost:3000/api/v1/health/ready

# Check MongoDB connection
docker compose -f docker-compose.dev.yml exec mongodb mongosh
```

### Issue: Tests failing
```bash
# Run with verbose output
pytest tests/ -v -s

# Run specific test
pytest tests/contract/test_auth.py::test_login -v
```

See **[config/README.md](./config/README.md)** for detailed troubleshooting.

## 📝 Git Workflow

- **Main Branch**: `main` (production-ready)
- **Development Branch**: `develop` (active development)
- **Feature Branches**: `feature/<name>` (feature development)
- **Commit Style**: Conventional commits (feat:, fix:, refactor:, etc.)

## 🤝 Contributing

1. Create feature branch: `git checkout -b feature/your-feature`
2. Make changes and commit: `git commit -m "feat: description"`
3. Push branch: `git push origin feature/your-feature`
4. Create pull request to `develop`
5. Ensure tests pass and coverage is maintained

## 📚 Additional Resources

- **[Pipecat Documentation](https://docs.pipecat.ai/)** - Voice pipeline framework
- **[OpenAI Realtime API](https://platform.openai.com/docs/guides/realtime)** - Real-time voice AI
- **[Twilio Media Streams](https://www.twilio.com/docs/voice/media-streams)** - WebSocket audio streaming
- **[FastAPI Documentation](https://fastapi.tiangolo.com/)** - Web framework
- **[Celery Documentation](https://docs.celeryproject.io/)** - Task queue system

## 📄 License

Proprietary - All rights reserved

## 🆘 Support

For issues or questions:
1. Check [CLAUDE.md](./CLAUDE.md) for architecture and commands
2. Review [config/README.md](./config/README.md) for configuration
3. Check [specs](./specs/001-patient-feedback-api/) for feature details
4. Review git history for recent changes
5. Check Docker logs for runtime errors

## 🗂️ Project Structure

```
shifo-supervisor-backend/
├── backend/
│   └── app/
│       ├── api/v1/              # REST API endpoints
│       ├── core/                # Config, database, security
│       ├── domains/             # Feature-specific logic
│       │   ├── patient_feedback/ # Patient feedback flows
│       │   └── supervisor/       # Supervisor features
│       ├── models/              # MongoDB document models
│       ├── schemas/             # Pydantic request/response
│       ├── services/            # Business logic
│       ├── tasks/               # Celery async tasks
│       ├── infrastructure/      # S3 storage, integrations
│       ├── main.py              # FastAPI app factory
│       └── celery_app.py        # Celery configuration
├── tests/                       # Test suite
├── config/                      # Environment configuration
├── docker/                      # Docker build files
├── docker-compose.*.yml         # Docker Compose files
├── CLAUDE.md                    # Development guide
└── README.md                    # This file
```
