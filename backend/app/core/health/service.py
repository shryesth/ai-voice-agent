"""
Health Check Service

Aggregates all health checkers with caching support.
Provides Kubernetes-style health probes.
"""

import asyncio
import time
import logging
from typing import Dict, Optional, Tuple

from .models import (
    ServiceHealth,
    ServiceStatus,
    HealthResponse,
    LivenessResponse,
    ReadinessResponse,
    StartupResponse,
)
from .checkers import (
    BaseHealthChecker,
    MongoDBHealthChecker,
    RedisHealthChecker,
    MinIOHealthChecker,
    CeleryHealthChecker,
    OpenAIConfigChecker,
)

logger = logging.getLogger(__name__)


class HealthCheckService:
    """
    Centralized health check service with caching

    Features:
    - Aggregates multiple service checkers
    - Caches health status with configurable TTL
    - Runs checks in parallel for speed
    - Distinguishes required vs optional services
    """

    def __init__(
        self,
        cache_ttl_seconds: float = 5.0,
        version: str = "3.0.0"
    ):
        self.cache_ttl_seconds = cache_ttl_seconds
        self.version = version
        self._start_time = time.time()
        self._startup_complete = False
        self._startup_time: Optional[float] = None

        # Checkers: {name: (checker, required)}
        self._checkers: Dict[str, Tuple[BaseHealthChecker, bool]] = {}

        # Cached results: {name: (health, cached_at)}
        self._cache: Dict[str, Tuple[ServiceHealth, float]] = {}

    def register_checker(
        self,
        checker: BaseHealthChecker,
        required: bool = True
    ):
        """Register a health checker"""
        self._checkers[checker.name] = (checker, required)
        logger.debug(f"Registered health checker: {checker.name} (required={required})")

    def mark_startup_complete(self):
        """Mark startup as complete"""
        self._startup_complete = True
        self._startup_time = time.time() - self._start_time
        logger.info(f"Health service: startup complete in {self._startup_time:.2f}s")

    @property
    def uptime_seconds(self) -> float:
        """Get application uptime in seconds"""
        return time.time() - self._start_time

    async def _get_cached_or_check(
        self,
        checker: BaseHealthChecker
    ) -> ServiceHealth:
        """Get cached result or run check"""
        cached = self._cache.get(checker.name)
        if cached:
            health, cached_at = cached
            if time.time() - cached_at < self.cache_ttl_seconds:
                return health

        # Run check and cache result
        health = await checker.check_with_timeout()
        self._cache[checker.name] = (health, time.time())
        return health

    async def check_all(self, use_cache: bool = True) -> HealthResponse:
        """
        Run all health checks

        Args:
            use_cache: Whether to use cached results

        Returns:
            HealthResponse with all service statuses
        """
        services: Dict[str, ServiceHealth] = {}

        if not self._checkers:
            return HealthResponse(
                status=ServiceStatus.HEALTHY,
                version=self.version,
                uptime_seconds=round(self.uptime_seconds, 2),
                services={}
            )

        # Run all checks in parallel
        checker_list = list(self._checkers.values())

        if use_cache:
            tasks = [
                self._get_cached_or_check(checker)
                for checker, _ in checker_list
            ]
        else:
            tasks = [
                checker.check_with_timeout()
                for checker, _ in checker_list
            ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for (checker, required), result in zip(checker_list, results):
            if isinstance(result, Exception):
                services[checker.name] = ServiceHealth(
                    name=checker.name,
                    status=ServiceStatus.UNHEALTHY,
                    message=str(result)
                )
            else:
                services[checker.name] = result

            # Update cache if not using cache
            if not use_cache and not isinstance(result, Exception):
                self._cache[checker.name] = (result, time.time())

        # Determine overall status
        overall_status = self._compute_overall_status(services)

        return HealthResponse(
            status=overall_status,
            version=self.version,
            uptime_seconds=round(self.uptime_seconds, 2),
            services=services
        )

    def _compute_overall_status(
        self,
        services: Dict[str, ServiceHealth]
    ) -> ServiceStatus:
        """Compute overall status from individual services"""
        has_unhealthy_required = False
        has_degraded = False

        for name, health in services.items():
            checker_info = self._checkers.get(name)
            if not checker_info:
                continue

            _, required = checker_info

            if health.status == ServiceStatus.UNHEALTHY:
                if required:
                    has_unhealthy_required = True
            elif health.status == ServiceStatus.DEGRADED:
                has_degraded = True

        if has_unhealthy_required:
            return ServiceStatus.UNHEALTHY
        elif has_degraded:
            return ServiceStatus.DEGRADED
        return ServiceStatus.HEALTHY

    async def liveness(self) -> LivenessResponse:
        """
        Liveness probe - is the process alive?

        This should be very fast and not check external services.
        If this fails, Kubernetes will restart the container.
        """
        return LivenessResponse(status="alive")

    async def readiness(self) -> ReadinessResponse:
        """
        Readiness probe - ready to accept traffic?

        Checks required services only.
        If this fails, Kubernetes removes the pod from service.
        """
        if not self._startup_complete:
            return ReadinessResponse(
                ready=False,
                status=ServiceStatus.UNHEALTHY,
                message="Startup not complete"
            )

        # Check only required services
        services: Dict[str, ServiceStatus] = {}
        all_ready = True

        for name, (checker, required) in self._checkers.items():
            if required:
                health = await self._get_cached_or_check(checker)
                services[name] = health.status
                if not health.is_healthy:
                    all_ready = False

        return ReadinessResponse(
            ready=all_ready,
            status=ServiceStatus.HEALTHY if all_ready else ServiceStatus.UNHEALTHY,
            services=services,
            message=None if all_ready else "One or more required services unhealthy"
        )

    async def startup(self) -> StartupResponse:
        """
        Startup probe - has initialization completed?

        Used during initial startup to give the app time to initialize.
        """
        services_initialized = {
            name: self._startup_complete
            for name in self._checkers.keys()
        }

        return StartupResponse(
            started=self._startup_complete,
            status=ServiceStatus.HEALTHY if self._startup_complete else ServiceStatus.UNHEALTHY,
            initialization_time_seconds=round(self._startup_time or 0, 2),
            services_initialized=services_initialized,
            message="Startup complete" if self._startup_complete else "Starting up..."
        )


# Global health check service instance
_health_service: Optional[HealthCheckService] = None


def get_health_service() -> Optional[HealthCheckService]:
    """Get the global health service instance"""
    return _health_service


async def init_health_service(config) -> HealthCheckService:
    """
    Initialize the global health service with all checkers

    Args:
        config: Application configuration object

    Returns:
        Initialized HealthCheckService
    """
    global _health_service

    from backend.app.services.database import get_database

    cache_ttl = getattr(config, "health", None)
    cache_ttl_seconds = cache_ttl.cache_ttl_seconds if cache_ttl else 5.0

    _health_service = HealthCheckService(
        cache_ttl_seconds=cache_ttl_seconds,
        version="3.0.0"
    )

    # MongoDB - required if configured
    if config.mongodb_url:
        _health_service.register_checker(
            MongoDBHealthChecker(get_database),
            required=True
        )
        logger.info("Health: MongoDB checker registered")

    # Redis - required if queue is enabled
    if config.queue.enabled:
        _health_service.register_checker(
            RedisHealthChecker(config.queue_redis_url),
            required=True
        )
        logger.info("Health: Redis checker registered")

        # Celery - optional even if queue is enabled (workers may be separate)
        try:
            from backend.app.services.queue.celery_app import celery_app
            _health_service.register_checker(
                CeleryHealthChecker(celery_app),
                required=False  # Workers may run separately
            )
            logger.info("Health: Celery checker registered (optional)")
        except ImportError:
            logger.debug("Health: Celery not available, skipping checker")

    # MinIO/S3 - required if recordings enabled with remote storage
    if config.recordings.enabled and config.recordings.is_remote_storage:
        if config.recordings.storage_backend == "minio":
            _health_service.register_checker(
                MinIOHealthChecker(
                    endpoint_url=config.minio.endpoint_url,
                    access_key=config.minio.access_key,
                    secret_key=config.minio.secret_key,
                    bucket_name=config.minio.bucket_name,
                ),
                required=True
            )
            logger.info("Health: MinIO checker registered")
        elif config.recordings.storage_backend == "s3":
            _health_service.register_checker(
                MinIOHealthChecker(
                    endpoint_url=config.s3.endpoint_url,
                    access_key=config.s3.access_key,
                    secret_key=config.s3.secret_key,
                    bucket_name=config.s3.bucket_name,
                ),
                required=True
            )
            logger.info("Health: S3 checker registered")

    # OpenAI - config check only (not connectivity)
    _health_service.register_checker(
        OpenAIConfigChecker(
            api_key=config.openai.api_key,
            model=config.openai_realtime.model,
        ),
        required=True
    )
    logger.info("Health: OpenAI config checker registered")

    return _health_service
