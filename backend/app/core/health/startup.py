"""
Startup Validation Script

Validates that required services are available.
Can be run standalone via docker-entrypoint.sh for pre-deployment checks.

Usage:
    python -m backend.app.core.health.startup

Exit codes:
    0 - All services available
    1 - One or more required services unavailable
"""

import asyncio
import time
import logging
import sys
from typing import Callable, Awaitable

# Configure logging for standalone execution
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)


class StartupValidator:
    """
    Validates required services during container startup

    Usage:
        validator = StartupValidator(config)
        success = await validator.validate_all(timeout_seconds=60)
        if not success:
            sys.exit(1)
    """

    def __init__(self, config):
        self.config = config
        self.retry_interval = 2.0  # Seconds between retries

    async def wait_for_service(
        self,
        name: str,
        check_func: Callable[[], Awaitable[bool]],
        timeout_seconds: float = 30,
        required: bool = True
    ) -> bool:
        """
        Wait for a service to become available

        Args:
            name: Service name for logging
            check_func: Async function that returns True if service is available
            timeout_seconds: Maximum time to wait
            required: If False, failure is logged but not fatal

        Returns:
            True if service is available, False otherwise
        """
        start = time.time()
        logger.info(f"  Checking {name}...")

        while time.time() - start < timeout_seconds:
            try:
                if await check_func():
                    elapsed = time.time() - start
                    logger.info(f"  ✓ {name} available ({elapsed:.1f}s)")
                    return True
            except Exception as e:
                logger.debug(f"  {name} not ready: {e}")

            await asyncio.sleep(self.retry_interval)

        if required:
            logger.error(f"  ✗ {name} not available after {timeout_seconds}s - REQUIRED")
            return False
        else:
            logger.warning(f"  ⚠ {name} not available after {timeout_seconds}s - optional, continuing")
            return True

    async def check_mongodb(self) -> bool:
        """Check MongoDB connectivity"""
        from pymongo import AsyncMongoClient

        try:
            client = AsyncMongoClient(
                self.config.mongodb_url,
                serverSelectionTimeoutMS=2000
            )
            await client.admin.command("ping")
            client.close()
            return True
        except Exception:
            return False

    async def check_redis(self) -> bool:
        """Check Redis connectivity"""
        try:
            from redis.asyncio import Redis

            client = Redis.from_url(
                self.config.queue_redis_url,
                socket_timeout=2.0,
                socket_connect_timeout=2.0
            )
            result = await client.ping()
            await client.close()
            return result
        except ImportError:
            logger.warning("  redis package not installed")
            return False
        except Exception:
            return False

    async def check_minio(self) -> bool:
        """Check MinIO/S3 connectivity"""
        try:
            import boto3
            from botocore.exceptions import ClientError
            from botocore.config import Config as BotoConfig

            if self.config.recordings.storage_backend == "minio":
                endpoint_url = self.config.minio.endpoint_url
                access_key = self.config.minio.access_key
                secret_key = self.config.minio.secret_key
                bucket_name = self.config.minio.bucket_name
            else:
                endpoint_url = self.config.s3.endpoint_url
                access_key = self.config.s3.access_key
                secret_key = self.config.s3.secret_key
                bucket_name = self.config.s3.bucket_name

            client = boto3.client(
                "s3",
                endpoint_url=endpoint_url,
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
                config=BotoConfig(
                    connect_timeout=2,
                    read_timeout=2,
                    retries={"max_attempts": 1}
                )
            )
            client.head_bucket(Bucket=bucket_name)
            return True
        except ClientError as e:
            # Bucket might not exist yet, but service is reachable
            if e.response.get("Error", {}).get("Code") == "404":
                return True  # Service is up, bucket just doesn't exist
            return False
        except ImportError:
            logger.warning("  boto3 package not installed")
            return False
        except Exception:
            return False

    async def validate_all(
        self,
        timeout_seconds: float = 60,
        per_service_timeout: float = 30
    ) -> bool:
        """
        Validate all required services

        Args:
            timeout_seconds: Total timeout for all validations (unused, kept for API compat)
            per_service_timeout: Timeout per individual service

        Returns:
            True if all required services are available
        """
        logger.info("=" * 50)
        logger.info("Service Validation")
        logger.info("=" * 50)

        start = time.time()
        all_ok = True

        # MongoDB (required if configured)
        if self.config.mongodb_url:
            if not await self.wait_for_service(
                "MongoDB",
                self.check_mongodb,
                timeout_seconds=per_service_timeout,
                required=True
            ):
                all_ok = False
        else:
            logger.info("  - MongoDB: not configured (skipping)")

        # Redis (required if queue enabled)
        if self.config.queue.enabled:
            if not await self.wait_for_service(
                "Redis",
                self.check_redis,
                timeout_seconds=per_service_timeout,
                required=True
            ):
                all_ok = False
        else:
            logger.info("  - Redis: queue disabled (skipping)")

        # MinIO/S3 (required if remote recordings enabled)
        if self.config.recordings.enabled and self.config.recordings.is_remote_storage:
            if not await self.wait_for_service(
                "MinIO/S3",
                self.check_minio,
                timeout_seconds=per_service_timeout,
                required=True
            ):
                all_ok = False
        else:
            logger.info("  - MinIO/S3: local storage or disabled (skipping)")

        elapsed = time.time() - start
        logger.info("=" * 50)

        if all_ok:
            logger.info(f"All services validated ({elapsed:.1f}s)")
        else:
            logger.error(f"Service validation FAILED ({elapsed:.1f}s)")

        logger.info("=" * 50)
        return all_ok


async def run_startup_validation():
    """
    Run startup validation as a standalone script

    Exit codes:
        0 - All services available
        1 - Required service(s) unavailable
    """
    # Import config here to allow standalone execution
    from config import config

    # Get timeout from config or use defaults
    health_config = getattr(config, "health", None)
    startup_timeout = health_config.startup_timeout_seconds if health_config else 60.0
    per_service_timeout = health_config.per_service_timeout_seconds if health_config else 30.0

    validator = StartupValidator(config)
    success = await validator.validate_all(
        timeout_seconds=startup_timeout,
        per_service_timeout=per_service_timeout
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(run_startup_validation())
