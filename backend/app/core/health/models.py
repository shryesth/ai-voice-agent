"""
Health Check Models

Pydantic models for health check responses.
"""

from enum import Enum
from typing import Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class ServiceStatus(str, Enum):
    """Health status of a service"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"  # Working but with issues
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"  # Not configured or not checked


class ServiceHealth(BaseModel):
    """Health status of a single service"""
    name: str
    status: ServiceStatus
    latency_ms: Optional[float] = None
    message: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    checked_at: datetime = Field(default_factory=datetime.utcnow)

    @property
    def is_healthy(self) -> bool:
        """Check if service is in a healthy or degraded state"""
        return self.status in [ServiceStatus.HEALTHY, ServiceStatus.DEGRADED]


class HealthResponse(BaseModel):
    """Overall health response with all services"""
    status: ServiceStatus
    version: str = "3.0.0"
    uptime_seconds: float
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    services: Dict[str, ServiceHealth] = {}

    @property
    def is_healthy(self) -> bool:
        """Check if overall status is healthy"""
        return self.status == ServiceStatus.HEALTHY


class LivenessResponse(BaseModel):
    """
    Liveness probe response

    Answers: Is the process alive and responding?
    If this fails, the container should be restarted.
    """
    status: str = "alive"
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ReadinessResponse(BaseModel):
    """
    Readiness probe response

    Answers: Is the service ready to accept traffic?
    If this fails, traffic should not be routed to this instance.
    """
    ready: bool
    status: ServiceStatus
    services: Dict[str, ServiceStatus] = {}
    message: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class StartupResponse(BaseModel):
    """
    Startup probe response

    Answers: Has initialization completed?
    Used during initial startup to give the app time to initialize.
    """
    started: bool
    status: ServiceStatus
    initialization_time_seconds: float
    services_initialized: Dict[str, bool] = {}
    message: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
