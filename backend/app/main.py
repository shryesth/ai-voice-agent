"""
FastAPI application factory.

Creates and configures the FastAPI application with:
- Lifespan context for startup/shutdown
- Router registration
- CORS middleware
- Exception handlers
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from backend.app.core.config import settings
from backend.app.core.logging import get_logger
from backend.app.core.database import db
from backend.app.core.redis import redis_client

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """
    Application lifespan context manager.

    Handles startup and shutdown events:
    - Startup: Initialize database and Redis connections
    - Shutdown: Gracefully close all connections
    """
    # Startup
    logger.info(
        "Starting application",
        environment=settings.environment,
        log_format=settings.log_format,
    )

    # Validate configuration if not skipped
    if not settings.skip_startup_validation:
        logger.info("Validating startup configuration")
        _validate_required_configs()

    # Initialize database connection
    logger.info("Initializing database connection")
    try:
        # Import models for all user stories
        from backend.app.models.user import User
        from backend.app.models.geography import Geography
        from backend.app.models.campaign import Campaign
        from backend.app.models.call_record import CallRecord
        from backend.app.models.queue_entry import QueueEntry

        # Initialize database with models
        await db.connect(document_models=[User, Geography, Campaign, CallRecord, QueueEntry])
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error("Database initialization failed", error=str(e))
        if not settings.skip_startup_validation:
            raise

    # Run bootstrap operations
    if not settings.skip_startup_validation and settings.enable_bootstrap_admin:
        logger.info("Running bootstrap operations")
        try:
            from backend.app.core.bootstrap import bootstrap_default_admin
            await bootstrap_default_admin()
            logger.info("Bootstrap operations complete")
        except Exception as e:
            logger.error("Bootstrap failed", error=str(e))
            raise

    # Initialize Redis connection
    logger.info("Initializing Redis connection")
    try:
        await redis_client.connect()
        logger.info("Redis initialized successfully")
    except Exception as e:
        logger.error("Redis initialization failed", error=str(e))
        if not settings.skip_startup_validation:
            raise

    logger.info("Application startup complete")

    yield

    # Shutdown
    logger.info("Shutting down application")

    # Close Redis connection
    try:
        await redis_client.close()
        logger.info("Redis connection closed")
    except Exception as e:
        logger.error("Error closing Redis connection", error=str(e))

    # Close database connection
    try:
        await db.close()
        logger.info("Database connection closed")
    except Exception as e:
        logger.error("Error closing database connection", error=str(e))

    logger.info("Application shutdown complete")


def _validate_required_configs() -> None:
    """
    Validate required configuration variables.

    Raises:
        ValueError: If required configs are missing or invalid
    """
    required_fields = [
        "jwt_secret_key",
        "twilio_account_sid",
        "twilio_auth_token",
        "twilio_phone_number",
        "openai_api_key",
    ]

    missing = []
    for field in required_fields:
        value = getattr(settings, field, None)
        if not value or value == "":
            missing.append(field)

    if missing:
        error_msg = f"Missing required configuration: {', '.join(missing)}"
        logger.error("Configuration validation failed", missing_fields=missing)
        raise ValueError(error_msg)

    logger.info("Configuration validation passed")


def create_app() -> FastAPI:
    """
    Create and configure FastAPI application.

    Returns:
        Configured FastAPI application instance
    """
    # OpenAPI metadata
    description = """
## Patient Feedback Collection API

AI-powered voice call system for collecting patient feedback after medical appointments.

### Features

* **🤖 AI Voice Calls**: Automated patient outreach via Twilio + OpenAI Realtime API
* **🌍 Multilingual**: English, Spanish, French, Haitian Creole support
* **⚠️ Urgency Detection**: Automatic flagging of emergency keywords
* **🔄 Smart Retry Logic**: Intelligent retry with failure-specific delays
* **📊 Campaign Management**: Bulk call execution with queue automation
* **🔒 RBAC**: Admin and User roles with privacy controls
* **📈 Monitoring**: Prometheus metrics and DLQ management

### Architecture

- **Voice Pipeline**: Pipecat v0.0.99 + OpenAI gpt-4o-realtime-preview
- **Queue System**: Celery Beat (30s scheduler) + Redis broker
- **Database**: MongoDB 8.0.17 with Beanie ODM
- **Telephony**: Twilio Media Streams (WebSocket)

### Authentication

All endpoints except webhooks require JWT authentication.

1. Login via `POST /api/v1/auth/login` with email/password
2. Receive JWT token in response
3. Include token in Authorization header: `Bearer <token>`

### User Roles

- **Admin**: Full access (create campaigns, manage queue, access DLQ)
- **User**: Read-only access (view campaigns/calls, phone numbers redacted)
"""

    tags_metadata = [
        {
            "name": "Authentication",
            "description": "User authentication and authorization (JWT-based)",
        },
        {
            "name": "Health & Metrics",
            "description": "Health checks, readiness probes, and Prometheus metrics",
        },
        {
            "name": "Geographies",
            "description": "Regional organization with configurable retention policies",
        },
        {
            "name": "Campaigns",
            "description": "Patient feedback campaigns with time windows and concurrency controls",
        },
        {
            "name": "Calls & Webhooks",
            "description": "Voice call records, transcripts, and Twilio webhook integration",
        },
        {
            "name": "Queue & DLQ",
            "description": "Campaign queue management and Dead Letter Queue (DLQ) operations (Admin only)",
        },
    ]

    app = FastAPI(
        title="Patient Feedback Collection API",
        description=description,
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.is_development else None,
        redoc_url="/redoc" if settings.is_development else None,
        openapi_tags=tags_metadata,
        contact={
            "name": "API Support",
            "email": "support@example.com",
        },
        license_info={
            "name": "Proprietary",
        },
    )

    # CORS middleware
    if settings.is_development or settings.is_staging:
        # Development & UAT: Allow all origins for easier testing
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    else:
        # Production: Use configured origins (strict - set via CORS_ORIGINS env var)
        # Example: CORS_ORIGINS="https://app.example.com,https://admin.example.com"
        origins = settings.cors_origins if settings.cors_origins else [
            "https://localhost:3001",  # Default fallback for production testing
        ]
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=settings.cors_allow_credentials,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Content-Type", "Authorization", "Accept", "Origin"],
            max_age=settings.cors_max_age,
        )

    # Exception handlers
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request,
        exc: RequestValidationError
    ) -> JSONResponse:
        """Handle Pydantic validation errors."""
        # Sanitize errors for JSON serialization (Pydantic v2 may include non-serializable objects)
        errors = []
        for error in exc.errors():
            sanitized = {
                "loc": error.get("loc", []),
                "msg": str(error.get("msg", "")),
                "type": error.get("type", "unknown"),
            }
            # Include input if it's serializable
            if "input" in error:
                try:
                    import json
                    json.dumps(error["input"])
                    sanitized["input"] = error["input"]
                except (TypeError, ValueError):
                    sanitized["input"] = str(error["input"])
            errors.append(sanitized)

        logger.warning(
            "Validation error",
            path=request.url.path,
            errors=errors,
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": errors},
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(
        request: Request,
        exc: Exception
    ) -> JSONResponse:
        """Handle unexpected errors."""
        logger.error(
            "Unhandled exception",
            path=request.url.path,
            error=str(exc),
            exc_info=True,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error"},
        )

    # Register routers
    from backend.app.api.v1 import auth, health, geographies, campaigns, calls, queue

    app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])
    app.include_router(health.router, prefix="/api/v1", tags=["Health & Metrics"])
    app.include_router(geographies.router, prefix="/api/v1/geographies", tags=["Geographies"])
    app.include_router(campaigns.campaign_create_router, prefix="/api/v1", tags=["Campaigns"])
    app.include_router(campaigns.router, prefix="/api/v1/campaigns", tags=["Campaigns"])
    app.include_router(calls.router, prefix="/api/v1", tags=["Calls & Webhooks"])
    app.include_router(queue.router, prefix="/api/v1", tags=["Queue & DLQ"])

    logger.info("FastAPI application created")

    return app


# Create application instance
app = create_app()
