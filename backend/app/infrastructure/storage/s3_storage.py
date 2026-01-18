"""
S3/MinIO storage client for call recordings.

Provides unified interface for uploading and retrieving call recordings
from either AWS S3 or MinIO (self-hosted S3-compatible storage).
"""

import logging
from io import BytesIO
from typing import Optional

import boto3
from botocore.exceptions import ClientError

from backend.app.core.config import settings

logger = logging.getLogger(__name__)


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
        Upload audio recording to S3/MinIO.

        Args:
            object_key: S3 object key (path within bucket)
            audio_data: Raw audio bytes to upload
            content_type: MIME type of the audio file

        Returns:
            Full URL to the uploaded recording

        Raises:
            ClientError: If upload fails
        """
        try:
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

        except ClientError as e:
            logger.error(f"Failed to upload recording to S3: {e}")
            raise

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
