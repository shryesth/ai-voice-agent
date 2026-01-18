"""
Unit tests for S3StorageClient.

Tests S3/MinIO storage operations with mocked boto3.
"""

import pytest
import pytest_asyncio
from unittest.mock import MagicMock, patch
from io import BytesIO


class TestS3StorageClient:
    """Tests for S3StorageClient."""

    @pytest.fixture
    def mock_boto3_client(self):
        """Create a mock boto3 S3 client."""
        mock = MagicMock()
        mock.upload_fileobj = MagicMock()
        mock.generate_presigned_url = MagicMock(
            return_value="https://s3.example.com/presigned/file.wav"
        )
        mock.delete_object = MagicMock()
        mock.head_object = MagicMock()
        mock.head_bucket = MagicMock()
        mock.create_bucket = MagicMock()
        return mock

    @pytest.fixture
    def mock_settings(self):
        """Create mock settings."""
        mock = MagicMock()
        mock.s3_endpoint_url = "https://minio.example.com"
        mock.s3_bucket_name = "test-bucket"
        mock.s3_access_key_id = "test-access-key"
        mock.s3_secret_access_key = "test-secret-key"
        mock.s3_region = "us-east-1"
        return mock

    @pytest_asyncio.fixture
    async def storage_client(self, mock_boto3_client, mock_settings):
        """Create an S3StorageClient with mocked dependencies."""
        with patch(
            "backend.app.infrastructure.storage.s3_storage.settings", mock_settings
        ):
            with patch(
                "backend.app.infrastructure.storage.s3_storage.boto3"
            ) as mock_boto3:
                mock_boto3.client.return_value = mock_boto3_client
                from backend.app.infrastructure.storage.s3_storage import (
                    S3StorageClient,
                )

                client = S3StorageClient()
                client._client = mock_boto3_client
                return client

    @pytest.mark.asyncio
    async def test_upload_recording(
        self, storage_client, mock_boto3_client, mock_settings
    ):
        """Test recording upload to S3."""
        with patch(
            "backend.app.infrastructure.storage.s3_storage.settings", mock_settings
        ):
            audio_data = b"\x00\x01\x02\x03" * 100
            object_key = "recordings/campaign/2026/01/call.wav"

            url = await storage_client.upload_recording(
                object_key=object_key, audio_data=audio_data, content_type="audio/wav"
            )

            # Verify upload was called
            mock_boto3_client.upload_fileobj.assert_called_once()
            call_args = mock_boto3_client.upload_fileobj.call_args

            # Verify arguments
            assert call_args[0][1] == "test-bucket"
            assert call_args[0][2] == object_key
            assert call_args[1]["ExtraArgs"]["ContentType"] == "audio/wav"

            # Verify URL format for MinIO
            assert "test-bucket" in url
            assert object_key in url

    @pytest.mark.asyncio
    async def test_upload_recording_aws_s3(self, mock_boto3_client):
        """Test recording upload to AWS S3 (no endpoint URL)."""
        mock_settings_aws = MagicMock()
        mock_settings_aws.s3_endpoint_url = None
        mock_settings_aws.s3_bucket_name = "aws-bucket"
        mock_settings_aws.s3_access_key_id = "aws-access-key"
        mock_settings_aws.s3_secret_access_key = "aws-secret-key"
        mock_settings_aws.s3_region = "us-west-2"

        with patch(
            "backend.app.infrastructure.storage.s3_storage.settings", mock_settings_aws
        ):
            from backend.app.infrastructure.storage.s3_storage import S3StorageClient

            client = S3StorageClient()
            client._client = mock_boto3_client

            audio_data = b"\x00\x01\x02\x03"
            object_key = "recordings/call.wav"

            url = await client.upload_recording(
                object_key=object_key, audio_data=audio_data
            )

            # Verify AWS S3 URL format
            assert "s3.us-west-2.amazonaws.com" in url
            assert "aws-bucket" in url

    @pytest.mark.asyncio
    async def test_get_presigned_url(
        self, storage_client, mock_boto3_client, mock_settings
    ):
        """Test presigned URL generation."""
        with patch(
            "backend.app.infrastructure.storage.s3_storage.settings", mock_settings
        ):
            object_key = "recordings/call.wav"
            expiration = 3600

            url = storage_client.get_presigned_url(
                object_key=object_key, expiration=expiration
            )

            mock_boto3_client.generate_presigned_url.assert_called_once_with(
                "get_object",
                Params={"Bucket": "test-bucket", "Key": object_key},
                ExpiresIn=expiration,
            )
            assert url == "https://s3.example.com/presigned/file.wav"

    @pytest.mark.asyncio
    async def test_delete_recording(
        self, storage_client, mock_boto3_client, mock_settings
    ):
        """Test recording deletion."""
        with patch(
            "backend.app.infrastructure.storage.s3_storage.settings", mock_settings
        ):
            object_key = "recordings/call.wav"

            result = await storage_client.delete_recording(object_key)

            mock_boto3_client.delete_object.assert_called_once_with(
                Bucket="test-bucket", Key=object_key
            )
            assert result is True

    @pytest.mark.asyncio
    async def test_recording_exists_true(
        self, storage_client, mock_boto3_client, mock_settings
    ):
        """Test checking if recording exists (exists case)."""
        with patch(
            "backend.app.infrastructure.storage.s3_storage.settings", mock_settings
        ):
            object_key = "recordings/call.wav"

            result = await storage_client.recording_exists(object_key)

            mock_boto3_client.head_object.assert_called_once_with(
                Bucket="test-bucket", Key=object_key
            )
            assert result is True

    @pytest.mark.asyncio
    async def test_recording_exists_false(
        self, storage_client, mock_boto3_client, mock_settings
    ):
        """Test checking if recording exists (not found case)."""
        from botocore.exceptions import ClientError

        with patch(
            "backend.app.infrastructure.storage.s3_storage.settings", mock_settings
        ):
            mock_boto3_client.head_object.side_effect = ClientError(
                {"Error": {"Code": "404"}}, "head_object"
            )

            object_key = "recordings/nonexistent.wav"

            result = await storage_client.recording_exists(object_key)

            assert result is False

    @pytest.mark.asyncio
    async def test_ensure_bucket_exists_already_exists(
        self, storage_client, mock_boto3_client, mock_settings
    ):
        """Test bucket check when bucket already exists."""
        with patch(
            "backend.app.infrastructure.storage.s3_storage.settings", mock_settings
        ):
            result = await storage_client.ensure_bucket_exists()

            mock_boto3_client.head_bucket.assert_called_once_with(Bucket="test-bucket")
            assert result is True

    @pytest.mark.asyncio
    async def test_ensure_bucket_exists_creates_bucket(
        self, storage_client, mock_boto3_client, mock_settings
    ):
        """Test bucket creation when bucket doesn't exist."""
        from botocore.exceptions import ClientError

        with patch(
            "backend.app.infrastructure.storage.s3_storage.settings", mock_settings
        ):
            mock_boto3_client.head_bucket.side_effect = ClientError(
                {"Error": {"Code": "404"}}, "head_bucket"
            )

            result = await storage_client.ensure_bucket_exists()

            mock_boto3_client.create_bucket.assert_called_once_with(Bucket="test-bucket")
            assert result is True

    @pytest.mark.asyncio
    async def test_ensure_bucket_exists_creates_bucket_non_us_east_1(
        self, mock_boto3_client
    ):
        """Test bucket creation in non-us-east-1 region."""
        from botocore.exceptions import ClientError

        mock_settings_west = MagicMock()
        mock_settings_west.s3_endpoint_url = None
        mock_settings_west.s3_bucket_name = "west-bucket"
        mock_settings_west.s3_access_key_id = "key"
        mock_settings_west.s3_secret_access_key = "secret"
        mock_settings_west.s3_region = "us-west-2"

        with patch(
            "backend.app.infrastructure.storage.s3_storage.settings", mock_settings_west
        ):
            from backend.app.infrastructure.storage.s3_storage import S3StorageClient

            client = S3StorageClient()
            client._client = mock_boto3_client
            mock_boto3_client.head_bucket.side_effect = ClientError(
                {"Error": {"Code": "404"}}, "head_bucket"
            )

            result = await client.ensure_bucket_exists()

            mock_boto3_client.create_bucket.assert_called_once_with(
                Bucket="west-bucket",
                CreateBucketConfiguration={"LocationConstraint": "us-west-2"},
            )
            assert result is True
