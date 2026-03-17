# AI Voice Agent (FastAPI)

An AI-powered voice agent system for automated patient feedback collection via phone calls. Built with FastAPI, Pipecat, OpenAI Realtime API, Twilio, MongoDB, Redis, and Celery. Supports English, Spanish, French, Haitian Creole, and multi-geography deployment.

## Features

- Automated AI voice calls with Twilio and OpenAI Realtime
- Multilingual support: English, Spanish, French, Haitian Creole
- Flexible queue modes: Forever, Batch, Manual
- Nexus integration for subject synchronization

## Architecture Overview

- Async-first: all DB, Redis, and HTTP operations are async
- State machine: FlowManager handles the 6-stage conversation flow
- Environment config: `ENVIRONMENT` selects `config/.env.local`, `config/.env.uat`, or `config/.env.prod`

## Main Entry Points

- API: `backend/app/main.py` (`uvicorn backend.app.main:app`)
- Celery: `backend/app/celery_app.py`
- Voice pipeline: `backend/app/domains/patient_feedback/voice_pipeline.py`

## API Routes

- `POST /api/v1/auth/login` - JWT login
- `GET /api/v1/health/live` and `GET /api/v1/health/ready` - health probes
- `GET /api/v1/geographies` and `POST /api/v1/geographies` - geography management
- `GET /api/v1/queues` and `POST /api/v1/queues` - call queue management
- `GET /api/v1/recipients` and `POST /api/v1/recipients` - recipient management

## Celery Tasks

- `queue_processor.py` - periodic queue processing
- `voice_call.py` - call initiation and Twilio webhook handling
- `recording_download.py` - Twilio recording download and S3 upload
- `split_recording.py` - audio file processing
- `transcript_translation.py` - transcript translation
- `nexus_sync.py` - Nexus subject and result synchronization

## Development and Testing

### Quickstart

```bash
git clone https://github.com/shryesth/ai-voice-agent.git
cd ai-voice-agent
cp config/.env.local.example config/.env.local
# Edit config/.env.local with your credentials
docker compose -f docker-compose.dev.yml up
```

### Testing

```bash
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

- Development: `docker-compose.dev.yml`
- UAT: `docker-compose.uat.yml`
- Production: `docker-compose.production.yml`
- CapRover: `git push caprover main`

## Security and Privacy

- JWT authentication with role-based access control
- Patient phone numbers are redacted for non-admin users
- Environment-based configuration; never commit credentials
- CORS is relaxed for dev and UAT, strict for production

## Documentation

- [CLAUDE.md](CLAUDE.md) - architecture, commands, and patterns
- [config/README.md](config/README.md) - configuration details
- [specs/001-patient-feedback-api/](specs/001-patient-feedback-api/) - feature specs, data models, and contracts

## Support

For issues or questions:

1. Check [CLAUDE.md](./CLAUDE.md) for architecture and commands
2. Review [config/README.md](./config/README.md) for configuration
3. Check [specs](./specs/001-patient-feedback-api/) for feature details
4. Review git history for recent changes
5. Check Docker logs for runtime errors

## Project Structure

```text
ai-voice-agent/
|-- backend/
|   `-- app/
|       |-- api/v1/          # REST API endpoints
|       |-- core/            # config, database, security
|       |-- domains/         # feature-specific logic
|       |   |-- patient_feedback/  # patient feedback flows
|       |   `-- supervisor/        # supervisor features
|       |-- models/          # MongoDB document models
|       |-- schemas/         # Pydantic request/response schemas
|       |-- services/        # business logic
|       |-- tasks/           # Celery async tasks
|       |-- infrastructure/  # S3 storage and integrations
|       |-- main.py          # FastAPI app entry point
|       `-- celery_app.py     # Celery configuration
|-- tests/                   # test suite
|-- config/                  # environment configuration
|-- docker/                  # Docker build files
|-- docker-compose.*.yml     # Docker Compose files
|-- CLAUDE.md                # development guide
`-- README.md                # this file
```

## Voice Pipeline

1. Conversation stages
   - Greeting
   - Confirm Identity
   - Collect Satisfaction Rating (1-10)
   - Completion
2. Voice components
   - VAD: OpenAI server-side voice activity detection
   - Speech-to-Text: OpenAI Realtime API
   - LLM: OpenAI gpt-4o-realtime-preview
   - Text-to-Speech: OpenAI Realtime API
   - Transport: Twilio Media Streams over WebSocket

## Monitoring and Alerts

- Prometheus metrics are available at `/metrics`
- Alert groups are defined in `prometheus-alerts.yml`
  - DLQ Count High/Critical
  - Queue Depth High
  - Queue Processor Stalled

## Git Workflow

- Main branch: `main` (production-ready)
- Development branch: `develop` (active development)
- Feature branches: `feature/<name>`
- Commit style: conventional commits such as `feat:`, `fix:`, and `refactor:`

## Contributing

1. Create a feature branch: `git checkout -b feature/your-feature`
2. Make changes and commit: `git commit -m "feat: description"`
3. Push the branch: `git push origin feature/your-feature`
4. Open a pull request to `develop`
5. Ensure tests pass and coverage is maintained

## Additional Resources

- [Pipecat Documentation](https://docs.pipecat.ai/) - Voice pipeline framework
- [OpenAI Realtime API](https://platform.openai.com/docs/guides/realtime) - Real-time voice AI
- [Twilio Media Streams](https://www.twilio.com/docs/voice/media-streams) - WebSocket audio streaming
- [FastAPI Documentation](https://fastapi.tiangolo.com/) - Web framework
- [Celery Documentation](https://docs.celeryproject.io/) - Task queue system

## License

MIT License
