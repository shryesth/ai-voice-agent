"""
Individual Service Health Checkers

Each checker:
- Is async for non-blocking operation
- Has a configurable timeout (default 1 second)
- Returns ServiceHealth object
- Handles exceptions gracefully
"""

import asyncio
import time
import logging
from typing import Optional, Callable, Any
from abc import ABC, abstractmethod

from .models import ServiceHealth, ServiceStatus

logger = logging.getLogger(__name__)


class BaseHealthChecker(ABC):
    """Base class for health checkers"""

    def __init__(self, name: str, timeout_seconds: float = 1.0):
        self.name = name
        self.timeout_seconds = timeout_seconds

    @abstractmethod
    async def check(self) -> ServiceHealth:
        """Perform health check - must be implemented by subclasses"""
        pass

    async def check_with_timeout(self) -> ServiceHealth:
        """Run check with timeout protection"""
        try:
            return await asyncio.wait_for(
                self.check(),
                timeout=self.timeout_seconds
            )
        except asyncio.TimeoutError:
            return ServiceHealth(
                name=self.name,
                status=ServiceStatus.UNHEALTHY,
                message=f"Health check timed out after {self.timeout_seconds}s"
            )
        except Exception as e:
            logger.error(f"Health check failed for {self.name}: {e}")
            return ServiceHealth(
                name=self.name,
                status=ServiceStatus.UNHEALTHY,
                message=str(e)
            )


class MongoDBHealthChecker(BaseHealthChecker):
    """MongoDB connectivity checker"""

    def __init__(
        self,
        get_database_func: Callable,
        timeout_seconds: float = 0.5
    ):
        super().__init__("mongodb", timeout_seconds)
        self.get_database = get_database_func

    async def check(self) -> ServiceHealth:
        start = time.time()
        try:
            db = self.get_database()
            if db is None:
                return ServiceHealth(
                    name=self.name,
                    status=ServiceStatus.UNKNOWN,
                    message="Not configured"
                )

            # Use ping command - fastest way to check connectivity
            await db.command("ping")
            latency = (time.time() - start) * 1000

            return ServiceHealth(
                name=self.name,
                status=ServiceStatus.HEALTHY,
                latency_ms=round(latency, 2),
                message="Connected"
            )
        except RuntimeError as e:
            # Database not configured or not connected
            return ServiceHealth(
                name=self.name,
                status=ServiceStatus.UNKNOWN,
                message=str(e)
            )
        except Exception as e:
            return ServiceHealth(
                name=self.name,
                status=ServiceStatus.UNHEALTHY,
                message=str(e)
            )


class RedisHealthChecker(BaseHealthChecker):
    """Redis connectivity checker"""

    def __init__(self, redis_url: str, timeout_seconds: float = 0.5):
        super().__init__("redis", timeout_seconds)
        self.redis_url = redis_url
        self._client = None

    async def check(self) -> ServiceHealth:
        start = time.time()
        try:
            # Import here to avoid issues if redis is not installed
            from redis.asyncio import Redis

            if self._client is None:
                self._client = Redis.from_url(
                    self.redis_url,
                    socket_timeout=self.timeout_seconds,
                    socket_connect_timeout=self.timeout_seconds
                )

            # PING is the standard Redis health check
            result = await self._client.ping()
            latency = (time.time() - start) * 1000

            if result:
                return ServiceHealth(
                    name=self.name,
                    status=ServiceStatus.HEALTHY,
                    latency_ms=round(latency, 2),
                    message="Connected"
                )
            else:
                return ServiceHealth(
                    name=self.name,
                    status=ServiceStatus.UNHEALTHY,
                    message="PING returned False"
                )
        except ImportError:
            return ServiceHealth(
                name=self.name,
                status=ServiceStatus.UNKNOWN,
                message="redis package not installed"
            )
        except Exception as e:
            # Reset client on error
            self._client = None
            return ServiceHealth(
                name=self.name,
                status=ServiceStatus.UNHEALTHY,
                message=str(e)
            )

    async def close(self):
        """Close Redis connection"""
        if self._client:
            await self._client.close()
            self._client = None


class MinIOHealthChecker(BaseHealthChecker):
    """MinIO/S3 storage health checker"""

    def __init__(
        self,
        endpoint_url: Optional[str],
        access_key: str,
        secret_key: str,
        bucket_name: str,
        timeout_seconds: float = 1.0
    ):
        super().__init__("minio", timeout_seconds)
        self.endpoint_url = endpoint_url
        self.access_key = access_key
        self.secret_key = secret_key
        self.bucket_name = bucket_name

    async def check(self) -> ServiceHealth:
        start = time.time()
        try:
            # boto3 is sync, run in executor
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, self._sync_check)
            result.latency_ms = round((time.time() - start) * 1000, 2)
            return result
        except Exception as e:
            return ServiceHealth(
                name=self.name,
                status=ServiceStatus.UNHEALTHY,
                message=str(e)
            )

    def _sync_check(self) -> ServiceHealth:
        """Synchronous S3 check"""
        try:
            import boto3
            from botocore.exceptions import ClientError
            from botocore.config import Config as BotoConfig

            client = boto3.client(
                "s3",
                endpoint_url=self.endpoint_url,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                config=BotoConfig(
                    connect_timeout=2,
                    read_timeout=2,
                    retries={"max_attempts": 1}
                )
            )

            # HEAD request on bucket - fast and cheap
            client.head_bucket(Bucket=self.bucket_name)

            return ServiceHealth(
                name=self.name,
                status=ServiceStatus.HEALTHY,
                message=f"Bucket '{self.bucket_name}' accessible"
            )
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            if error_code == "404":
                return ServiceHealth(
                    name=self.name,
                    status=ServiceStatus.DEGRADED,
                    message=f"Bucket '{self.bucket_name}' not found (service reachable)"
                )
            return ServiceHealth(
                name=self.name,
                status=ServiceStatus.UNHEALTHY,
                message=f"Bucket error: {error_code}"
            )
        except ImportError:
            return ServiceHealth(
                name=self.name,
                status=ServiceStatus.UNKNOWN,
                message="boto3 package not installed"
            )
        except Exception as e:
            return ServiceHealth(
                name=self.name,
                status=ServiceStatus.UNHEALTHY,
                message=str(e)
            )


class CeleryHealthChecker(BaseHealthChecker):
    """Celery worker health checker"""

    def __init__(self, celery_app: Any, timeout_seconds: float = 2.0):
        super().__init__("celery", timeout_seconds)
        self.celery_app = celery_app

    async def check(self) -> ServiceHealth:
        start = time.time()
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, self._sync_check)
            result.latency_ms = round((time.time() - start) * 1000, 2)
            return result
        except Exception as e:
            return ServiceHealth(
                name=self.name,
                status=ServiceStatus.UNHEALTHY,
                message=str(e)
            )

    def _sync_check(self) -> ServiceHealth:
        """Synchronous Celery check"""
        try:
            # Inspect active workers
            inspector = self.celery_app.control.inspect(timeout=1.0)

            # Get active queues - None means no workers
            active = inspector.active()

            if active is None:
                return ServiceHealth(
                    name=self.name,
                    status=ServiceStatus.UNHEALTHY,
                    message="No workers responding"
                )

            worker_count = len(active)
            active_tasks = sum(len(tasks) for tasks in active.values())

            return ServiceHealth(
                name=self.name,
                status=ServiceStatus.HEALTHY,
                message=f"{worker_count} worker(s), {active_tasks} active task(s)",
                details={
                    "workers": list(active.keys()),
                    "active_tasks": active_tasks
                }
            )
        except Exception as e:
            return ServiceHealth(
                name=self.name,
                status=ServiceStatus.UNHEALTHY,
                message=str(e)
            )


class OpenAIConfigChecker(BaseHealthChecker):
    """
    OpenAI configuration checker

    Note: Does NOT test API connectivity as that would be expensive
    and subject to rate limiting. Only validates configuration.
    """

    def __init__(self, api_key: str, model: str):
        super().__init__("openai", 0.1)
        self.api_key = api_key
        self.model = model

    async def check(self) -> ServiceHealth:
        # Only validate configuration, not connectivity
        if not self.api_key:
            return ServiceHealth(
                name=self.name,
                status=ServiceStatus.UNHEALTHY,
                message="API key not configured"
            )

        if not self.api_key.startswith("sk-"):
            return ServiceHealth(
                name=self.name,
                status=ServiceStatus.DEGRADED,
                message="API key format may be invalid"
            )

        return ServiceHealth(
            name=self.name,
            status=ServiceStatus.HEALTHY,
            message=f"Configured (model: {self.model})",
            details={"model": self.model}
        )
