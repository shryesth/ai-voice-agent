"""
Structured logging setup with correlation IDs.

Provides JSON-formatted logging for production and human-readable
logging for development. Includes correlation ID tracking for
distributed tracing.
"""

import logging
import sys
from typing import Any, Dict
import structlog
from structlog.types import EventDict, Processor

from backend.app.core.config import settings


def add_correlation_id(logger: Any, method_name: str, event_dict: EventDict) -> EventDict:
    """
    Add correlation IDs to log entries.

    Correlation IDs help trace requests across services:
    - call_sid: Twilio Call SID
    - stream_sid: Twilio Stream SID
    - campaign_id: Campaign identifier
    - request_id: HTTP request identifier
    """
    # These will be set by middleware/context
    # For now, we just ensure the structure is ready
    return event_dict


def drop_color_message_key(logger: Any, method_name: str, event_dict: EventDict) -> EventDict:
    """
    Remove color codes from structured logs.

    Colored output is useful for development but should be
    removed in production JSON logs.
    """
    event_dict.pop("color_message", None)
    return event_dict


def setup_logging() -> None:
    """
    Configure structured logging based on environment settings.

    Production: JSON format with correlation IDs
    Development: Human-readable colored output
    """
    # Determine log level
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    # Configure stdlib logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

    # Build processor chain
    processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        add_correlation_id,
    ]

    # Add format-specific processors
    if settings.log_format == "json":
        # Production: JSON format
        processors.extend([
            drop_color_message_key,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ])
    else:
        # Development: Colored console output
        processors.extend([
            structlog.dev.ConsoleRenderer(colors=True),
        ])

    # Configure structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """
    Get a structured logger instance.

    Args:
        name: Logger name (typically __name__ of the module)

    Returns:
        Configured structlog logger

    Example:
        >>> logger = get_logger(__name__)
        >>> logger.info("call_initiated", call_sid="CA123", campaign_id="camp-456")
    """
    return structlog.get_logger(name)


def mask_sensitive_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Mask sensitive data before logging.

    Sensitive fields:
    - phone numbers (partial masking: +1202555****
)
    - API keys (show only first 8 chars)
    - passwords (completely hidden)
    - auth tokens (completely hidden)

    Args:
        data: Dictionary potentially containing sensitive data

    Returns:
        Dictionary with sensitive data masked
    """
    masked = data.copy()

    # Phone number masking
    if "phone" in masked or "patient_phone" in masked:
        for key in ["phone", "patient_phone", "phone_number"]:
            if key in masked and isinstance(masked[key], str):
                phone = masked[key]
                if len(phone) > 6:
                    masked[key] = f"{phone[:6]}{'*' * (len(phone) - 6)}"

    # API key masking
    for key in ["api_key", "openai_api_key", "twilio_auth_token"]:
        if key in masked and isinstance(masked[key], str):
            value = masked[key]
            masked[key] = f"{value[:8]}{'*' * max(0, len(value) - 8)}" if len(value) > 8 else "***"

    # Complete hiding
    for key in ["password", "hashed_password", "token", "access_token", "secret"]:
        if key in masked:
            masked[key] = "***REDACTED***"

    return masked


# Initialize logging on module import
setup_logging()
