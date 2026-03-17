# AI Voice Agent (FastAPI)

An AI-powered voice agent system for automated patient feedback collection via phone calls. Built with FastAPI, Pipecat, OpenAI Realtime API, Twilio, MongoDB, Redis, and Celery. Supports English, Spanish, French, Haitian Creole, and multi-geography deployment.

## Features

- Automated AI voice calls (Twilio + OpenAI Realtime)
- Multilingual support (en, es, fr, ht)
- Flexible queue modes: Forever, Batch, Manual
- Nexus integration for subject sync

# AI Voice Agent (FastAPI)

```
backend/app/
├── api/v1/          # FastAPI route handlers
├── services/        # Business logic
```

- Async-first: All DB, Redis, HTTP ops are async
- State machine: FlowManager handles 6-stage conversation flow
- Environment config: `ENVIRONMENT` variable selects `.env.local`, `.env.uat`, `.env.prod`

## Main Entry Points

- API: `backend/app/main.py` (uvicorn backend.app.main:app)
- Celery: `backend/app/celery_app.py`
- Voice Pipeline: `backend/app/domains/patient_feedback/voice_pipeline.py`

## API Routes

- `POST /api/v1/auth/login` - JWT login
- `GET /api/v1/health/live`, `/ready` - Health probes
- `GET/POST /api/v1/geographies` - Geography management
- `GET/POST /api/v1/queues` - Call queue management
- `GET/POST /api/v1/recipients` - Recipient management

## Celery Tasks

- `split_recording.py` - Audio file processing
- `transcript_translation.py` - Translate transcripts
- `nexus_sync.py` - Nexus subject/result sync (every 60s)
- `recipients` - Queue recipients
- `call_records` - Call data, transcripts
- `recording_dlq` - Failed S3 uploads
- Twilio: Telephony via WebSocket

Stages:

1. Confirm guardian
2. Confirm visit
Voice mapping: en→alloy, es→nova, fr→alloy, ht→echo

## Infrastructure

## Development & Testing

### Quickstart

```bash
git clone https://github.com/shryesth/ai-voice-agent.git
cd ai-voice-agent
cp config/.env.local.example config/.env.local
# Edit config/.env.local with your credentials
docker compose -f docker-compose.dev.yml up
```

### Testing

pytest -m "not slow"  # Exclude slow tests

```

### Code Quality

```bash
black backend/ tests/           # Format
ruff check backend/ tests/      # Lint
mypy backend/                   # Type check
```

### Celery

```bash
celery -A backend.app.celery_app worker --loglevel=info
celery -A backend.app.celery_app beat --loglevel=info
celery -A backend.app.celery_app flower --port=5555
```

## Deployment

- Dev: `docker-compose.dev.yml`
- UAT: `docker-compose.uat.yml`
- Prod: `docker-compose.production.yml`
- CapRover: `git push caprover main`

## Security & Privacy

- JWT authentication, RBAC
- Privacy filtering: `[REDACTED]` for patient_phone in API responses

## Documentation

- [CLAUDE.md](CLAUDE.md) - Architecture, commands, patterns
- [config/README.md](config/README.md) - Configuration details
- [specs/001-patient-feedback-api/](specs/001-patient-feedback-api/) - Feature specs, data models

## License

MIT License

- **Coverage Requirement**: 80% (configured in pytest.ini)
- **Test Markers**: unit, integration, contract, voice, queue, auth
- **Test Fixtures**: async_client, test_db, test_admin_user, auth_headers

## 🎙️ Voice Pipeline

1. **Conversation Stages**:
   - Greeting
   - Confirm Identity
   - Collect Satisfaction Rating (1-10)
   - Completion

2. **Voice Components**:
   - **VAD**: OpenAI Server-side Voice Activity Detection
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

curl <http://localhost:3000/api/v1/health/ready>

# Check MongoDB connection

docker compose -f docker-compose.dev.yml exec mongodb mongosh

```

### Issue: Tests failing
```bash
# Run with verbose output
pytest tests/ -v -s


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

MIT License

## 🆘 Support

For issues or questions:
1. Check [CLAUDE.md](./CLAUDE.md) for architecture and commands
2. Review [config/README.md](./config/README.md) for configuration
3. Check [specs](./specs/001-patient-feedback-api/) for feature details
4. Review git history for recent changes
5. Check Docker logs for runtime errors

## 🗂️ Project Structure

```

ai-voice-agent/
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
