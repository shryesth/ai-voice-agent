"""
Application configuration using Pydantic Settings.

Loads configuration from environment variables with validation.
All configuration variables defined in research.md with secure defaults.
"""

from typing import Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    # MongoDB Configuration
    mongodb_uri: str = Field(default="mongodb://localhost:27017", description="MongoDB connection URI")
    mongodb_database: str = Field(default="voice_ai", description="MongoDB database name")

    # Redis Configuration
    redis_url: str = Field(default="redis://localhost:6379/0", description="Redis connection URL")

    # Twilio Credentials
    twilio_account_sid: str = Field(..., description="Twilio Account SID")
    twilio_auth_token: str = Field(..., description="Twilio Auth Token")
    twilio_phone_number: str = Field(..., description="Twilio phone number for outbound calls")
    twilio_websocket_url: Optional[str] = Field(
        default=None,
        description="WebSocket URL for Twilio Media Streams (optional - derived from public_url if not set)"
    )

    # OpenAI Configuration
    openai_api_key: str = Field(..., description="OpenAI API key")
    openai_model: str = Field(
        default="gpt-realtime-mini-2025-10-06",
        description="OpenAI Realtime model"
    )

    # Security
    jwt_secret_key: str = Field(..., description="Secret key for JWT token signing")
    jwt_algorithm: str = Field(default="HS256", description="JWT signing algorithm")
    jwt_expiration_hours: int = Field(default=24, description="JWT token expiration in hours")

    # Application Settings
    log_level: str = Field(default="info", description="Logging level")
    log_format: str = Field(default="json", description="Log format: json or text")
    environment: str = Field(default="development", description="Environment: development, staging, production")

    # Configuration Overrides (from research.md)
    # Container Architecture
    enable_supervisor_mode: bool = Field(
        default=False,
        description="Enable supervisord mode (NOT RECOMMENDED - use separate containers)"
    )

    # Resource Limits
    docker_resource_limits_enabled: bool = Field(default=True, description="Enable Docker resource limits")
    api_cpu_limit: str = Field(default="2.0", description="API CPU limit")
    api_memory_limit: str = Field(default="2G", description="API memory limit")
    worker_cpu_limit: str = Field(default="1.0", description="Worker CPU limit")
    worker_memory_limit: str = Field(default="1G", description="Worker memory limit")

    # Secrets Management
    use_docker_secrets: bool = Field(
        default=True,
        description="Use Docker secrets (fallback to env vars if false)"
    )

    # Startup Validation
    skip_startup_validation: bool = Field(
        default=False,
        description="Skip startup config validation (NOT RECOMMENDED)"
    )

    # Health Checks
    health_check_dependencies: bool = Field(
        default=True,
        description="Check dependencies (MongoDB, Redis) in health endpoints"
    )
    health_check_cache_ttl: int = Field(
        default=5,
        description="Health check result cache TTL in seconds"
    )

    # Database Backups
    enable_automated_backups: bool = Field(
        default=True,
        description="Enable automated MongoDB backups"
    )
    backup_interval: int = Field(default=86400, description="Backup interval in seconds (default: 24h)")
    backup_retention_days: int = Field(default=7, description="Backup retention in days")

    # Monitoring
    enable_prometheus_metrics: bool = Field(
        default=True,
        description="Enable Prometheus metrics export"
    )
    enable_dlq_alerts: bool = Field(
        default=True,
        description="Enable Dead Letter Queue alerts"
    )
    metrics_update_interval: int = Field(
        default=15,
        description="Metrics update interval in seconds"
    )

    # Graceful Shutdown
    graceful_shutdown_timeout: int = Field(
        default=30,
        description="Graceful shutdown timeout in seconds"
    )
    celery_worker_shutdown_timeout: int = Field(
        default=600,
        description="Celery worker shutdown timeout in seconds (10 minutes for voice calls)"
    )

    # Deployment
    enable_rolling_updates: bool = Field(
        default=True,
        description="Enable rolling updates for zero-downtime deployments"
    )
    skip_predeploy_hooks: bool = Field(
        default=False,
        description="Skip pre-deploy hooks (migrations)"
    )

    # Network Segmentation
    enable_network_segmentation: bool = Field(
        default=True,
        description="Enable multi-network Docker architecture"
    )

    # CORS Configuration
    cors_origins: list[str] = Field(
        default_factory=list,
        description="Allowed CORS origins (comma-separated in env: CORS_ORIGINS)"
    )
    cors_allow_credentials: bool = Field(
        default=True,
        description="Allow credentials in CORS requests"
    )
    cors_max_age: int = Field(
        default=600,
        description="CORS preflight cache duration in seconds"
    )

    # Celery Configuration
    celery_worker_concurrency: int = Field(
        default=10,
        description="Celery worker concurrency"
    )
    celery_broker_url: Optional[str] = Field(
        default=None,
        description="Celery broker URL (defaults to redis_url)"
    )
    celery_result_backend: Optional[str] = Field(
        default=None,
        description="Celery result backend URL (defaults to redis_url)"
    )

    # Campaign Queue Settings
    queue_processor_interval: int = Field(
        default=30,
        description="Queue processor interval in seconds"
    )
    max_concurrent_calls: int = Field(
        default=10,
        description="Maximum concurrent calls per campaign"
    )
    max_retry_attempts: int = Field(
        default=3,
        description="Maximum retry attempts before DLQ"
    )

    # Call Configuration
    max_call_duration_seconds: int = Field(
        default=600,
        description="Maximum call duration in seconds (10 minutes)"
    )
    carrier_rate_limit_seconds: int = Field(
        default=2,
        description="Minimum seconds between calls per number (carrier compliance)"
    )

    # Supported Languages
    supported_languages: str = Field(
        default="en,es,fr,ht",
        description="Comma-separated list of supported language codes"
    )
    default_language: str = Field(default="en", description="Default language code")

    # S3/MinIO Configuration (for call recordings)
    s3_endpoint_url: Optional[str] = Field(
        default=None,
        description="S3 endpoint URL (required for MinIO, omit for AWS S3)"
    )
    s3_bucket_name: str = Field(
        default="voice-recordings",
        description="S3 bucket name for call recordings"
    )
    s3_access_key_id: Optional[str] = Field(
        default=None,
        description="S3 access key ID"
    )
    s3_secret_access_key: Optional[str] = Field(
        default=None,
        description="S3 secret access key"
    )
    s3_region: str = Field(
        default="us-east-1",
        description="S3 region"
    )

    # Recording Settings
    recording_enabled: bool = Field(
        default=True,
        description="Enable call recording and upload to S3"
    )
    recording_format: str = Field(
        default="wav",
        description="Recording format: wav or mp3"
    )
    recording_sample_rate: int = Field(
        default=24000,
        description="Recording sample rate in Hz"
    )

    # Public URL for Twilio webhooks and media streams
    public_url: Optional[str] = Field(
        default=None,
        description="Public URL for Twilio callbacks and WebSocket (e.g., https://your-domain.com or https://your-domain.ngrok.io)"
    )

    @field_validator("celery_broker_url", mode="before")
    @classmethod
    def set_celery_broker_url(cls, v: Optional[str], info) -> str:
        """Default Celery broker to Redis URL if not set."""
        if v is None:
            return info.data.get("redis_url", "redis://localhost:6379/0")
        return v

    @field_validator("celery_result_backend", mode="before")
    @classmethod
    def set_celery_result_backend(cls, v: Optional[str], info) -> str:
        """Default Celery result backend to Redis URL if not set."""
        if v is None:
            return info.data.get("redis_url", "redis://localhost:6379/0")
        return v

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: Optional[str]) -> list[str]:
        """Parse CORS_ORIGINS from comma-separated string."""
        if v is None or v == "":
            return []
        if isinstance(v, list):
            return v
        # Parse comma-separated string from environment variable
        return [origin.strip() for origin in v.split(",") if origin.strip()]

    @property
    def supported_languages_list(self) -> list[str]:
        """Get supported languages as a list."""
        return [lang.strip() for lang in self.supported_languages.split(",")]

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.environment.lower() == "production"

    @property
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.environment.lower() == "development"

    @property
    def twilio_websocket_url_derived(self) -> str:
        """
        Get Twilio WebSocket URL, deriving from public_url if not explicitly set.

        Converts https:// to wss:// and appends the media stream endpoint path.
        Falls back to twilio_websocket_url if public_url is not set (backward compatibility).

        Returns:
            WebSocket URL for Twilio Media Streams
        """
        if self.twilio_websocket_url:
            # Explicit configuration takes precedence (backward compatibility)
            return self.twilio_websocket_url

        if self.public_url:
            # Derive from public_url
            base_url = self.public_url.rstrip('/')
            # Convert https:// to wss:// for WebSocket protocol
            ws_url = base_url.replace('https://', 'wss://').replace('http://', 'ws://')
            return f"{ws_url}/api/v1/webhooks/twilio/media"

        # Fallback to default (for local dev without proper config)
        return "wss://api.example.com/api/v1/webhooks/twilio/media"


# Global settings instance
settings = Settings()
