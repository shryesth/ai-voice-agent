"""
S3/MinIO storage client for call recordings.

Provides unified interface for uploading and retrieving call recordings
from either AWS S3 or MinIO (self-hosted S3-compatible storage).

Includes exponential backoff retry logic for resilience.
"""

import asyncio
import functools
import logging
import random
from io import BytesIO
from typing import Optional, Callable, TypeVar

import boto3
from botocore.exceptions import ClientError

from backend.app.core.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T")


class S3UploadError(Exception):
    """Custom exception for S3 upload failures after all retries."""

    def __init__(self, message: str, attempts: int, last_error: Optional[Exception] = None):
        super().__init__(message)
        self.attempts = attempts
        self.last_error = last_error


def exponential_backoff(
    max_retries: Optional[int] = None,
    base_delay: Optional[float] = None,
    max_delay: Optional[float] = None,
    jitter: bool = True,
    retriable_exceptions: tuple = (ClientError, ConnectionError, TimeoutError),
) -> Callable:
    """
    Decorator for exponential backoff retry logic.

    Args:
        max_retries: Maximum number of retry attempts (defaults to config)
        base_delay: Base delay in seconds (defaults to config)
        max_delay: Maximum delay in seconds (defaults to config)
        jitter: Whether to add random jitter to delays
        retriable_exceptions: Tuple of exceptions that should trigger retry

    Returns:
        Decorated async function with retry logic
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            # Use config defaults if not specified
            _max_retries = max_retries if max_retries is not None else settings.recording_upload_max_retries
            _base_delay = base_delay if base_delay is not None else settings.recording_upload_base_delay
            _max_delay = max_delay if max_delay is not None else settings.recording_upload_max_delay

            last_exception: Optional[Exception] = None

            for attempt in range(1, _max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except retriable_exceptions as e:
                    last_exception = e

                    if attempt == _max_retries:
                        logger.error(
                            f"S3 operation failed after {attempt} attempts: {e}",
                            exc_info=True
                        )
                        raise S3UploadError(
                            f"S3 operation failed after {attempt} attempts: {e}",
                            attempts=attempt,
                            last_error=e
                        )

                    # Calculate delay with exponential backoff
                    delay = min(_base_delay * (2 ** (attempt - 1)), _max_delay)

                    # Add jitter (0-25% of delay)
                    if jitter:
                        delay = delay * (1 + random.uniform(0, 0.25))

                    logger.warning(
                        f"S3 operation failed (attempt {attempt}/{_max_retries}), "
                        f"retrying in {delay:.2f}s: {e}"
                    )
                    await asyncio.sleep(delay)

            # Should not reach here, but just in case
            raise S3UploadError(
                f"S3 operation failed after {_max_retries} attempts",
                attempts=_max_retries,
                last_error=last_exception
            )

        return wrapper
    return decorator


class S3StorageClient:
    """
    S3/MinIO storage client for call recordings.

    Supports both AWS S3 and MinIO (self-hosted S3-compatible storage).
    When s3_endpoint_url is configured, it connects to MinIO instead of AWS.
    """

    def __init__(self):
        """
        Initialize the S3 client.

        Uses settings from config.py for authentication and endpoint configuration.
        """
        self._client: Optional[boto3.client] = None
        self.bucket = settings.s3_bucket_name

    @property
    def client(self) -> boto3.client:
        """
        Lazy-initialize and return the S3 client.

        Returns:
            Configured boto3 S3 client
        """
        if self._client is None:
            client_kwargs = {
                "service_name": "s3",
                "region_name": settings.s3_region,
            }

            # Add credentials if provided
            if settings.s3_access_key_id and settings.s3_secret_access_key:
                client_kwargs["aws_access_key_id"] = settings.s3_access_key_id
                client_kwargs["aws_secret_access_key"] = settings.s3_secret_access_key

            # Add endpoint URL for MinIO
            if settings.s3_endpoint_url:
                client_kwargs["endpoint_url"] = settings.s3_endpoint_url

            self._client = boto3.client(**client_kwargs)

        return self._client

    async def upload_recording(
        self,
        object_key: str,
        audio_data: bytes,
        content_type: str = "audio/wav"
    ) -> str:
        """
        Upload audio recording to S3/MinIO (no retry, use upload_recording_with_retry for retries).

        Args:
            object_key: S3 object key (path within bucket)
            audio_data: Raw audio bytes to upload
            content_type: MIME type of the audio file

        Returns:
            Full URL to the uploaded recording

        Raises:
            ClientError: If upload fails
        """
        # Ensure bucket exists before uploading
        await self.ensure_bucket_exists()

        self.client.upload_fileobj(
            BytesIO(audio_data),
            self.bucket,
            object_key,
            ExtraArgs={"ContentType": content_type}
        )

        # Build URL based on endpoint
        if settings.s3_endpoint_url:
            url = f"{settings.s3_endpoint_url}/{self.bucket}/{object_key}"
        else:
            url = f"https://{self.bucket}.s3.{settings.s3_region}.amazonaws.com/{object_key}"

        logger.info(f"Uploaded recording to S3: {object_key}")
        return url

    @exponential_backoff()
    async def upload_recording_with_retry(
        self,
        object_key: str,
        audio_data: bytes,
        content_type: str = "audio/wav"
    ) -> str:
        """
        Upload audio recording to S3/MinIO with exponential backoff retry.

        Uses configurable retry settings from config:
        - recording_upload_max_retries (default: 5)
        - recording_upload_base_delay (default: 1.0s)
        - recording_upload_max_delay (default: 60.0s)

        Args:
            object_key: S3 object key (path within bucket)
            audio_data: Raw audio bytes to upload
            content_type: MIME type of the audio file

        Returns:
            Full URL to the uploaded recording

        Raises:
            S3UploadError: If upload fails after all retries
        """
        return await self.upload_recording(object_key, audio_data, content_type)

    async def download_recording(self, object_key: str) -> Optional[bytes]:
        """
        Download recording from S3/MinIO.

        Args:
            object_key: S3 object key (path within bucket)

        Returns:
            Audio bytes if successful, None otherwise
        """
        try:
            response = self.client.get_object(
                Bucket=self.bucket,
                Key=object_key
            )
            audio_data = response['Body'].read()
            logger.info(f"Downloaded {len(audio_data)} bytes from S3: {object_key}")
            return audio_data

        except ClientError as e:
            logger.error(f"Failed to download from S3: {e}")
            return None

    def get_presigned_url(
        self,
        object_key: str,
        expiration: int = 3600
    ) -> str:
        """
        Generate a presigned URL for downloading a recording.

        Args:
            object_key: S3 object key (path within bucket)
            expiration: URL expiration time in seconds (default: 1 hour)

        Returns:
            Presigned URL for downloading the recording

        Raises:
            ClientError: If URL generation fails
        """
        try:
            url = self.client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": object_key},
                ExpiresIn=expiration
            )
            logger.debug(f"Generated presigned URL for: {object_key}")
            return url

        except ClientError as e:
            logger.error(f"Failed to generate presigned URL: {e}")
            raise

    async def delete_recording(self, object_key: str) -> bool:
        """
        Delete a recording from S3/MinIO.

        Args:
            object_key: S3 object key (path within bucket)

        Returns:
            True if deletion was successful

        Raises:
            ClientError: If deletion fails
        """
        try:
            self.client.delete_object(Bucket=self.bucket, Key=object_key)
            logger.info(f"Deleted recording from S3: {object_key}")
            return True

        except ClientError as e:
            logger.error(f"Failed to delete recording from S3: {e}")
            raise

    async def recording_exists(self, object_key: str) -> bool:
        """
        Check if a recording exists in S3/MinIO.

        Args:
            object_key: S3 object key (path within bucket)

        Returns:
            True if the recording exists
        """
        try:
            self.client.head_object(Bucket=self.bucket, Key=object_key)
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            raise

    async def ensure_bucket_exists(self) -> bool:
        """
        Ensure the configured bucket exists, creating it if necessary.

        Returns:
            True if bucket exists or was created successfully

        Raises:
            ClientError: If bucket creation fails
        """
        try:
            self.client.head_bucket(Bucket=self.bucket)
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                # Bucket doesn't exist, create it
                try:
                    if settings.s3_region == "us-east-1":
                        # us-east-1 doesn't need LocationConstraint
                        self.client.create_bucket(Bucket=self.bucket)
                    else:
                        self.client.create_bucket(
                            Bucket=self.bucket,
                            CreateBucketConfiguration={
                                "LocationConstraint": settings.s3_region
                            }
                        )
                    logger.info(f"Created S3 bucket: {self.bucket}")
                    return True
                except ClientError as create_error:
                    logger.error(f"Failed to create S3 bucket: {create_error}")
                    raise
            raise
