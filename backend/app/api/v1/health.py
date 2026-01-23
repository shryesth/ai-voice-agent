"""
Health check and metrics endpoints.

Endpoints:
- GET /api/v1/health/live - Liveness probe
- GET /api/v1/health/ready - Readiness probe with dependency checks
- GET /api/v1/metrics - Application metrics (JSON/Prometheus format)
"""

import time
from datetime import datetime, timezone
from typing import Dict, Any
from fastapi import APIRouter, Request, Response, status
from fastapi.responses import JSONResponse, PlainTextResponse

from backend.app.core.config import settings
from backend.app.core.logging import get_logger
from backend.app.core.database import db
from backend.app.core.redis import redis_client

logger = get_logger(__name__)
router = APIRouter()

# Simple in-memory cache for health checks
_health_check_cache: Dict[str, Any] = {}
_cache_timestamp: float = 0.0

# Application start time for uptime calculation
_app_start_time = datetime.now(timezone.utc)


@router.get("/health/live")
async def liveness_probe():
    """
    Liveness probe - simple check if process is alive.

    Returns:
        200 OK with status: alive

    Note: No dependency checks, fast response for Kubernetes/Docker liveness
    """
    return {"status": "alive"}


@router.get("/health/ready")
async def readiness_probe():
    """
    Readiness probe - check if application can serve traffic.

    Checks:
    - MongoDB connection
    - Redis connection

    Returns:
        200 OK if all dependencies healthy
        503 Service Unavailable if any dependency unhealthy

    Note: Results cached for 5s to avoid hammering dependencies
    """
    global _health_check_cache, _cache_timestamp
    
    # Check if we should use cached result
    if settings.health_check_cache_ttl > 0:
        cache_age = time.time() - _cache_timestamp
        if cache_age < settings.health_check_cache_ttl and _health_check_cache:
            logger.debug("Returning cached health check", age=cache_age)
            cached_status = _health_check_cache.get("status")
            if cached_status == "ready":
                return JSONResponse(
                    status_code=status.HTTP_200_OK,
                    content=_health_check_cache
                )
            else:
                return JSONResponse(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    content=_health_check_cache
                )

    # Perform health checks
    checks = {}

    # Check MongoDB
    if settings.health_check_dependencies:
        try:
            mongodb_healthy = await db.ping()
            checks["mongodb"] = mongodb_healthy
            if mongodb_healthy:
                logger.debug("MongoDB health check passed")
            else:
                logger.warning("MongoDB health check failed: ping returned false")
        except Exception as e:
            checks["mongodb"] = False
            logger.warning("MongoDB health check failed", error=str(e))
    else:
        checks["mongodb"] = True  # Skip check if disabled

    # Check Redis
    if settings.health_check_dependencies:
        try:
            await redis_client.ping()
            checks["redis"] = True
            logger.debug("Redis health check passed")
        except Exception as e:
            checks["redis"] = False
            logger.warning("Redis health check failed", error=str(e))
    else:
        checks["redis"] = True  # Skip check if disabled

    # Determine overall status
    all_healthy = all(checks.values())
    result = {
        "status": "ready" if all_healthy else "unhealthy",
        "checks": checks
    }

    # Update cache
    _health_check_cache = result
    _cache_timestamp = time.time()

    # Return appropriate status code
    if all_healthy:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=result
        )
    else:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=result
        )


@router.get("/metrics")
async def metrics(request: Request):
    """
    Application metrics endpoint.

    Supports both JSON and Prometheus formats based on Accept header.

    Returns:
        JSON format: Dict with metrics
        Prometheus format: Plain text in Prometheus exposition format

    Note: No authentication required for metrics scraping
    """
    # Calculate uptime
    uptime_seconds = (datetime.now(timezone.utc) - _app_start_time).total_seconds()

    # Collect metrics
    metrics_data = {
        "uptime_seconds": uptime_seconds,
        "environment": settings.environment,
        "version": "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # Check Accept header for format
    accept_header = request.headers.get("accept", "")

    if "text/plain" in accept_header or "application/openmetrics-text" in accept_header:
        # Return Prometheus format
        prometheus_output = _format_prometheus_metrics(metrics_data)
        return PlainTextResponse(
            content=prometheus_output,
            media_type="text/plain; version=0.0.4"
        )

    # Default: Return JSON format
    return JSONResponse(content=metrics_data)


def _format_prometheus_metrics(metrics: Dict[str, Any]) -> str:
    """
    Format metrics dict as Prometheus exposition format.

    Args:
        metrics: Metrics dictionary

    Returns:
        Prometheus formatted string
    """
    lines = []

    # Add HELP and TYPE comments
    lines.append("# HELP app_uptime_seconds Application uptime in seconds")
    lines.append("# TYPE app_uptime_seconds gauge")
    lines.append(f"app_uptime_seconds {metrics['uptime_seconds']}")

    lines.append("")
    lines.append("# HELP app_info Application information")
    lines.append("# TYPE app_info gauge")
    lines.append(
        f'app_info{{environment="{metrics["environment"]}",version="{metrics["version"]}"}} 1'
    )

    lines.append("")

    return "\n".join(lines) + "\n"
