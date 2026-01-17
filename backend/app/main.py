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
        # Import models for User Stories 1 and 2
        from backend.app.models.user import User
        from backend.app.models.geography import Geography
        from backend.app.models.campaign import Campaign

        # Initialize database with models
        await db.connect(document_models=[User, Geography, Campaign])
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error("Database initialization failed", error=str(e))
        if not settings.skip_startup_validation:
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
    app = FastAPI(
        title="Patient Feedback Collection API",
        description="AI-powered patient feedback collection via voice calls",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.is_development else None,
        redoc_url="/redoc" if settings.is_development else None,
    )

    # CORS middleware
    if settings.is_development:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],  # Allow all origins in development
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    else:
        # TODO: Configure specific origins for production
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[],  # Set allowed origins from config
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            allow_headers=["*"],
        )

    # Exception handlers
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request,
        exc: RequestValidationError
    ) -> JSONResponse:
        """Handle Pydantic validation errors."""
        logger.warning(
            "Validation error",
            path=request.url.path,
            errors=exc.errors(),
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": exc.errors()},
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
    from backend.app.api.v1 import auth, health, geographies, campaigns, calls

    app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])
    app.include_router(health.router, prefix="/api/v1", tags=["Health & Metrics"])
    app.include_router(geographies.router, prefix="/api/v1/geographies", tags=["Geographies"])
    app.include_router(campaigns.router, prefix="/api/v1/campaigns", tags=["Campaigns"])
    app.include_router(calls.router, prefix="/api/v1", tags=["Calls & Webhooks"])
    # More routers will be added in subsequent user stories

    logger.info("FastAPI application created")

    return app


# Create application instance
app = create_app()
