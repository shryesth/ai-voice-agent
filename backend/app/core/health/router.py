"""
Health Check API Endpoints

Kubernetes-style health probes:
- /health/live - Liveness probe (is process alive?)
- /health/ready - Readiness probe (ready for traffic?)
- /health/startup - Startup probe (initialization complete?)
- /health - Full health status with all services
"""

from fastapi import APIRouter, Response, status
from fastapi.responses import JSONResponse

from .service import get_health_service
from .models import ServiceStatus

router = APIRouter(prefix="/health", tags=["Health"])


@router.get(
    "/live",
    summary="Liveness probe",
    description="""
    **Kubernetes Liveness Probe**

    Returns 200 if the process is alive and responding.
    Does NOT check external services - this should be fast.

    If this fails, the container should be restarted.

    Use this for Docker HEALTHCHECK or Kubernetes livenessProbe.
    """,
    responses={
        200: {
            "description": "Process is alive",
            "content": {
                "application/json": {
                    "example": {"status": "alive", "timestamp": "2025-01-15T10:30:00Z"}
                }
            }
        },
        503: {"description": "Process is unresponsive"}
    }
)
async def liveness_probe():
    """Liveness probe - is the process alive?"""
    service = get_health_service()
    if not service:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "unavailable", "message": "Health service not initialized"}
        )

    result = await service.liveness()
    return result


@router.get(
    "/ready",
    summary="Readiness probe",
    description="""
    **Kubernetes Readiness Probe**

    Returns 200 if the service is ready to accept traffic.
    Checks all required external services (MongoDB, Redis, etc.).

    If this fails, traffic should not be routed to this instance.

    Use this for Kubernetes readinessProbe or load balancer health checks.
    """,
    responses={
        200: {
            "description": "Service is ready",
            "content": {
                "application/json": {
                    "example": {
                        "ready": True,
                        "status": "healthy",
                        "services": {"mongodb": "healthy", "redis": "healthy"},
                        "timestamp": "2025-01-15T10:30:00Z"
                    }
                }
            }
        },
        503: {
            "description": "Service is not ready",
            "content": {
                "application/json": {
                    "example": {
                        "ready": False,
                        "status": "unhealthy",
                        "services": {"mongodb": "healthy", "redis": "unhealthy"},
                        "message": "One or more required services unhealthy"
                    }
                }
            }
        }
    }
)
async def readiness_probe(response: Response):
    """Readiness probe - ready to accept traffic?"""
    service = get_health_service()
    if not service:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"ready": False, "message": "Health service not initialized"}

    result = await service.readiness()

    if not result.ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return result


@router.get(
    "/startup",
    summary="Startup probe",
    description="""
    **Kubernetes Startup Probe**

    Returns 200 once initialization is complete.
    Used during initial startup to give the app time to initialize.

    This allows long startup times without affecting liveness checks.

    Use this for Kubernetes startupProbe with slow-starting containers.
    """,
    responses={
        200: {
            "description": "Startup complete",
            "content": {
                "application/json": {
                    "example": {
                        "started": True,
                        "status": "healthy",
                        "initialization_time_seconds": 3.45,
                        "services_initialized": {"mongodb": True, "redis": True}
                    }
                }
            }
        },
        503: {
            "description": "Still starting up",
            "content": {
                "application/json": {
                    "example": {
                        "started": False,
                        "status": "unhealthy",
                        "initialization_time_seconds": 0,
                        "message": "Starting up..."
                    }
                }
            }
        }
    }
)
async def startup_probe(response: Response):
    """Startup probe - has initialization completed?"""
    service = get_health_service()
    if not service:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"started": False, "message": "Health service not initialized"}

    result = await service.startup()

    if not result.started:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return result


@router.get(
    "",
    summary="Full health check",
    description="""
    **Comprehensive Health Status**

    Returns detailed health status of all registered services:
    - MongoDB connectivity and latency
    - Redis connectivity and latency
    - MinIO/S3 storage accessibility
    - Celery worker count and status
    - OpenAI configuration validation

    Results are cached for 5 seconds by default.
    Use `?refresh=true` to bypass cache and force fresh checks.

    This endpoint is suitable for monitoring dashboards and alerting systems.
    """,
    responses={
        200: {
            "description": "Health status retrieved",
            "content": {
                "application/json": {
                    "example": {
                        "status": "healthy",
                        "version": "3.0.0",
                        "uptime_seconds": 3600.5,
                        "timestamp": "2025-01-15T10:30:00Z",
                        "services": {
                            "mongodb": {
                                "name": "mongodb",
                                "status": "healthy",
                                "latency_ms": 2.34,
                                "message": "Connected"
                            },
                            "redis": {
                                "name": "redis",
                                "status": "healthy",
                                "latency_ms": 1.12,
                                "message": "Connected"
                            }
                        }
                    }
                }
            }
        },
        503: {
            "description": "One or more required services unhealthy"
        }
    }
)
async def full_health_check(response: Response, refresh: bool = False):
    """
    Full health check with all services

    Args:
        refresh: If True, bypass cache and force fresh checks
    """
    service = get_health_service()
    if not service:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "unavailable", "message": "Health service not initialized"}

    result = await service.check_all(use_cache=not refresh)

    if result.status == ServiceStatus.UNHEALTHY:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return result
